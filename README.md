# dicton

French voice dictation. Hold a hotkey, speak, release — cleaned-up text appears
in the active app in under two seconds.

Single provider (Groq). Single binary entrypoint. Three platforms.

## Install

```bash
uv tool install dicton
dicton wizard
```

The wizard walks through: system check → Groq API key → hotkey → live self-test
of four cleanup models → autostart. The resulting TOML lives at the platform's
config dir (Linux `~/.config/dicton/config.toml`, macOS
`~/Library/Application Support/dicton/config.toml`, Windows
`%APPDATA%\dicton\config.toml`).

## Use

Hold the configured hotkey (default `F2`), speak in French, release. The text
is pasted into whatever app currently has focus.

## Commands

| Command         | Effect                                                   |
| --------------- | -------------------------------------------------------- |
| `dicton`        | Run the daemon (default — re-runs the wizard if needed). |
| `dicton wizard` | Re-run the full first-launch setup.                      |
| `dicton config` | Re-pick the cleanup model.                               |
| `dicton stats`  | Print lifetime totals (chars, typing time saved).        |
| `dicton update` | `uv tool upgrade dicton`.                                |

## Architecture

Fourteen files under `src/dicton/`. `pipeline.py` is the only file that owns
the runtime lifecycle (hotkey, audio, chunker, HTTP, paste). Hard cap of 300
LOC, enforced by `./scripts/check.sh lint`.

| File            | Role                                                  |
| --------------- | ----------------------------------------------------- |
| `pipeline.py`   | Orchestrator. Hotkey → audio → STT → cleanup → paste. |
| `chunker.py`    | Silence-based RMS chunking during recording.          |
| `stt.py`        | Groq Whisper, shared `httpx.AsyncClient`.             |
| `cleanup.py`    | Groq LLM cleanup pass (same socket).                  |
| `output.py`     | Cross-platform clipboard + paste keystroke.           |
| `visualizer.py` | pygame waveform + state badge.                        |
| `fn_key.py`     | Linux Fn-key listener via `evdev` (optional).         |
| `wizard.py`     | Rich first-run setup with 4-model self-test.          |
| `config.py`     | TOML at XDG path (`chmod 600` on the key).            |
| `stats.py`      | Append-only JSONL of every dictation.                 |
| `platform.py`   | Autostart via systemd / launchd / HKCU Run.           |
| `cli.py`        | `typer` entrypoint.                                   |
| `__main__.py`   | `python -m dicton`.                                   |
| `__init__.py`   | Version export from `hatch-vcs`.                      |

## Development

```bash
uv sync --extra dev
./scripts/check.sh all
```

`./scripts/check.sh lint` runs `ruff check`, `ruff format --check`, and enforces
the 300-LOC cap on `pipeline.py`. `./scripts/check.sh test` runs the pytest
suite (chunker, stats, config, mocked STT/cleanup via respx).

## License

MIT — see [LICENSE](LICENSE).
