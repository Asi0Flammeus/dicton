"""Behavioral tests for the Act on Text processing pipeline."""

from contextlib import nullcontext

import dicton.llm_processor as llm_processor
import dicton.main as main_module
from dicton.main import Dicton
from dicton.processing_mode import ProcessingMode


class RecordingKeyboard:
    def __init__(self, replacement_succeeds=True):
        self.replacement_succeeds = replacement_succeeds
        self.replacements = []
        self.insertions = []

    def replace_selection_with_text(self, text):
        self.replacements.append(text)
        return self.replacement_succeeds

    def insert_text(self, text, typing_delay_ms=50):
        self.insertions.append((text, typing_delay_ms))


class FakeTracker:
    def start_session(self):
        return None

    def measure(self, *args, **kwargs):
        return nullcontext()

    def end_session(self):
        return None


class FakeRecognizer:
    def __init__(self, instruction="make it concise"):
        self.instruction = instruction

    def record(self):
        return b"recorded audio"

    def transcribe(self, audio):
        return self.instruction


def bare_app():
    app = Dicton.__new__(Dicton)
    app.keyboard = RecordingKeyboard()
    app.recording = False
    app.record_thread = None
    app._selected_text = None
    app._current_context = None
    app._visualizer = None
    return app


def test_act_on_text_builds_prompt_and_handles_long_selection(monkeypatch):
    selected = "Paragraph one.\n\n" + ("Long selected content. " * 1000)
    captured = {}

    def call_llm(prompt):
        captured["prompt"] = prompt
        return "Condensed result"

    monkeypatch.setattr(llm_processor, "_call_llm_with_fallback", call_llm)

    result = llm_processor.act_on_text(selected, "make it concise")

    assert result == "Condensed result"
    assert selected in captured["prompt"]
    assert "make it concise" in captured["prompt"]
    assert "Return ONLY the modified text" in captured["prompt"]


def test_act_on_text_returns_none_when_llm_fails(monkeypatch):
    monkeypatch.setattr(llm_processor, "_call_llm_with_fallback", lambda prompt: None)

    assert llm_processor.act_on_text("Original text", "make it formal") is None


def test_successful_capture_process_and_apply(monkeypatch):
    app = bare_app()
    notifications = []
    selection_calls = []

    def get_selection():
        selection_calls.append(True)
        return "Original selected text"

    monkeypatch.setattr("dicton.selection_handler.get_primary_selection", get_selection)
    monkeypatch.setattr(main_module, "notify", lambda title, body: notifications.append((title, body)))
    monkeypatch.setattr(llm_processor, "is_available", lambda: True)
    monkeypatch.setattr(
        llm_processor,
        "act_on_text",
        lambda selected, instruction, context=None: "Rewritten text",
    )

    selected = app._capture_selection_for_act_on_text()
    result = app._process_text("make it clearer", ProcessingMode.ACT_ON_TEXT, selected)
    applied = app._output_result(result, ProcessingMode.ACT_ON_TEXT, selected is not None)

    assert selection_calls == [True]
    assert applied is True
    assert app.keyboard.replacements == ["Rewritten text"]
    assert app.keyboard.insertions == []
    assert notifications[-1] == ("✓ Text Replaced", "Rewritten text")


def test_no_selection_does_not_start_recording(monkeypatch):
    app = bare_app()
    notifications = []
    monkeypatch.setattr(main_module.config, "CONTEXT_ENABLED", False)
    monkeypatch.setattr("dicton.selection_handler.get_primary_selection", lambda: None)
    monkeypatch.setattr(main_module, "notify", lambda title, body: notifications.append((title, body)))

    app._on_start_recording(ProcessingMode.ACT_ON_TEXT)

    assert app.recording is False
    assert app.record_thread is None
    assert notifications[0][0] == "⚠ No Selection"


def test_missing_llm_does_not_replace_selection_with_instruction(monkeypatch):
    app = bare_app()
    notifications = []
    monkeypatch.setattr(llm_processor, "is_available", lambda: False)
    monkeypatch.setattr(main_module, "notify", lambda title, body: notifications.append((title, body)))

    result = app._process_text(
        "make it formal",
        ProcessingMode.ACT_ON_TEXT,
        "Original selected text",
    )

    assert result is None
    assert app.keyboard.replacements == []
    assert notifications[-1][0] == "⚠ LLM Not Available"


def test_llm_failure_in_recording_pipeline_leaves_selection_unchanged(monkeypatch):
    app = bare_app()
    app.recording = True
    app._current_mode = ProcessingMode.ACT_ON_TEXT
    app._selected_text = "Original selected text"
    app.recognizer = FakeRecognizer()
    notifications = []

    monkeypatch.setattr(main_module, "get_latency_tracker", lambda: FakeTracker())
    monkeypatch.setattr(main_module.config, "VISUALIZER_BACKEND", "pygame")
    monkeypatch.setattr(main_module.config, "DEBUG", False)
    monkeypatch.setattr(main_module, "notify", lambda title, body: notifications.append((title, body)))
    monkeypatch.setattr(llm_processor, "is_available", lambda: True)
    monkeypatch.setattr(llm_processor, "act_on_text", lambda *args, **kwargs: None)
    monkeypatch.setattr("dicton.visualizer.get_visualizer", lambda: None)

    app._record_and_transcribe()

    assert app.keyboard.replacements == []
    assert app.keyboard.insertions == []
    assert ("⚠ Processing failed", "Check logs") in notifications
    assert app.recording is False


def test_replacement_failure_is_reported(monkeypatch):
    app = bare_app()
    app.keyboard = RecordingKeyboard(replacement_succeeds=False)
    notifications = []
    monkeypatch.setattr(main_module, "notify", lambda title, body: notifications.append((title, body)))

    assert app._output_result("Result", ProcessingMode.ACT_ON_TEXT, True) is False
    assert notifications[-1] == (
        "⚠ Replacement Failed",
        "Selected text was left unchanged",
    )


def test_replacement_keeps_transformed_text_in_clipboard(monkeypatch):
    import dicton.keyboard_handler as keyboard_handler
    import dicton.selection_handler as selection_handler

    clipboard = {"text": "previous clipboard"}
    controller_events = []

    class Controller:
        def press(self, key):
            controller_events.append(("press", key))

        def release(self, key):
            controller_events.append(("release", key))

    handler = keyboard_handler.KeyboardHandler.__new__(keyboard_handler.KeyboardHandler)
    handler._keyboard_controller = Controller()
    handler._verify_clipboard = lambda expected, getter: getter() == expected

    monkeypatch.setattr(keyboard_handler, "IS_LINUX", True)
    monkeypatch.setattr(keyboard_handler, "IS_WINDOWS", False)
    monkeypatch.setattr(selection_handler, "get_clipboard", lambda: clipboard["text"])
    monkeypatch.setattr(
        selection_handler,
        "set_clipboard",
        lambda text: clipboard.__setitem__("text", text) is None,
    )

    assert handler.replace_selection_with_text("Transformed text\n") is True
    assert clipboard["text"] == "Transformed text\n"
    assert controller_events[-2:] == [("release", "v"), ("release", keyboard_handler.Key.ctrl)]


def test_duplicate_secondary_hotkey_keeps_first_assignment(monkeypatch, capsys):
    from dicton.fn_key_handler import FnKeyHandler, SECONDARY_HOTKEY_MAP
    from dicton.fn_key_handler import config as hotkey_config

    monkeypatch.setattr(hotkey_config, "SECONDARY_HOTKEY", "f1")
    monkeypatch.setattr(hotkey_config, "SECONDARY_HOTKEY_TRANSLATION", "none")
    monkeypatch.setattr(hotkey_config, "SECONDARY_HOTKEY_ACT_ON_TEXT", "f1")

    handler = FnKeyHandler()

    assert handler._secondary_hotkeys[SECONDARY_HOTKEY_MAP["f1"]] == ProcessingMode.BASIC
    assert "assigned to both BASIC and ACT_ON_TEXT" in capsys.readouterr().out
