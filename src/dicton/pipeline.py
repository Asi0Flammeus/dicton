"""Pipeline orchestrator — the only file that owns the full lifecycle.

Soft cap: ≤500 LOC (`scripts/check.sh lint`). The cap exists to keep the
orchestrator from becoming a junk drawer — when this file starts growing
domain logic (chunking, HTTP, paste, output, audio session, …) extract
it to a sibling module instead of cramming it here. Wiring stays, logic
moves.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx
import numpy as np
import sounddevice as sd
from pynput import keyboard

from . import cleanup as cleanup_mod
from . import stats, stt
from .async_lifecycle import AsyncLoopRunner
from .chunker import Chunker, ChunkParams
from .config import Config
from .gesture import DoubleTapRecognizer
from .os_ import audio_session, fn_key, hotkey
from .os_.paste import paste
from .visualizer import Visualizer

log = logging.getLogger("dicton")


class State(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"


# Reject secondary-key presses arriving within this window of the previous
# accepted one — covers physical chatter and an impatient finger mashing the
# key. Wider than the double-tap window because a real start→speak→stop has
# at least a second between presses; tighter than that would let bounces
# through.
SECONDARY_DEBOUNCE_S = 0.5


@dataclass
class _Session:
    chunks: dict[int, asyncio.Task]
    started_at: float
    paused_players: list[str] = field(default_factory=list)
    max_duration_task: asyncio.Task | None = None


class Pipeline:
    """Wires hotkey + audio + chunker + Groq HTTP + paste. Long-lived."""

    def __init__(self, cfg: Config, *, viz: Visualizer | None = None) -> None:
        self.cfg = cfg
        self.viz = viz
        self._runner = AsyncLoopRunner(lambda: httpx.AsyncClient(http2=True, http1=True))
        self._stream: sd.InputStream | None = None
        self._chunker = Chunker(self._chunk_params(), self._on_chunk_ready)
        self._session: _Session | None = None
        self._stop = threading.Event()
        self._fn_listener: fn_key.FnKeyListener | None = None
        self._listener: keyboard.Listener | None = None
        self._primary_taps = DoubleTapRecognizer(self._trigger)
        self._secondary_last = 0.0
        self._state = State.IDLE
        self._state_lock = threading.Lock()

    def _chunk_params(self) -> ChunkParams:
        c = self.cfg.chunk
        return ChunkParams(
            min_chunk_s=c.min_chunk_s,
            max_chunk_s=c.max_chunk_s,
            overlap_s=c.overlap_s,
            silence_threshold_dbfs=c.silence_threshold_dbfs,
            silence_window_s=c.silence_window_s,
            sample_rate=self.cfg.sample_rate,
        )

    # ---- lifecycle ----

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def start(self) -> None:
        self._runner.start()
        self._start_hotkeys()
        log.info(
            "dicton ready: hotkey=%s/%s model=%s",
            self.cfg.hotkey_primary,
            self.cfg.hotkey_secondary,
            self.cfg.cleanup_model,
        )

    def stop(self) -> None:
        if self._stop.is_set():
            return
        self._stop.set()
        self._close_stream()
        if self._session is not None:
            max_duration_task = getattr(self._session, "max_duration_task", None)
            if max_duration_task is not None:
                max_duration_task.cancel()
            audio_session.resume_players(self._session.paused_players)
            self._session = None
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._fn_listener is not None:
            self._fn_listener.stop()
            self._fn_listener = None
        self._primary_taps.stop()
        if self.viz is not None:
            self.viz.stop()
        self._runner.close(timeout=5.0)

    def _close_stream(self) -> None:
        stream = self._stream
        if stream is None:
            return
        try:
            stop = getattr(stream, "stop", None)
            if stop is not None:
                stop()
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()
            self._stream = None

    def _set_idle(self) -> None:
        with self._state_lock:
            self._state = State.IDLE
        if self.viz is not None:
            self.viz.set_state("idle")

    # ---- hotkey wiring ----

    def _start_hotkeys(self) -> None:
        fn_keycode = self.cfg.hotkey_fn_keycode
        secondary = _parse_key(self.cfg.hotkey_secondary)
        # Primary = double-tap (taptap), recognised by the recognizer which
        # discards single taps and 3+ bursts as noise. On Linux it rides the
        # evdev path (learned keycode), so we don't also bind it via pynput.
        primary = None if fn_keycode is not None else _parse_key(self.cfg.hotkey_primary)
        held: set[object] = set()

        # Only pynput's macOS backend exposes Key.fn. Windows and Linux
        # X11 backends don't define it — Linux uses evdev (KEY_WAKEUP on
        # ThinkPads, KEY_FN elsewhere), Windows has no userland Fn path
        # at all. The OS-specific lookup lives in os_.hotkey.
        pynput_fn = hotkey.pynput_primary_key()

        def _is_primary(norm: object) -> bool:
            return norm == primary or (pynput_fn is not None and norm == pynput_fn)

        def on_press(key: object) -> None:
            norm = _normalize(key)
            if norm in held:
                return  # ignore X11 / Quartz autorepeat
            if _is_primary(norm):
                held.add(norm)
                self._primary_taps.feed_tap()
                return
            if secondary is not None and norm == secondary:
                held.add(norm)
                self._secondary_press()

        def on_release(key: object) -> None:
            held.discard(_normalize(key))

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

        keycodes = fn_key.FN_KEYCODES | ({fn_keycode} if fn_keycode is not None else set())
        self._fn_listener = fn_key.FnKeyListener(self._primary_taps.feed_tap, keycodes=keycodes)
        self._fn_listener.start()

    # ---- state transitions ----

    def _secondary_press(self) -> None:
        # Secondary key is a single-tap toggle, but debounced: a deliberate
        # start→speak→stop has seconds between presses, so both pass; rapid
        # repeats / chatter within the window are refused as noise.
        now = time.monotonic()
        if now - self._secondary_last < SECONDARY_DEBOUNCE_S:
            return
        self._secondary_last = now
        self._trigger()

    def _trigger(self) -> None:
        """Advance the state machine on a significant gesture (clean taptap, or
        a debounced secondary press): IDLE→RECORDING→PROCESSING. PROCESSING is
        locked until it auto-returns to IDLE at the end of _end."""
        with self._state_lock:
            if self._state is State.IDLE:
                self._state = State.RECORDING
                coro_fn = self._begin
            elif self._state is State.RECORDING:
                self._state = State.PROCESSING
                coro_fn = self._end
            else:
                log.debug("trigger ignored — state=processing")
                return
        self._runner.submit(coro_fn())

    # ---- session lifecycle (async, on the loop) ----

    async def _stop_after_max_duration(self) -> None:
        await asyncio.sleep(self.cfg.max_recording_s)
        with self._state_lock:
            if self._state is not State.RECORDING:
                return
            self._state = State.PROCESSING
        log.warning("recording exceeded %.1fs; stopping automatically", self.cfg.max_recording_s)
        await self._end()

    async def _begin(self) -> None:
        if self._session is not None:
            return
        paused: list[str] = []
        try:
            self._chunker.reset()
            paused = audio_session.pause_active_players()
            self._session = _Session(chunks={}, started_at=time.monotonic(), paused_players=paused)
            self._session.max_duration_task = asyncio.create_task(self._stop_after_max_duration())
            if self.viz is not None:
                self.viz.set_state("recording")
            client = self._runner.client
            if client is None:
                raise RuntimeError("async client is not started")
            asyncio.create_task(stt.prewarm(client, api_key=self.cfg.groq_api_key))
            self._stream = sd.InputStream(
                samplerate=self.cfg.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=int(self.cfg.sample_rate * 0.05),
                callback=self._audio_cb,
                device=self.cfg.input_device,
            )
            self._stream.start()
        except Exception:
            if self._session is not None and self._session.max_duration_task is not None:
                self._session.max_duration_task.cancel()
            self._close_stream()
            if paused:
                audio_session.resume_players(paused)
            self._session = None
            self._set_idle()
            raise

    def _audio_cb(self, indata: np.ndarray, frames: int, time_info, status) -> None:  # type: ignore[no-untyped-def]
        if status:
            log.debug("audio status: %s", status)
        mono = indata[:, 0].copy()
        if self.viz is not None:
            self.viz.push_frame(mono)
        self._runner.call(self._chunker.feed, mono)

    def _on_chunk_ready(self, chunk_id: int, wav: bytes) -> None:
        client = self._runner.client
        if self._session is None or client is None:
            return
        task = asyncio.create_task(
            stt.transcribe(
                client,
                wav,
                api_key=self.cfg.groq_api_key,
                model=self.cfg.stt_model,
                language=self.cfg.language,
            )
        )
        self._session.chunks[chunk_id] = task

    async def _end(self) -> None:
        if self._session is None:
            self._set_idle()
            return
        session = self._session
        max_duration_task = getattr(session, "max_duration_task", None)
        if max_duration_task is not None and max_duration_task is not asyncio.current_task():
            max_duration_task.cancel()
        recording_ended_at = time.monotonic()
        recording_ms = int((recording_ended_at - session.started_at) * 1000)
        paste_error: Exception | None = None
        cleaned = ""
        stt_ms = 0
        cleanup_ms = 0

        try:
            self._close_stream()

            self._chunker.flush()
            self._session = None
            if self.viz is not None:
                self.viz.set_state("processing")

            t_stt_start = time.monotonic()
            ordered_ids = sorted(session.chunks)
            texts: list[str] = []
            dropped = 0
            for cid in ordered_ids:
                try:
                    transcript = await session.chunks[cid]
                except Exception as exc:
                    log.warning("chunk %d failed: %s", cid, exc)
                    continue
                dropped += transcript.dropped
                texts.append(transcript.clean_text())
            joined = " ".join(t for t in texts if t).strip()
            if dropped:
                log.info("dropped %d hallucinated segment(s)", dropped)
            stt_ms = int((time.monotonic() - t_stt_start) * 1000)

            t_cl_start = time.monotonic()
            client = self._runner.client
            if client is None:
                raise RuntimeError("async client is not started")
            cleaned = await cleanup_mod.cleanup(
                client,
                joined,
                api_key=self.cfg.groq_api_key,
                model=self.cfg.cleanup_model,
            )
            cleanup_ms = int((time.monotonic() - t_cl_start) * 1000)

            if self.viz is not None:
                self.viz.set_state("idle")

            if cleaned:
                try:
                    await asyncio.to_thread(paste, cleaned)
                except Exception as exc:  # noqa: BLE001
                    paste_error = exc
                    log.error("paste failed: %s", exc, exc_info=True)

            process_ms = int((time.monotonic() - recording_ended_at) * 1000)
            try:
                stats.record(
                    stats.Dictation(
                        ts=stats.now_iso(),
                        duration_s=round(recording_ms / 1000.0, 2),
                        chars=len(cleaned),
                        chunks=len(session.chunks),
                        recording_ms=recording_ms,
                        process_ms=process_ms,
                        stt_ms=stt_ms,
                        cleanup_ms=cleanup_ms,
                        model=self.cfg.cleanup_model,
                    )
                )
            except OSError as exc:
                log.warning("stats append failed: %s", exc)
        finally:
            audio_session.resume_players(session.paused_players)
            self._session = None
            self._set_idle()

        log.info(
            "dictation: %d chars · recording=%dms · process=%dms (stt=%dms cleanup=%dms) · chunks=%d%s",
            len(cleaned),
            recording_ms,
            int((time.monotonic() - recording_ended_at) * 1000),
            stt_ms,
            cleanup_ms,
            len(session.chunks),
            " · PASTE FAILED" if paste_error else "",
        )


def _parse_key(name: str) -> object | None:
    """Map a config string ('f2', 'ctrl', 'space') to a pynput key."""
    name = name.strip().lower()
    if not name:
        return None
    if hasattr(keyboard.Key, name):
        return getattr(keyboard.Key, name)
    if len(name) == 1:
        return keyboard.KeyCode.from_char(name)
    return None


def _normalize(key: object) -> object:
    if isinstance(key, keyboard.KeyCode) and key.char is not None:
        return keyboard.KeyCode.from_char(key.char.lower())
    return key
