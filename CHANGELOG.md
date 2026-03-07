# Changelog

All notable changes to Dicton will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- Simplified the default product surface to direct transcription plus translation to English.
- Hid advanced modes behind `ENABLE_ADVANCED_MODES=true` instead of exposing them by default.
- Made basic mode plain transcription instead of automatic reformulation.
- Made tests independent from user-level `~/.config/dicton/.env`.
- Updated README and example configuration to match the simplified defaults.
- Fixed stale Windows/Linux launcher scripts and aligned installers with `pyproject.toml`.
- Made the package version single-source and corrected GitHub/update metadata.
- Started a Windows PyInstaller packaging path and moved user config/data handling toward platform-native directories.
- Added a Linux release package path and a tag-based GitHub release workflow that publishes Windows, Linux, and Python distribution assets.

## [1.1.1]

### Added

- Mistral Voxtral STT provider support with fallback integration.
- Core controller/state-machine orchestration for dictation sessions.
- Playback mute / pause support during recording.

## [1.0.0] - 2024-12-21

### Added

- **ElevenLabs Speech-to-Text Integration**
  - Real-time transcription using ElevenLabs Scribe API
  - Automatic language detection
  - High-quality transcription with noise filtering

- **Cross-Platform Support**
  - Linux (X11/Wayland) with xdotool text insertion
  - Windows with pyautogui fallback
  - macOS support via pynput

- **Audio Visualizers**
  - Pygame-based circular donut visualizer (default)
  - VisPy-based GPU-accelerated visualizer (optional)
  - Multiple visual styles: toric, classic, legacy, minimalistic, terminal
  - Configurable colors and position

- **Hotkey System**
  - Configurable hotkey (default: Alt+G)
  - Toggle-based recording (press to start, press to stop)
  - Cross-platform keyboard handling via pynput

- **Desktop Notifications**
  - Recording status notifications
  - Transcription completion alerts
  - Cross-platform notification support (notify-send, plyer)

- **Configuration**
  - Environment-based configuration via `.env` file
  - Configurable microphone device selection
  - Adjustable audio parameters (sample rate, chunk size)

- **Installation Options**
  - pip installable package (`pip install -e .`)
  - System-wide installation script (`install.sh`)
  - Systemd service support for auto-start

### Technical Details

- Python 3.10+ required
- Uses PyAudio for audio capture
- Supports both pygame and VisPy visualizer backends
- MIT licensed

[1.0.0]: https://github.com/asi0flammern/dicton/releases/tag/v1.0.0
