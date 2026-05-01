"""Backward-compat shim — canonical home is ``adapters.config.update_checker``."""

from ..adapters.config.update_checker import *  # noqa: F401,F403
from ..adapters.config.update_checker import (  # noqa: F401
    UpdateInfo,
    check_for_updates,
    check_for_updates_async,
    is_newer_version,
    parse_version,
    print_update_notification,
)
