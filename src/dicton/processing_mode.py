"""Processing modes for Dicton - defines different transcription/processing pipelines

Each mode has a dedicated ring color (Flexoki palette) for visual feedback.
See CLAUDE.md for the full color convention.
"""

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
    ACT_ON_TEXT = auto()  # LLM manipulation of selected text, Magenta ring


# Flexoki color mapping for each mode
MODE_COLORS: dict[ProcessingMode, str] = {
    ProcessingMode.BASIC: "orange",
    ProcessingMode.TRANSLATION: "green",
    ProcessingMode.REFORMULATION: "purple",
    ProcessingMode.TRANSLATE_REFORMAT: "cyan",
    ProcessingMode.RAW: "yellow",
    ProcessingMode.ACT_ON_TEXT: "magenta",
}


@dataclass
class ModeConfig:
    """Configuration for a processing mode"""

    mode: ProcessingMode
    color: str
    requires_selection: bool = False  # True for ACT_ON_TEXT
    requires_llm: bool = False  # True for reformulation, translation, act_on_text
    description: str = ""

    @classmethod
    def for_mode(cls, mode: ProcessingMode) -> "ModeConfig":
        """Get configuration for a specific mode"""
        configs = {
            ProcessingMode.BASIC: cls(
                mode=ProcessingMode.BASIC,
                color="orange",
                requires_selection=False,
                requires_llm=False,
                description="Basic speech-to-text transcription",
            ),
            ProcessingMode.TRANSLATION: cls(
                mode=ProcessingMode.TRANSLATION,
                color="green",
                requires_selection=False,
                requires_llm=True,
                description="Transcribe and translate to English",
            ),
            ProcessingMode.REFORMULATION: cls(
                mode=ProcessingMode.REFORMULATION,
                color="purple",
                requires_selection=False,
                requires_llm=True,
                description="Transcribe with light reformulation",
            ),
            ProcessingMode.TRANSLATE_REFORMAT: cls(
                mode=ProcessingMode.TRANSLATE_REFORMAT,
                color="cyan",
                requires_selection=False,
                requires_llm=True,
                description="Translate and reformat text",
            ),
            ProcessingMode.RAW: cls(
                mode=ProcessingMode.RAW,
                color="yellow",
                requires_selection=False,
                requires_llm=False,
                description="Raw STT output without processing",
            ),
            ProcessingMode.ACT_ON_TEXT: cls(
                mode=ProcessingMode.ACT_ON_TEXT,
                color="magenta",
                requires_selection=True,
                requires_llm=True,
                description="Apply voice instruction to selected text",
            ),
        }
        return configs.get(mode, configs[ProcessingMode.BASIC])


def get_mode_color(mode: ProcessingMode) -> str:
    """Get the Flexoki color name for a processing mode"""
    return MODE_COLORS.get(mode, "orange")
