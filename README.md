<p align="center">
  <img src="src/dicton/assets/logo.png" alt="Dicton Logo" width="560">
</p>

<p align="center">
  <a href="https://github.com/Asi0Flammeus/dicton/actions/workflows/ci.yml"><img src="https://github.com/Asi0Flammeus/dicton/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://github.com/Asi0Flammeus/dicton/releases/latest"><img src="https://img.shields.io/github/v/release/Asi0Flammeus/dicton" alt="Latest Release"></a>
  <a href="https://github.com/Asi0Flammeus/dicton/blob/main/LICENSE"><img src="https://img.shields.io/github/license/Asi0Flammeus/dicton" alt="License"></a>
</p>

# Dicton

Dicton is a dictation app that lets you speak directly into any text field.

It is built for speed and low friction: press a hotkey, talk, release, and the text appears where your cursor already is. The default product is intentionally simple:

- direct transcription
- translation to English
- system-wide typing into the active app

## Why It Works Well

- It stays out of the way. You do not have to dictate inside a separate editor first.
- It is fast. The app is optimized for short push-to-talk dictation.
- It is simple. The default workflow is just “talk” or “translate to English”.
- It works across apps. If you can type there, Dicton can usually type there too.
- It has provider fallback. You can use Mistral or ElevenLabs for speech-to-text.

## Platforms

- Linux: stable main platform
- Windows: first packaged release available
- macOS: not packaged yet

## Install

Download the latest release here:

[Latest release](https://github.com/Asi0Flammeus/dicton/releases/latest)

### Linux

Download the `.deb` file from the latest release, then install it with:

```bash
sudo apt install ./dicton_1.3.0_amd64.deb
```

If your system prefers `dpkg`:

```bash
sudo dpkg -i dicton_1.3.0_amd64.deb
sudo apt-get install -f
```

### Windows

Download `dicton-windows-x64.zip` from the latest release.

1. Unzip it.
2. Open the extracted folder.
3. Run `dicton.exe`.

## First Setup

Dicton needs at least one speech-to-text API key.

Use one of these:

- `MISTRAL_API_KEY`
- `ELEVENLABS_API_KEY`

For translation to English, add one of these too:

- `GEMINI_API_KEY`
- `ANTHROPIC_API_KEY`

The easiest way to configure Dicton is:

```bash
dicton --config
```

That opens the guided setup page in your browser. It walks through:

- speech provider key
- hotkey validation
- first transcription test
- start-on-login

`dicton --config-ui` still works, but `dicton --config` is the main onboarding command now.

If you prefer editing the file directly, Dicton reads `.env` from its user config directory:

- Linux: `~/.config/dicton/.env`
- Windows: `%APPDATA%\dicton\.env`

Minimal example:

```env
MISTRAL_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

## Use

### Linux default hotkeys

- `FN` hold: transcribe
- `FN` double-tap: start/stop recording
- `FN + Ctrl`: translate to English

### Windows default hotkey

- `Alt+G`: start/stop dictation

## Notes

- Linux has the best support today.
- Windows currently targets the simpler fallback workflow rather than full Linux feature parity.
- macOS support is not packaged yet.

## Releases

- Latest release: [https://github.com/Asi0Flammeus/dicton/releases/latest](https://github.com/Asi0Flammeus/dicton/releases/latest)
- All releases: `https://github.com/Asi0Flammeus/dicton/releases`

## Development

If you want to work on Dicton rather than just install it:

- setup guide: [SETUP.md](SETUP.md)
- contributing guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Windows packaging notes: [docs/windows-packaging.md](docs/windows-packaging.md)
- Linux packaging notes: [docs/linux-packaging.md](docs/linux-packaging.md)
