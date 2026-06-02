from __future__ import annotations

import asyncio
import types

import pytest

from dicton.config import Config
from dicton.pipeline import Pipeline, State


class FakeStream:
    def __init__(self) -> None:
        self.stopped = False
        self.closed = False

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


class FakeListener:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class FakeLoopRunner:
    def __init__(self) -> None:
        self.client = object()
        self.submitted: list[object] = []
        self.closed = False
        self.calls: list[tuple[object, tuple[object, ...]]] = []

    def start(self) -> None:
        pass

    def submit(self, coro: object) -> object:
        self.submitted.append(coro)
        return object()

    def call(self, fn: object, *args: object) -> None:
        self.calls.append((fn, args))

    def close(self, *, timeout: float = 5.0) -> None:
        self.closed = True


def test_stop_closes_active_stream_listener_and_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    resumed: list[list[str]] = []
    monkeypatch.setattr(
        "dicton.pipeline.audio_session.resume_players",
        lambda players: resumed.append(list(players)),
    )

    pipe = Pipeline(Config())
    runner = FakeLoopRunner()
    stream = FakeStream()
    listener = FakeListener()
    pipe._runner = runner
    pipe._stream = stream
    pipe._listener = listener
    pipe._session = types.SimpleNamespace(chunks={}, started_at=0.0, paused_players=["spotify"])

    pipe.stop()

    assert pipe.stopped
    assert stream.stopped
    assert stream.closed
    assert pipe._stream is None
    assert listener.stopped
    assert runner.closed
    assert resumed == [["spotify"]]


def test_trigger_observes_begin_transition() -> None:
    pipe = Pipeline(Config())
    runner = FakeLoopRunner()
    pipe._runner = runner

    pipe._trigger()

    assert pipe._state is State.RECORDING
    assert len(runner.submitted) == 1
    submitted = runner.submitted[0]
    assert asyncio.iscoroutine(submitted)
    submitted.close()


async def test_begin_failure_returns_to_idle_and_resumes_players(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paused = ["spotify"]
    resumed: list[list[str]] = []
    monkeypatch.setattr("dicton.pipeline.audio_session.pause_active_players", lambda: paused)
    monkeypatch.setattr(
        "dicton.pipeline.audio_session.resume_players",
        lambda players: resumed.append(list(players)),
    )

    class BrokenInputStream:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("microphone failed")

    monkeypatch.setattr("dicton.pipeline.sd.InputStream", BrokenInputStream)
    monkeypatch.setattr("dicton.pipeline.stt.prewarm", lambda *args, **kwargs: asyncio.sleep(0))

    pipe = Pipeline(Config())
    pipe._runner = FakeLoopRunner()
    pipe._state = State.RECORDING

    with pytest.raises(RuntimeError, match="microphone failed"):
        await pipe._begin()

    assert pipe._session is None
    assert pipe._state is State.IDLE
    assert resumed == [["spotify"]]


async def test_end_failure_returns_to_idle_and_resumes_players(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resumed: list[list[str]] = []
    monkeypatch.setattr(
        "dicton.pipeline.audio_session.resume_players",
        lambda players: resumed.append(list(players)),
    )

    pipe = Pipeline(Config())
    pipe._runner = FakeLoopRunner()
    pipe._state = State.PROCESSING
    pipe._session = types.SimpleNamespace(
        chunks={},
        started_at=0.0,
        paused_players=["spotify"],
    )
    pipe._stream = FakeStream()

    async def broken_cleanup(*args: object, **kwargs: object) -> str:
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr("dicton.pipeline.cleanup_mod.cleanup", broken_cleanup)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        await pipe._end()

    assert pipe._session is None
    assert pipe._state is State.IDLE
    assert pipe._stream is None
    assert resumed == [["spotify"]]
