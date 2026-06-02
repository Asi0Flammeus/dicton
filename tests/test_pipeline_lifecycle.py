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
