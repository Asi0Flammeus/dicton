from __future__ import annotations

import logging
import types

from dicton import cli, config


def test_crash_diagnostics_enable_faulthandler_with_persistent_file(tmp_path, monkeypatch) -> None:
    crash_log = tmp_path / "dicton-crash.log"
    calls: list[dict[str, object]] = []

    def fake_enable(**kwargs: object) -> None:
        calls.append(kwargs)

    registers: list[dict[str, object]] = []

    def fake_register(signalnum: object, **kwargs: object) -> None:
        registers.append({"signalnum": signalnum, **kwargs})

    monkeypatch.setattr(config, "CRASH_LOG_PATH", crash_log)
    monkeypatch.setattr(cli.faulthandler, "enable", fake_enable)
    monkeypatch.setattr(cli.faulthandler, "register", fake_register)
    monkeypatch.setattr(cli, "_crash_log_file", None)

    cli._setup_crash_diagnostics()

    assert crash_log.exists()
    assert len(calls) == 1
    assert calls[0]["all_threads"] is True
    assert calls[0]["c_stack"] is True
    assert registers == [
        {"signalnum": cli.signal.SIGUSR1, "file": cli._crash_log_file, "all_threads": True}
    ]
    assert cli._crash_log_file is not None
    assert not cli._crash_log_file.closed
    cli._crash_log_file.close()


def test_crash_diagnostics_falls_back_on_python_without_c_stack(tmp_path, monkeypatch) -> None:
    crash_log = tmp_path / "dicton-crash.log"
    calls: list[dict[str, object]] = []

    def fake_enable(**kwargs: object) -> None:
        calls.append(kwargs)
        if "c_stack" in kwargs:
            raise TypeError("no c_stack")

    registers: list[dict[str, object]] = []

    def fake_register(signalnum: object, **kwargs: object) -> None:
        registers.append({"signalnum": signalnum, **kwargs})

    monkeypatch.setattr(config, "CRASH_LOG_PATH", crash_log)
    monkeypatch.setattr(cli.faulthandler, "enable", fake_enable)
    monkeypatch.setattr(cli.faulthandler, "register", fake_register)
    monkeypatch.setattr(cli, "_crash_log_file", None)

    cli._setup_crash_diagnostics()

    assert calls == [
        {"file": cli._crash_log_file, "all_threads": True, "c_stack": True},
        {"file": cli._crash_log_file, "all_threads": True},
    ]
    assert registers == [
        {"signalnum": cli.signal.SIGUSR1, "file": cli._crash_log_file, "all_threads": True}
    ]
    cli._crash_log_file.close()


def test_visualizer_visibility_breadcrumbs_are_emitted(caplog) -> None:
    from dicton import visualizer

    class FakeScreen:
        def fill(self, _color: tuple[int, int, int]) -> None:
            pass

    class FakeDisplay:
        def flip(self) -> None:
            pass

    class FakeWindow:
        opacity = 1.0

        def hide(self) -> None:
            pass

    class WindowFacade:
        @staticmethod
        def from_display_module() -> FakeWindow:
            return FakeWindow()

    pygame = types.SimpleNamespace(
        display=FakeDisplay(),
        _sdl2=types.SimpleNamespace(video=types.SimpleNamespace(Window=WindowFacade)),
    )

    with caplog.at_level(logging.INFO, logger="dicton"):
        visualizer.Visualizer()._set_visible(pygame, FakeScreen(), False)

    messages = [record.getMessage() for record in caplog.records]
    assert "visualizer set_visible begin: visible=False" in messages
    assert "visualizer SDL hide complete" in messages
    assert "visualizer set_visible end: visible=False" in messages
