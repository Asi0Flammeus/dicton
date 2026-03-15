"""Update checker for Dicton - check GitHub releases for new versions

This module provides a non-blocking update check that runs on startup
and notifies users when a new version is available.
"""

import json
import threading
from datetime import datetime, timedelta
from typing import NamedTuple
from urllib.error import URLError
from urllib.request import Request, urlopen

from .. import __version__
from .app_paths import get_update_cache_path
from .config import config

# GitHub repository info
GITHUB_OWNER = "Asi0Flammeus"
GITHUB_REPO = "dicton"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# Cache settings
CACHE_FILE = get_update_cache_path()
CHECK_INTERVAL_HOURS = 24  # Only check once per day


class UpdateInfo(NamedTuple):
    """Information about an available update"""

    current_version: str
    latest_version: str
    release_url: str
    release_notes: str
    published_at: str


def parse_version(version_str: str) -> tuple[int, ...]:
    """Parse version string into comparable tuple.

    Args:
        version_str: Version like "1.2.3" or "v1.2.3"

    Returns:
        Tuple of integers like (1, 2, 3)
    """
    # Remove 'v' prefix if present
    version_str = version_str.lstrip("v")

    # Remove any suffix like -alpha, -beta, etc.
    version_str = version_str.split("-")[0]

    try:
        parts = version_str.split(".")
        return tuple(int(p) for p in parts)
    except (ValueError, AttributeError):
        return (0, 0, 0)


def is_newer_version(current: str, latest: str) -> bool:
    """Check if latest version is newer than current.

    Args:
        current: Current installed version
        latest: Latest available version

    Returns:
        True if latest > current
    """
    return parse_version(latest) > parse_version(current)


def _load_cache() -> dict | None:
    """Load cached update check result."""
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_cache(data: dict) -> None:
    """Save update check result to cache."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def _should_check() -> bool:
    """Check if enough time has passed since last check."""
    cache = _load_cache()
    if cache is None:
        return True

    last_check = cache.get("last_check")
    if last_check is None:
        return True

    try:
        last_check_time = datetime.fromisoformat(last_check)
        elapsed = datetime.now() - last_check_time
        return elapsed > timedelta(hours=CHECK_INTERVAL_HOURS)
    except (ValueError, TypeError):
        return True


def check_for_updates(force: bool = False) -> UpdateInfo | None:
    """Check GitHub for a newer version.

    Args:
        force: If True, bypass the rate limit cache

    Returns:
        UpdateInfo if a newer version is available, None otherwise.
    """
    if not force and not _should_check():
        # Check if we have a cached "update available" result
        cache = _load_cache()
        if cache and cache.get("update_available"):
            latest = cache.get("latest_version", "")
            if is_newer_version(__version__, latest):
                return UpdateInfo(
                    current_version=__version__,
                    latest_version=latest,
                    release_url=cache.get("release_url", ""),
                    release_notes=cache.get("release_notes", ""),
                    published_at=cache.get("published_at", ""),
                )
        return None

    try:
        # Create request with User-Agent (required by GitHub API)
        request = Request(
            GITHUB_API_URL,
            headers={
                "User-Agent": f"Dicton/{__version__}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))

        latest_version = data.get("tag_name", "").lstrip("v")
        release_url = data.get("html_url", "")
        release_notes = data.get("body", "")[:500]  # Truncate long notes
        published_at = data.get("published_at", "")

        # Update cache
        cache_data = {
            "last_check": datetime.now().isoformat(),
            "latest_version": latest_version,
            "release_url": release_url,
            "release_notes": release_notes,
            "published_at": published_at,
            "update_available": is_newer_version(__version__, latest_version),
        }
        _save_cache(cache_data)

        if is_newer_version(__version__, latest_version):
            return UpdateInfo(
                current_version=__version__,
                latest_version=latest_version,
                release_url=release_url,
                release_notes=release_notes,
                published_at=published_at,
            )

    except (URLError, json.JSONDecodeError, OSError, TimeoutError) as e:
        if config.DEBUG:
            print(f"Update check failed: {e}")

    return None


def check_for_updates_async(callback=None) -> None:
    """Check for updates in a background thread.

    Args:
        callback: Optional function to call with UpdateInfo (or None) result.
    """

    def _check():
        result = check_for_updates()
        if callback:
            callback(result)
        elif result:
            print_update_notification(result)

    thread = threading.Thread(target=_check, daemon=True)
    thread.start()


def print_update_notification(update: UpdateInfo) -> None:
    """Print update notification to console."""
    print("\n" + "=" * 50)
    print(f"🆕 New version available: v{update.latest_version}")
    print(f"   Current version: v{update.current_version}")
    print(f"   Download: {update.release_url}")
    if update.release_notes:
        # Show first line of release notes
        first_line = update.release_notes.split("\n")[0].strip()
        if first_line:
            print(f"   Notes: {first_line[:60]}...")
    print("=" * 50 + "\n")
