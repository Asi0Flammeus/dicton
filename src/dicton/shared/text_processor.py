"""Backward-compat shim — canonical home is ``adapters.text.processor``."""

from ..adapters.text.processor import *  # noqa: F401,F403
from ..adapters.text.processor import (  # noqa: F401
    TextProcessor,
    filter_filler_words,
    get_text_processor,
)
