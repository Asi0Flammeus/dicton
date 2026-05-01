"""Text processing and output adapters."""

from __future__ import annotations


class TextProcessorAdapter:
    """Adapter satisfying :class:`~dicton.core.ports.TextProcessor`."""

    def __init__(self, process_fn) -> None:
        self._process_fn = process_fn

    def process(
        self,
        text: str,
        mode,
        selected_text: str | None = None,
    ) -> str | None:
        return self._process_fn(text, mode, selected_text)


class TextOutputAdapter:
    """Adapter satisfying :class:`~dicton.core.ports.TextOutput`."""

    def __init__(self, output_fn) -> None:
        self._output_fn = output_fn

    def output(self, text: str, mode) -> None:
        self._output_fn(text, mode)
