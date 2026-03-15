"""Text processing and output adapters."""

from __future__ import annotations


class TextProcessorAdapter:
    def __init__(self, process_fn):
        self._process_fn = process_fn

    def process(self, text: str, mode, selected_text=None):
        return self._process_fn(text, mode, selected_text)


class TextOutputAdapter:
    def __init__(self, output_fn):
        self._output_fn = output_fn

    def output(self, text: str, mode, replace_selection: bool) -> None:
        self._output_fn(text, mode, replace_selection)
