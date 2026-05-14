"""Pause/resume MPRIS-aware players while a dictation is recording.

Linux only. Uses ``playerctl`` to talk to the MPRIS D-Bus interface, which
covers Spotify, YouTube via Firefox/Chromium, VLC, mpv, and most other
desktop media apps. Players that were already paused/stopped are left
alone; we only pause the ones that were actively *Playing* when the
recording started, then resume them at the end.

No system-wide mute fallback on purpose: if dicton crashes mid-record we
don't want to leave the user's audio muted with no obvious way to
recover.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys

log = logging.getLogger("dicton")


def pause_active_players() -> list[str]:
    """Pause every MPRIS player currently ``Playing``. Returns the names so
    they can be resumed in the same order at the end of the recording.
    Returns an empty list if playerctl isn't installed or no player is
    playing — both are normal."""
    if sys.platform != "linux" or not shutil.which("playerctl"):
        return []
    paused: list[str] = []
    try:
        listing = _run(["playerctl", "-l"])
        if not listing or not listing.stdout.strip():
            return []
        for line in listing.stdout.splitlines():
            name = line.strip()
            if not name:
                continue
            status = _run(["playerctl", "-p", name, "status"])
            if status and status.stdout.strip().lower() == "playing":
                _run(["playerctl", "-p", name, "pause"])
                paused.append(name)
        if paused:
            log.info("paused %d player(s): %s", len(paused), ", ".join(paused))
    except Exception as exc:  # noqa: BLE001
        log.warning("audio_session.pause_active_players failed: %s", exc)
    return paused


def resume_players(paused: list[str]) -> None:
    """Resume each previously-paused player. Best-effort — a player that
    was closed in the meantime is skipped silently."""
    if not paused:
        return
    if sys.platform != "linux" or not shutil.which("playerctl"):
        return
    for name in paused:
        _run(["playerctl", "-p", name, "play"])


def _run(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=1.5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
