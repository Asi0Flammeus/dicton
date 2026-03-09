"""Regression tests for session-service concurrency."""

from __future__ import annotations

import sys
import threading
import time
import types

from dicton.application.session_service import SessionService
from dicton.processing_mode import ProcessingMode


class _DummyController:
    def __init__(self):
        self.sessions: list[tuple[ProcessingMode, object | None]] = []
        self.stop_calls = 0
        self.cancel_calls = 0

        class _State:
            def add_observer(self, callback) -> None:
                return None

        self._state = _State()

    def stop(self) -> None:
        self.stop_calls += 1

    def cancel(self) -> None:
        self.cancel_calls += 1

    def run_session(self, mode, session, mode_names, pre_output=None):
        self.sessions.append((mode, session.context))
        time.sleep(0.05)
        return True, None


class _DummyMetrics:
    def end_session(self):
        return None


class _AppConfig:
    def __init__(self, context_enabled: bool):
        self.context_enabled = context_enabled
        self.context_debug = False
        self.debug = True


def test_concurrent_starts_only_launch_one_session(monkeypatch):
    context_module = types.ModuleType("dicton.context_detector")

    class _Detector:
        def get_context(self):
            time.sleep(0.05)
            return "ctx"

    context_module.get_context_detector = lambda: _Detector()
    monkeypatch.setitem(sys.modules, "dicton.context_detector", context_module)

    controller = _DummyController()
    service = SessionService(
        controller=controller,
        keyboard=None,
        metrics=_DummyMetrics(),
        app_config=_AppConfig(context_enabled=True),
    )
    monkeypatch.setattr(service, "_load_visualizer", lambda: None)

    threads = [
        threading.Thread(target=service.start_recording, args=(ProcessingMode.BASIC,)),
        threading.Thread(target=service.start_recording, args=(ProcessingMode.BASIC,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    record_thread = service._record_thread
    assert record_thread is not None
    record_thread.join(timeout=1.0)

    assert len(controller.sessions) == 1
    assert controller.sessions == [(ProcessingMode.BASIC, "ctx")]
    assert service.recording is False
