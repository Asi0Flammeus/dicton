"""Hotkey → audio chunks → Groq STT → one cleanup → paste."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

from .chunker import Chunker, ChunkSettings
from .cleanup import cleanup_text
from .config import Config, load_config
from .output import paste
from .stats import DictationStat, append_stat
from .stt import GroqClient, transcribe
from .visualizer import Visualizer


class Pipeline:
    def __init__(self, cfg: Config | None = None) -> None:
        self.cfg = cfg or load_config()
        settings = ChunkSettings(
            **{k: v for k, v in asdict(self.cfg).items() if k in ChunkSettings.__dataclass_fields__}
        )
        self.chunker = Chunker(settings)
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.visualizer = Visualizer()
        self._client: GroqClient | None = None
        self._tasks: list[asyncio.Task[str]] = []
        self._recording = False
        self._started = 0.0

    async def start_recording(self) -> None:
        self._client = GroqClient(self.cfg.groq_api_key)
        self.chunker.reset()
        self._tasks.clear()
        self._started = time.monotonic()
        self._recording = True
        self.visualizer.start()
        asyncio.create_task(self._client.prewarm())

    async def feed_audio(self, pcm16: bytes) -> None:
        if not self._recording or not self._client:
            return
        self.visualizer.feed(pcm16)
        wav = self.chunker.feed(pcm16)
        if wav:
            self._tasks.append(asyncio.create_task(transcribe(self._client, wav)))

    async def stop_recording(self) -> str:
        if not self._client:
            raise RuntimeError("Recording was not started")
        released = time.monotonic()
        self._recording = False
        self.visualizer.stop()
        tail = self.chunker.flush()
        if tail:
            self._tasks.append(asyncio.create_task(transcribe(self._client, tail)))
        raw_parts = await asyncio.gather(*self._tasks, return_exceptions=True)
        transcript = " ".join(str(p) for p in raw_parts if isinstance(p, str) and p.strip())
        cleaned = await cleanup_text(self._client, transcript, self.cfg.cleanup_model)
        paste(cleaned)
        latency_ms = round((time.monotonic() - released) * 1000)
        append_stat(
            DictationStat(
                len(cleaned),
                released - self._started,
                latency_ms,
                len(self._tasks),
                self.cfg.cleanup_model,
            )
        )
        await self._client.close()
        return cleaned


def run_daemon() -> None:
    """Run global hotkeys. Audio capture is imported only at runtime."""
    from pynput import keyboard

    pipeline = Pipeline()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def simulated_hold() -> None:
        # Real audio callbacks call feed_audio(); this keeps daemon wiring compact
        # and testable while sounddevice integration remains behind runtime import.
        import sounddevice as sd

        frame_samples = int(pipeline.cfg.sample_rate * pipeline.cfg.frame_ms / 1000)

        def cb(indata, _frames, _time, _status):
            loop.call_soon_threadsafe(asyncio.create_task, pipeline.feed_audio(bytes(indata)))

        await pipeline.start_recording()
        with sd.RawInputStream(
            samplerate=pipeline.cfg.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=frame_samples,
            callback=cb,
        ):
            while pipeline._recording:
                await asyncio.sleep(0.02)

    task: asyncio.Task[None] | None = None

    def on_press(key):
        nonlocal task
        if (
            str(key).lower()
            in {pipeline.cfg.primary_hotkey, pipeline.cfg.secondary_hotkey, "key.f2"}
            and not pipeline._recording
        ):
            task = loop.create_task(simulated_hold())

    def on_release(key):
        if (
            str(key).lower()
            in {pipeline.cfg.primary_hotkey, pipeline.cfg.secondary_hotkey, "key.f2"}
            and pipeline._recording
        ):
            pipeline._recording = False
            loop.create_task(pipeline.stop_recording())

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.start()
    try:
        loop.run_forever()
    finally:
        listener.stop()
