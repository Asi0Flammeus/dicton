from __future__ import annotations

import types

from dicton import runtime
from dicton.config import Config


class _Lock:
    def close(self) -> None:
        pass


def test_visualizer_window_initializes_before_pipeline_hotkeys(monkeypatch) -> None:
    calls: list[str] = []

    class FakeVisualizer:
        def __init__(self) -> None:
            self.quit_requested = False

        def initialize(self) -> None:
            calls.append("visualizer.initialize")

        def run(self) -> None:
            calls.append("visualizer.run")
            self.quit_requested = True

    class FakePipeline:
        def __init__(self, cfg: Config, viz: FakeVisualizer | None) -> None:
            calls.append("pipeline.__init__")

        def start(self) -> None:
            calls.append("pipeline.start")

        def stop(self) -> None:
            calls.append("pipeline.stop")

    monkeypatch.setenv("DICTON_ENABLE_X11_VISUALIZER", "1")
    monkeypatch.setattr(runtime.x11, "init_threads", lambda: calls.append("x11.init_threads"))
    monkeypatch.setattr(runtime.singleton, "acquire", lambda: _Lock())
    monkeypatch.setitem(
        __import__("sys").modules,
        "dicton.visualizer",
        types.SimpleNamespace(Visualizer=FakeVisualizer),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "dicton.pipeline",
        types.SimpleNamespace(Pipeline=FakePipeline),
    )

    runtime.run(Config(visualizer=True))

    assert calls == [
        "x11.init_threads",
        "visualizer.initialize",
        "pipeline.__init__",
        "pipeline.start",
        "visualizer.run",
        "pipeline.stop",
    ]


def test_x11_visualizer_is_disabled_by_default_before_pipeline_starts(monkeypatch) -> None:
    calls: list[str] = []

    class FakeVisualizer:
        def __init__(self) -> None:
            calls.append("visualizer.__init__")

    class FakePipeline:
        def __init__(self, cfg: Config, viz: FakeVisualizer | None) -> None:
            calls.append(f"pipeline.__init__:viz={viz is not None}")
            self.stopped = True

        def start(self) -> None:
            calls.append("pipeline.start")

        def stop(self) -> None:
            calls.append("pipeline.stop")

    monkeypatch.setenv("DISPLAY", ":0")
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.delenv("DICTON_ENABLE_X11_VISUALIZER", raising=False)
    monkeypatch.setattr(runtime.x11, "init_threads", lambda: calls.append("x11.init_threads"))
    monkeypatch.setattr(runtime.singleton, "acquire", lambda: _Lock())
    monkeypatch.setitem(
        __import__("sys").modules,
        "dicton.visualizer",
        types.SimpleNamespace(Visualizer=FakeVisualizer),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "dicton.pipeline",
        types.SimpleNamespace(Pipeline=FakePipeline),
    )

    runtime.run(Config(visualizer=True))

    assert calls == [
        "x11.init_threads",
        "pipeline.__init__:viz=False",
        "pipeline.start",
        "pipeline.stop",
    ]
