"""Pipeline orchestrator — the only file that owns the full lifecycle.

Hard cap: ≤300 LOC. Validated by `scripts/check.sh lint` (a length guard
is enforced in CI). Anything domain-specific (chunking, HTTP, paste) lives
elsewhere; this file wires them.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass

import httpx
import numpy as np
import sounddevice as sd
from pynput import keyboard

from . import cleanup as cleanup_mod
from . import fn_key, stats, stt
from .chunker import Chunker, ChunkParams
from .config import Config
from .output import paste
from .visualizer import Visualizer

log = logging.getLogger("dicton")


@dataclass
class _Session:
    chunks: dict[int, asyncio.Task]
    started_at: float


class Pipeline:
    """Wires hotkey + audio + chunker + Groq HTTP + paste. Long-lived."""

    def __init__(self, cfg: Config, *, viz: Visualizer | None = None) -> None:
        self.cfg = cfg
        self.viz = viz
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None
        self._loop_ready = threading.Event()
        self._client: httpx.AsyncClient | None = None
        self._stream: sd.InputStream | None = None
        self._chunker = Chunker(self._chunk_params(), self._on_chunk_ready)
        self._session: _Session | None = None
        self._stop = threading.Event()
        self._fn_listener: fn_key.FnKeyListener | None = None
        self._hotkey_active = False
        self._hotkey_lock = threading.Lock()

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

    def start(self) -> None:
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()
        self._loop_ready.wait()
        self._start_hotkeys()
        log.info(
            "dicton ready: hotkey=%s/%s model=%s",
            self.cfg.hotkey_primary,
            self.cfg.hotkey_secondary,
            self.cfg.cleanup_model,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._fn_listener is not None:
            self._fn_listener.stop()
        if self.viz is not None:
            self.viz.stop()

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._client = httpx.AsyncClient(http2=True, http1=True)
        self._loop_ready.set()
        try:
            loop.run_forever()
        finally:
            loop.run_until_complete(self._client.aclose())
            loop.close()

    # ---- hotkey wiring ----

    def _start_hotkeys(self) -> None:
        primary = _parse_key(self.cfg.hotkey_primary)
        secondary = _parse_key(self.cfg.hotkey_secondary)
        watched = {primary, secondary} - {None}

        def on_press(key: object) -> None:
            if _normalize(key) in watched:
                self._press()

        def on_release(key: object) -> None:
            if _normalize(key) in watched:
                self._release()

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

        self._fn_listener = fn_key.FnKeyListener(self._press, self._release)
        self._fn_listener.start()

    # ---- press / release (thread-safe entrypoints) ----

    def _press(self) -> None:
        with self._hotkey_lock:
            if self._hotkey_active:
                return
            self._hotkey_active = True
        asyncio.run_coroutine_threadsafe(self._begin(), self._loop)  # type: ignore[arg-type]

    def _release(self) -> None:
        with self._hotkey_lock:
            if not self._hotkey_active:
                return
            self._hotkey_active = False
        asyncio.run_coroutine_threadsafe(self._end(), self._loop)  # type: ignore[arg-type]

    # ---- session lifecycle (async, on the loop) ----

    async def _begin(self) -> None:
        if self._session is not None:
            return
        self._chunker.reset()
        self._session = _Session(chunks={}, started_at=time.monotonic())
        if self.viz is not None:
            self.viz.set_state("recording")
        asyncio.create_task(stt.prewarm(self._client, api_key=self.cfg.groq_api_key))  # type: ignore[arg-type]
        self._stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=int(self.cfg.sample_rate * 0.05),
            callback=self._audio_cb,
        )
        self._stream.start()

    def _audio_cb(self, indata: np.ndarray, frames: int, time_info, status) -> None:  # type: ignore[no-untyped-def]
        if status:
            log.debug("audio status: %s", status)
        mono = indata[:, 0].copy()
        if self.viz is not None:
            self.viz.push_frame(mono)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._chunker.feed, mono)

    def _on_chunk_ready(self, chunk_id: int, wav: bytes) -> None:
        if self._session is None or self._client is None:
            return
        task = asyncio.create_task(
            stt.transcribe(
                self._client,
                wav,
                api_key=self.cfg.groq_api_key,
                model=self.cfg.stt_model,
                language=self.cfg.language,
            )
        )
        self._session.chunks[chunk_id] = task

    async def _end(self) -> None:
        if self._session is None:
            return
        session = self._session
        self._session = None

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self._chunker.flush()
        if self.viz is not None:
            self.viz.set_state("processing")

        t_stt_start = time.monotonic()
        ordered_ids = sorted(session.chunks)
        texts: list[str] = []
        for cid in ordered_ids:
            try:
                texts.append(await session.chunks[cid])
            except Exception as exc:
                log.warning("chunk %d failed: %s", cid, exc)
        joined = " ".join(t for t in texts if t).strip()
        stt_ms = int((time.monotonic() - t_stt_start) * 1000)

        t_cl_start = time.monotonic()
        cleaned = await cleanup_mod.cleanup(
            self._client,  # type: ignore[arg-type]
            joined,
            api_key=self.cfg.groq_api_key,
            model=self.cfg.cleanup_model,
        )
        cleanup_ms = int((time.monotonic() - t_cl_start) * 1000)

        if cleaned:
            await asyncio.to_thread(paste, cleaned)

        e2e_ms = int((time.monotonic() - session.started_at) * 1000)
        try:
            stats.record(
                stats.Dictation(
                    ts=stats.now_iso(),
                    duration_s=round(time.monotonic() - session.started_at, 2),
                    chars=len(cleaned),
                    chunks=len(session.chunks),
                    e2e_ms=e2e_ms,
                    stt_ms=stt_ms,
                    cleanup_ms=cleanup_ms,
                    model=self.cfg.cleanup_model,
                )
            )
        except OSError as exc:
            log.warning("stats append failed: %s", exc)

        if self.viz is not None:
            self.viz.set_state("idle")
        log.info(
            "dictation: %d chars in %dms (stt=%dms cleanup=%dms chunks=%d)",
            len(cleaned),
            e2e_ms,
            stt_ms,
            cleanup_ms,
            len(session.chunks),
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


def run(cfg: Config) -> None:
    """Blocking entrypoint — wires pygame on the main thread when enabled."""
    viz = Visualizer() if cfg.visualizer else None
    pipe = Pipeline(cfg, viz=viz)
    pipe.start()

    try:
        if viz is not None:
            viz.run()  # main-thread pygame loop
        else:
            while not pipe._stop.is_set():
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        pipe.stop()
