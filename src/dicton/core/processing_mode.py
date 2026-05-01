"""Processing modes for Dicton - defines different transcription/processing pipelines

Each mode has a dedicated ring color (Flexoki palette) for visual feedback.
See CLAUDE.md for the full color convention.
"""

import os
from dataclasses import dataclass
from enum import Enum, auto


class ProcessingMode(Enum):
    """Processing modes for dictation

    Each mode corresponds to a specific ring color and processing pipeline.
    """

    BASIC = auto()  # Basic transcription, Orange ring
    TRANSLATION = auto()  # Transcribe + translate to EN, Green ring
    REFORMULATION = auto()  # Transcribe + reformat, Purple ring
    TRANSLATE_REFORMAT = auto()  # Translate + reformat, Cyan ring
    RAW = auto()  # No processing (raw STT output), Yellow ring


# Flexoki color mapping for each mode
MODE_COLORS: dict[ProcessingMode, str] = {
    ProcessingMode.BASIC: "orange",
    ProcessingMode.TRANSLATION: "green",
    ProcessingMode.REFORMULATION: "purple",
    ProcessingMode.TRANSLATE_REFORMAT: "cyan",
    ProcessingMode.RAW: "yellow",
}


@dataclass
class ModeConfig:
    """Configuration for a processing mode"""

    mode: ProcessingMode
    color: str
    requires_llm: bool = False
    description: str = ""

    @classmethod
    def for_mode(cls, mode: ProcessingMode) -> "ModeConfig":
        """Get configuration for a specific mode"""
        configs = {
            ProcessingMode.BASIC: cls(
                mode=ProcessingMode.BASIC,
                color="orange",
                requires_llm=False,
                description="Basic speech-to-text transcription",
            ),
            ProcessingMode.TRANSLATION: cls(
                mode=ProcessingMode.TRANSLATION,
                color="green",
                requires_llm=True,
                description="Transcribe and translate to English",
            ),
            ProcessingMode.REFORMULATION: cls(
                mode=ProcessingMode.REFORMULATION,
                color="purple",
                requires_llm=True,
                description="Transcribe with light reformulation",
            ),
            ProcessingMode.TRANSLATE_REFORMAT: cls(
                mode=ProcessingMode.TRANSLATE_REFORMAT,
                color="cyan",
                requires_llm=True,
                description="Translate and reformat text",
            ),
            ProcessingMode.RAW: cls(
                mode=ProcessingMode.RAW,
                color="yellow",
                requires_llm=False,
                description="Raw STT output without processing",
            ),
        }
        return configs.get(mode, configs[ProcessingMode.BASIC])


def get_mode_color(mode: ProcessingMode) -> str:
    """Get the Flexoki color name for a processing mode"""
    return MODE_COLORS.get(mode, "orange")


def advanced_modes_enabled() -> bool:
    """Return whether advanced processing modes are exposed to the user."""
    return os.getenv("ENABLE_ADVANCED_MODES", "false").lower() == "true"


def is_mode_enabled(mode: ProcessingMode) -> bool:
    """Return whether a processing mode is user-accessible."""
    if mode in {ProcessingMode.BASIC, ProcessingMode.TRANSLATION}:
        return True
    return advanced_modes_enabled()


# Convenience alias kept for backward compatibility with ModeConfig.for_mode
for_mode = ModeConfig.for_mode
