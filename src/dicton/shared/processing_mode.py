"""Backward-compat shim — canonical home is ``core.processing_mode``."""

from ..core.processing_mode import *  # noqa: F401,F403
from ..core.processing_mode import (  # noqa: F401
    ModeConfig,
    ProcessingMode,
    for_mode,
    get_mode_color,
    is_mode_enabled,
)
