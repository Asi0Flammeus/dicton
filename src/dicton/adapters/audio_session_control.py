"""Audio session control adapter (mute/pause during recording)."""

from __future__ import annotations

import shutil
import subprocess

from ..config import config
from ..platform_utils import IS_LINUX


class AudioSessionControlAdapter:
    def __init__(self):
        self._active = False
        self._paused_players: list[str] = []
        self._sink_muted_before: bool | None = None
        self._source_muted_before: bool | None = None

    def start_recording(self) -> None:
        if self._active:
            return
        self._active = True

        if not IS_LINUX:
            return

        if config.MUTE_PLAYBACK_ON_RECORDING:
            self._apply_playback_control()

        if config.MUTE_MIC_ON_RECORDING:
            self._apply_source_mute()

    def stop_recording(self) -> None:
        if not self._active:
            return

        if IS_LINUX:
            if config.MUTE_MIC_ON_RECORDING:
                self._restore_source_mute()
            if config.MUTE_PLAYBACK_ON_RECORDING:
                self._restore_playback_control()

        self._active = False

    def cancel_recording(self) -> None:
        self.stop_recording()

    def _apply_playback_control(self) -> None:
        strategy = _normalize_strategy(config.PLAYBACK_MUTE_STRATEGY)
        backend = _normalize_backend(config.MUTE_BACKEND)

        paused = []
        if strategy in ("auto", "pause"):
            if backend in ("auto", "playerctl"):
                paused = self._pause_players()
                if paused:
                    self._paused_players = paused
                    if strategy == "pause":
                        return
            elif strategy == "pause":
                return

        if strategy in ("auto", "mute"):
            self._mute_sink(backend)

    def _restore_playback_control(self) -> None:
        self._resume_players()
        self._unmute_sink()

    def _pause_players(self) -> list[str]:
        if not _has_cmd("playerctl"):
            return []

        players = _run(["playerctl", "-l"])
        if not players or not players.stdout.strip():
            return []

        paused = []
        for player in players.stdout.splitlines():
            status = _run(["playerctl", "-p", player, "status"])
            if status and status.stdout.strip().lower() == "playing":
                _run(["playerctl", "-p", player, "pause"])
                paused.append(player)

        return paused

    def _resume_players(self) -> None:
        if not self._paused_players:
            return
        for player in self._paused_players:
            _run(["playerctl", "-p", player, "play"])
        self._paused_players = []

    def _mute_sink(self, backend: str) -> None:
        if backend in ("auto", "pipewire") and _has_cmd("wpctl"):
            self._sink_muted_before = _get_wpctl_mute("@DEFAULT_AUDIO_SINK@")
            if self._sink_muted_before is False:
                _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "1"])
            return

        if backend in ("auto", "pulseaudio") and _has_cmd("pactl"):
            self._sink_muted_before = _get_pactl_mute("sink")
            if self._sink_muted_before is False:
                _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"])

    def _unmute_sink(self) -> None:
        if self._sink_muted_before is None:
            return

        if _has_cmd("wpctl"):
            if self._sink_muted_before is False:
                _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "0"])
        elif _has_cmd("pactl"):
            if self._sink_muted_before is False:
                _run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"])

        self._sink_muted_before = None

    def _apply_source_mute(self) -> None:
        backend = _normalize_backend(config.MUTE_BACKEND)
        if backend in ("auto", "pipewire") and _has_cmd("wpctl"):
            self._source_muted_before = _get_wpctl_mute("@DEFAULT_AUDIO_SOURCE@")
            if self._source_muted_before is False:
                _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "1"])
            return

        if backend in ("auto", "pulseaudio") and _has_cmd("pactl"):
            self._source_muted_before = _get_pactl_mute("source")
            if self._source_muted_before is False:
                _run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1"])

    def _restore_source_mute(self) -> None:
        if self._source_muted_before is None:
            return

        if _has_cmd("wpctl"):
            if self._source_muted_before is False:
                _run(["wpctl", "set-mute", "@DEFAULT_AUDIO_SOURCE@", "0"])
        elif _has_cmd("pactl"):
            if self._source_muted_before is False:
                _run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"])

        self._source_muted_before = None


def _has_cmd(name: str) -> bool:
    return shutil.which(name) is not None


def _run(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=1.5)
    except Exception:
        return None


def _get_wpctl_mute(target: str) -> bool | None:
    result = _run(["wpctl", "get-volume", target])
    if not result or not result.stdout:
        return None
    return "[MUTED]" in result.stdout


def _get_pactl_mute(target: str) -> bool | None:
    if target == "sink":
        result = _run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
    else:
        result = _run(["pactl", "get-source-mute", "@DEFAULT_SOURCE@"])
    if not result or not result.stdout:
        return None
    return "yes" in result.stdout.lower()


def _normalize_backend(value: str) -> str:
    if value in ("auto", "playerctl", "pipewire", "pulseaudio"):
        return value
    return "auto"


def _normalize_strategy(value: str) -> str:
    if value in ("auto", "pause", "mute"):
        return value
    return "auto"
