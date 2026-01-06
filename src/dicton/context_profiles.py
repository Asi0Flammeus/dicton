"""Context Profiles System for Dicton

Provides context-aware configuration through profile matching.
Profiles define LLM preambles, typing speeds, and formatting options
based on the detected application context.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .context_detector import ContextInfo

logger = logging.getLogger(__name__)


# =============================================================================
# Data Classes
# =============================================================================


@dataclass
class ProfileMatch:
    """Matching criteria for a context profile.

    All specified criteria must match (AND logic).
    Empty/None fields are ignored (match anything).
    """

    wm_class: list[str] = field(default_factory=list)
    window_title_contains: list[str] = field(default_factory=list)
    file_extension: list[str] = field(default_factory=list)
    widget_role: list[str] = field(default_factory=list)
    url_contains: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileMatch":
        return cls(
            wm_class=data.get("wm_class", []),
            window_title_contains=data.get("window_title_contains", []),
            file_extension=data.get("file_extension", []),
            widget_role=data.get("widget_role", []),
            url_contains=data.get("url_contains", []),
        )


@dataclass
class ContextProfile:
    """A context profile with matching criteria and configuration.

    Attributes:
        name: Profile identifier
        match: Matching criteria for this profile
        llm_preamble: Text prepended to LLM prompts for context
        typing_speed: Speed preset ("fast", "normal", "slow") or custom float
        formatting: Output formatting style ("auto", "raw", "paragraphs", etc.)
        extends: Parent profile name for inheritance
        priority: Matching priority (higher = checked first)
    """

    name: str
    match: ProfileMatch = field(default_factory=ProfileMatch)
    llm_preamble: str = ""
    typing_speed: str = "normal"
    formatting: str = "auto"
    extends: str | None = None
    priority: int = 0

    @classmethod
    def from_dict(cls, name: str, data: dict) -> "ContextProfile":
        match_data = data.get("match", {})
        return cls(
            name=name,
            match=ProfileMatch.from_dict(match_data),
            llm_preamble=data.get("llm_preamble", ""),
            typing_speed=data.get("typing_speed", "normal"),
            formatting=data.get("formatting", "auto"),
            extends=data.get("extends"),
            priority=data.get("priority", 0),
        )


# =============================================================================
# Profile Manager
# =============================================================================


class ContextProfileManager:
    """Manages context profiles and matching logic.

    Loads profiles from:
    1. Default bundled profiles (src/dicton/default_contexts.json)
    2. User profiles (~/.config/dicton/contexts.json) - overrides defaults
    """

    # Typing speed presets (delay in seconds between characters)
    TYPING_SPEEDS = {
        "fast": 0.01,
        "normal": 0.02,
        "slow": 0.05,
    }

    def __init__(self):
        self._profiles: dict[str, ContextProfile] = {}
        self._typing_speeds: dict[str, float] = self.TYPING_SPEEDS.copy()
        self._loaded = False

    def load(self) -> None:
        """Load profiles from default and user config files."""
        if self._loaded:
            return

        # Load bundled defaults
        default_path = Path(__file__).parent / "default_contexts.json"
        if default_path.exists():
            self._load_from_file(default_path)

        # Load user overrides
        user_path = Path.home() / ".config" / "dicton" / "contexts.json"
        if user_path.exists():
            self._load_from_file(user_path)

        # Ensure default profile exists
        if "default" not in self._profiles:
            self._profiles["default"] = ContextProfile(name="default")

        self._loaded = True
        logger.debug(f"Loaded {len(self._profiles)} context profiles")

    def _load_from_file(self, path: Path) -> None:
        """Load profiles from a JSON file."""
        try:
            with open(path) as f:
                data = json.load(f)

            # Load profiles
            for name, profile_data in data.get("profiles", {}).items():
                self._profiles[name] = ContextProfile.from_dict(name, profile_data)

            # Load typing speed overrides
            for name, speed in data.get("typing_speeds", {}).items():
                self._typing_speeds[name] = float(speed)

            logger.debug(f"Loaded profiles from {path}")

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {path}: {e}")
        except Exception as e:
            logger.error(f"Failed to load profiles from {path}: {e}")

    def match_context(self, context: ContextInfo | None) -> ContextProfile:
        """Find the best matching profile for the given context.

        Profiles are checked in priority order. The first profile where
        all specified criteria match is returned.

        Args:
            context: The detected context information

        Returns:
            Matching profile, or default profile if no match
        """
        self.load()

        if context is None:
            return self._profiles["default"]

        # Sort by priority (descending)
        sorted_profiles = sorted(
            [p for p in self._profiles.values() if p.name != "default"],
            key=lambda p: p.priority,
            reverse=True,
        )

        for profile in sorted_profiles:
            if self._matches_profile(context, profile):
                logger.debug(f"Matched context to profile: {profile.name}")

                # Apply inheritance if specified
                if profile.extends:
                    return self._apply_inheritance(profile)

                return profile

        return self._profiles["default"]

    def _matches_profile(self, context: ContextInfo, profile: ContextProfile) -> bool:
        """Check if context matches all specified criteria in profile."""
        match = profile.match

        # Check wm_class (any match)
        if match.wm_class:
            if not context.window:
                return False
            app_name = context.window.app_name.lower()
            if not any(cls.lower() in app_name for cls in match.wm_class):
                return False

        # Check window_title_contains (any match)
        if match.window_title_contains:
            if not context.window:
                return False
            title = context.window.title.lower()
            if not any(s.lower() in title for s in match.window_title_contains):
                return False

        # Check widget_role (any match)
        if match.widget_role:
            if not context.widget:
                return False
            role = context.widget.role.lower()
            if not any(r.lower() == role for r in match.widget_role):
                return False

        # Check file_extension (from window title)
        if match.file_extension:
            if not context.window:
                return False
            title = context.window.title
            if not any(title.endswith(ext) for ext in match.file_extension):
                return False

        # Check url_contains (from window title, common in browsers)
        if match.url_contains:
            if not context.window:
                return False
            title = context.window.title.lower()
            if not any(url.lower() in title for url in match.url_contains):
                return False

        return True

    def _apply_inheritance(self, profile: ContextProfile) -> ContextProfile:
        """Apply inheritance from parent profile."""
        if not profile.extends or profile.extends not in self._profiles:
            return profile

        parent = self._profiles[profile.extends]

        # Create merged profile (child overrides parent)
        return ContextProfile(
            name=profile.name,
            match=profile.match,
            llm_preamble=profile.llm_preamble or parent.llm_preamble,
            typing_speed=profile.typing_speed if profile.typing_speed != "normal" else parent.typing_speed,
            formatting=profile.formatting if profile.formatting != "auto" else parent.formatting,
            extends=None,  # Don't chain inheritance
            priority=profile.priority,
        )

    def get_typing_delay(self, profile: ContextProfile) -> float:
        """Get typing delay in seconds for a profile.

        Args:
            profile: The context profile

        Returns:
            Delay between characters in seconds
        """
        speed = profile.typing_speed

        # Check if it's a preset
        if speed in self._typing_speeds:
            return self._typing_speeds[speed]

        # Try to parse as float (custom speed)
        try:
            return float(speed)
        except ValueError:
            return self._typing_speeds["normal"]

    def get_profile(self, name: str) -> ContextProfile | None:
        """Get a profile by name."""
        self.load()
        return self._profiles.get(name)

    def list_profiles(self) -> list[str]:
        """List all available profile names."""
        self.load()
        return list(self._profiles.keys())

    def reload(self) -> None:
        """Force reload profiles from disk."""
        self._profiles.clear()
        self._typing_speeds = self.TYPING_SPEEDS.copy()
        self._loaded = False
        self.load()


# =============================================================================
# Module-level Instance
# =============================================================================

_profile_manager: ContextProfileManager | None = None


def get_profile_manager() -> ContextProfileManager:
    """Get the global profile manager instance."""
    global _profile_manager
    if _profile_manager is None:
        _profile_manager = ContextProfileManager()
    return _profile_manager
