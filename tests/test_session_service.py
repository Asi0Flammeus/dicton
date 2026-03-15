"""Regression tests for session-service concurrency."""

from __future__ import annotations

import threading
import time

from dicton.orchestration.session_service import SessionService
from dicton.shared.processing_mode import ProcessingMode


class _DummyController:
    def __init__(self):
        self.sessions: list[ProcessingMode] = []
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
        self.sessions.append(mode)
        time.sleep(0.05)
        return True, None


class _DummyMetrics:
    def end_session(self):
        return None


class _AppConfig:
    def __init__(self):
        self.debug = True


def test_concurrent_starts_only_launch_one_session():
    controller = _DummyController()
    service = SessionService(
        controller=controller,
        text_output=None,
        metrics=_DummyMetrics(),
        app_config=_AppConfig(),
        visualizer_factory=lambda: None,
    )

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
    assert controller.sessions == [ProcessingMode.BASIC]
    assert service.recording is False
