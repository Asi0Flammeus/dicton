"""LLM adapter wrapping the existing llm_processor module."""

from __future__ import annotations

from .. import llm_processor


class LLMProcessorAdapter:
    def is_available(self) -> bool:
        return llm_processor.is_available()

    def act_on_text(self, selected_text: str, instruction: str, context=None):
        return llm_processor.act_on_text(selected_text, instruction, context=context)

    def reformulate(self, text: str, context=None):
        return llm_processor.reformulate(text, context=context)

    def translate(self, text: str, target_language: str = "English", context=None):
        return llm_processor.translate(text, target_language, context=context)
