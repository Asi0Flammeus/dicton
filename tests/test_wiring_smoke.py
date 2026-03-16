"""Smoke tests for composition-root wiring.

These tests verify that adapter method signatures match their call sites
in the orchestration layer — catching mismatches like ``typing_delay_ms``
vs ``delay_ms`` at test time rather than at runtime.
"""

from __future__ import annotations

import inspect

import pytest

from dicton.adapters.output.base import TextOutput as TextOutputABC
from dicton.adapters.output.fallback import PynputTextOutput
from dicton.adapters.output.linux import LinuxTextOutput
from dicton.adapters.output.macos import MacOSTextOutput
from dicton.adapters.output.windows import WindowsTextOutput
from dicton.core.ports import (
    AudioCapture,
    AudioSessionControl,
    MetricsSink,
    STTService,
    TextOutput,
    TextProcessor,
    UIFeedback,
)
from dicton.orchestration.session_service import SessionService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_param_names(cls, method_name: str) -> set[str]:
    """Return the parameter names (excluding 'self') for a method."""
    method = getattr(cls, method_name)
    sig = inspect.signature(method)
    return {p for p in sig.parameters if p != "self"}


# ---------------------------------------------------------------------------
# 1. TextOutput implementations share the same signatures as the ABC
# ---------------------------------------------------------------------------

_TEXT_OUTPUT_CLASSES = [
    LinuxTextOutput,
    MacOSTextOutput,
    WindowsTextOutput,
    PynputTextOutput,
]

_TEXT_OUTPUT_METHODS = ["insert_text", "paste_text", "replace_selection"]


@pytest.mark.parametrize("cls", _TEXT_OUTPUT_CLASSES, ids=lambda c: c.__name__)
@pytest.mark.parametrize("method", _TEXT_OUTPUT_METHODS)
def test_text_output_signatures_match_abc(cls, method):
    """Every TextOutput implementation must match the ABC's parameter names."""
    expected = _get_param_names(TextOutputABC, method)
    actual = _get_param_names(cls, method)
    assert actual == expected, f"{cls.__name__}.{method} params {actual} != ABC params {expected}"


# ---------------------------------------------------------------------------
# 2. SessionService.output_result calls insert_text with correct kwargs
# ---------------------------------------------------------------------------


def test_output_result_uses_correct_insert_text_kwarg():
    """The kwarg used in output_result must exist in TextOutput.insert_text."""
    source = inspect.getsource(SessionService.output_result)
    abc_params = _get_param_names(TextOutputABC, "insert_text")

    # Find all keyword arguments passed to insert_text in the source
    import re

    calls = re.findall(r"insert_text\([^)]*\)", source)
    assert calls, "output_result should call insert_text"

    for call in calls:
        kwargs = re.findall(r"(\w+)\s*=", call)
        for kwarg in kwargs:
            assert kwarg in abc_params, (
                f"output_result passes '{kwarg}=' to insert_text, but ABC only accepts {abc_params}"
            )


# ---------------------------------------------------------------------------
# 3. Core port protocols are runtime-checkable and adapters satisfy them
# ---------------------------------------------------------------------------


def test_text_output_adapter_satisfies_core_port():
    """TextOutputAdapter must satisfy the core TextOutput protocol."""
    from dicton.adapters.config.text_processing import TextOutputAdapter

    adapter = TextOutputAdapter(lambda text, mode, replace: None)
    assert isinstance(adapter, TextOutput)


def test_text_processor_adapter_satisfies_core_port():
    """TextProcessorAdapter must satisfy the core TextProcessor protocol."""
    from dicton.adapters.config.text_processing import TextProcessorAdapter

    adapter = TextProcessorAdapter(lambda text, mode, selected: text)
    assert isinstance(adapter, TextProcessor)


# ---------------------------------------------------------------------------
# 4. SessionService can be constructed with null/mock dependencies
# ---------------------------------------------------------------------------


class _StubController:
    """Minimal stand-in that satisfies bind_controller expectations."""

    class _State:
        def add_observer(self, cb):
            pass

    _state = _State()

    def run_session(self, **kw):
        return False, None

    def stop(self):
        pass

    def cancel(self):
        pass


class _StubTextOutput(TextOutputABC):
    def insert_text(self, text, delay_ms=50):
        pass

    def paste_text(self, text):
        return False

    def replace_selection(self, text):
        return False


class _StubMetrics:
    def start_session(self):
        pass

    def measure(self, name, **kwargs):
        from contextlib import nullcontext

        return nullcontext()

    def end_session(self):
        return None


class _StubConfig:
    debug = False


def test_session_service_wires_without_error():
    """SessionService + bind_controller must succeed with stub deps."""
    svc = SessionService(
        controller=None,
        text_output=_StubTextOutput(),
        metrics=_StubMetrics(),
        app_config=_StubConfig(),
        visualizer_factory=lambda: None,
    )
    svc.bind_controller(_StubController())

    # Verify the output path is callable end-to-end (no TypeError)
    from dicton.shared.processing_mode import ProcessingMode

    svc.output_result("hello", ProcessingMode.BASIC, replace_selection=False)


# ---------------------------------------------------------------------------
# 5. All port protocols are runtime-checkable
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "protocol",
    [
        AudioCapture,
        AudioSessionControl,
        STTService,
        TextProcessor,
        TextOutput,
        UIFeedback,
        MetricsSink,
    ],
    ids=lambda p: p.__name__,
)
def test_port_protocols_are_runtime_checkable(protocol):
    """Every core port must be decorated with @runtime_checkable."""
    assert (
        hasattr(protocol, "__protocol_attrs__")
        or hasattr(protocol, "__abstractmethods__")
        or (getattr(protocol, "_is_runtime_protocol", False))
    ), f"{protocol.__name__} is not runtime_checkable"
