"""dicton CLI — five commands via typer."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from . import __version__, config, stats, wizard
from .config import CLEANUP_MODELS
from .os_ import service

app = typer.Typer(
    name="dicton",
    help="French voice dictation. Hold the hotkey, speak, release. Text is pasted.",
    add_completion=False,
    no_args_is_help=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def _entry(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version and exit."),
    foreground: bool = typer.Option(
        False, "--foreground", help="Run inline (block the terminal) instead of via systemd."
    ),
) -> None:
    if version:
        console.print(f"dicton {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _smart_start(foreground=foreground)


@app.command()
def run() -> None:
    """Run the dictation daemon in foreground (legacy; prefer bare `dicton`)."""
    _smart_start(foreground=True)


@app.command(name="wizard")
def wizard_cmd(
    foreground: bool = typer.Option(
        False, "--foreground", help="Run inline instead of via systemd after the wizard."
    ),
) -> None:
    """Re-run the first-launch wizard, then start the daemon."""
    cfg = wizard.run_wizard(config.load() if config.exists() else None)
    cfg.save()
    console.print(f"[green]Saved[/green] {config.CONFIG_PATH}")
    _start_after_config(cfg, foreground=foreground)


@app.command(name="config")
def config_cmd() -> None:
    """Re-pick the cleanup model and write to the TOML."""
    if not config.exists():
        console.print("[red]No config yet[/red] — run `dicton wizard` first.")
        raise typer.Exit(1)
    cfg = config.load()
    console.print(f"Current model: [cyan]{cfg.cleanup_model}[/cyan]")
    console.print("Available:")
    for i, m in enumerate(CLEANUP_MODELS, 1):
        marker = "●" if m == cfg.cleanup_model else "○"
        console.print(f"  {marker} [{i}] {m}")
    choice = typer.prompt("Pick a number", default=str(CLEANUP_MODELS.index(cfg.cleanup_model) + 1))
    try:
        idx = int(choice) - 1
        cfg.cleanup_model = CLEANUP_MODELS[idx]
    except (ValueError, IndexError):
        console.print("[red]Invalid choice[/red]")
        raise typer.Exit(1) from None
    cfg.save()
    console.print(f"[green]Saved[/green] cleanup_model = {cfg.cleanup_model}")


@app.command(name="hotkey")
def hotkey_cmd() -> None:
    """Re-capture the trigger keys (primary double-tap + optional secondary)."""
    if not config.exists():
        console.print("[red]No config yet[/red] — run `dicton wizard` first.")
        raise typer.Exit(1)
    cfg = config.load()
    cfg.hotkey_primary, cfg.hotkey_secondary, cfg.hotkey_fn_keycode = wizard._step_hotkeys(cfg)
    cfg.save()
    secondary = cfg.hotkey_secondary or "—"
    console.print(
        f"[green]Saved[/green] primaire={cfg.hotkey_primary} (double-tap) · secondaire={secondary}"
    )
    _restart_hint()


@app.command(name="mic")
def mic_cmd() -> None:
    """Re-pick the input device (or follow the system default mic)."""
    if not config.exists():
        console.print("[red]No config yet[/red] — run `dicton wizard` first.")
        raise typer.Exit(1)
    cfg = config.load()
    cfg.input_device = wizard._pick_input_device(cfg.input_device)
    cfg.save()
    label = "système par défaut" if cfg.input_device is None else f"index {cfg.input_device}"
    console.print(f"[green]Saved[/green] micro = {label}")
    _restart_hint()


def _restart_hint() -> None:
    console.print("Restart the daemon to apply: [cyan]systemctl --user restart dicton[/cyan]")


@app.command(name="stats")
def stats_cmd() -> None:
    """Show lifetime usage summary."""
    s = stats.summarise()
    if s.count == 0:
        console.print("No dictations recorded yet.")
        raise typer.Exit()
    console.print(f"Dictations:        [cyan]{s.count}[/cyan]")
    console.print(f"Characters output: [cyan]{s.total_chars:,}[/cyan]")
    console.print(f"Audio recorded:    [cyan]{s.total_audio_s / 60:.1f} min[/cyan]")
    console.print(f"Typing saved:      [green]{s.typing_saved_min:.0f} min[/green]")
    console.print(f"Avg recording:     [cyan]{s.avg_recording_ms:.0f} ms[/cyan]  (you speaking)")
    console.print(
        f"Avg process:       [cyan]{s.avg_process_ms:.0f} ms[/cyan]  "
        "(stt + cleanup + paste, post-stop latency)"
    )


@app.command(name="update")
def update_cmd(
    source: str | None = typer.Argument(
        None,
        help="Local path (development install). Omit to pull the latest main from GitHub.",
    ),
    no_restart: bool = typer.Option(
        False, "--no-restart", help="Skip restarting the systemd unit after install."
    ),
) -> None:
    """Reinstall dicton, then restart the daemon to pick up the new code.

    Without arguments, reinstalls from the latest ``main`` on GitHub via
    ``uv tool install --force --reinstall git+<repo>@main``. We force a full
    reinstall (not a bare ``uv tool upgrade``) because ``main`` is a moving
    git ref: uv caches the resolved commit, so only ``--reinstall`` (which
    implies ``--refresh``) re-fetches the branch HEAD. This also self-heals an
    install whose recorded source path has gone missing.

    With a path, rebuilds from local sources via ``uv tool install --force
    --reinstall`` — the standard dev loop. Either way, if the systemd unit is
    active it is restarted automatically so the new binary takes effect.
    """
    if not _which("uv"):
        console.print("[red]uv not found.[/red] Install: https://docs.astral.sh/uv/")
        raise typer.Exit(1)

    if source:
        path = Path(source).expanduser().resolve()
        if not (path / "pyproject.toml").exists():
            console.print(f"[red]{path} has no pyproject.toml[/red]")
            raise typer.Exit(1)
        cmd = ["uv", "tool", "install", "--force", "--reinstall", str(path)]
    else:
        if not _check_for_updates():
            return
        cmd = [
            "uv",
            "tool",
            "install",
            "--force",
            "--reinstall",
            f"git+{GITHUB_REMOTE_URL}@main",
        ]

    service.kill_stale_dicton()
    # We can't replace our own running dicton.exe in place on Windows —
    # the OS holds an exclusive lock on it. spawn_detached_upgrade hands
    # off to a detached PowerShell helper there (returns True) and is a
    # no-op (returns False) elsewhere, so we run cmd ourselves.
    if service.spawn_detached_upgrade(cmd, restart_daemon=not no_restart):
        console.print("[cyan]Upgrade started in a new window — close this one.[/cyan]")
        if not no_restart:
            console.print("[dim]dictonw will be restarted once the upgrade succeeds.[/dim]")
        return

    console.print(f"Running [cyan]{' '.join(cmd)}[/cyan]…")
    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        raise typer.Exit(r.returncode)

    if no_restart:
        console.print("[green]Installed.[/green]  Skipped daemon restart (--no-restart).")
        return
    if service.systemd_unit_active():
        console.print("Restarting [cyan]systemctl --user dicton.service[/cyan]…")
        if service.restart_systemd_unit():
            console.print("[green]Daemon restarted on the new binary.[/green]")
        else:
            console.print("[yellow]Systemd restart failed.[/yellow]")
    else:
        console.print("[green]Installed.[/green]  Systemd unit isn't active; nothing to restart.")


# ---- internal ----


def _smart_start(*, foreground: bool) -> None:
    """Run wizard if no config, then start the daemon via systemd (default) or inline."""
    # When invoked by a systemd unit, INVOCATION_ID is set. Forcing foreground
    # there prevents an infinite restart loop where the unit's ExecStart command
    # would otherwise ask systemd to restart itself.
    if "INVOCATION_ID" in os.environ:
        foreground = True
    if not config.exists():
        console.print("[yellow]No config yet — running first-launch wizard.[/yellow]")
        cfg = wizard.run_wizard(None)
        cfg.save()
    else:
        cfg = config.load()
    _start_after_config(cfg, foreground=foreground)


def _start_after_config(cfg, *, foreground: bool) -> None:
    if not cfg.groq_api_key:
        console.print("[red]Missing Groq API key.[/red] Run [cyan]dicton wizard[/cyan].")
        raise typer.Exit(1)

    if not foreground and cfg.autostart and service.restart_systemd_unit():
        console.print("[green]Daemon running via systemd[/green] — terminal is free.")
        console.print("  status:  [cyan]systemctl --user status dicton[/cyan]")
        console.print("  logs:    [cyan]journalctl --user -u dicton -f[/cyan]")
        console.print("  stop:    [cyan]systemctl --user stop dicton[/cyan]")
        return

    # Skip the "unit already running" check when we *are* the unit's ExecStart.
    if "INVOCATION_ID" not in os.environ and service.systemd_unit_active():
        console.print(
            "[yellow]dicton.service is already running.[/yellow]\n"
            "Stop it first ([cyan]systemctl --user stop dicton[/cyan]) "
            "to run inline."
        )
        raise typer.Exit(1)

    _setup_logging()
    console.print("[cyan]Starting daemon in foreground…[/cyan]  (Ctrl+C to stop)")
    console.print(f"[dim]Logs: {config.LOG_PATH}[/dim]")
    from .runtime import run as run_pipeline

    run_pipeline(cfg)


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


GITHUB_REMOTE_URL = "https://github.com/Asi0Flammeus/dicton.git"


def _current_commit_sha() -> str | None:
    """Pull the abbreviated git SHA out of ``__version__`` (e.g. ``g3102926``).

    Returns ``None`` for non-git installs (PyPI), where hatch-vcs writes a
    plain version like ``1.15.0`` with no ``+g<sha>`` local tag.
    """
    import re

    m = re.search(r"\+g([0-9a-f]+)", __version__)
    return m.group(1) if m else None


def _remote_commit_sha() -> str | None:
    """Fetch the SHA of ``HEAD`` on the public repo. ``None`` if unreachable."""
    if not _which("git"):
        return None
    try:
        r = subprocess.run(
            ["git", "ls-remote", GITHUB_REMOTE_URL, "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not r.stdout:
        return None
    return r.stdout.split()[0]


def _check_for_updates() -> bool:
    """Compare local vs remote git SHA. Returns False if already up to date.

    Prints a status line either way so the user sees what dicton thinks is
    happening — `dicton update` used to silently spawn a window with no
    feedback in the parent shell.
    """
    with console.status("[cyan]Vérification des mises à jour…[/cyan]", spinner="dots"):
        current = _current_commit_sha()
        remote = _remote_commit_sha()

    if current and remote and remote.startswith(current):
        console.print(f"[green]Déjà à jour[/green] · [dim]commit {current}[/dim]")
        return False
    if current and remote:
        console.print(
            f"[yellow]Nouvelle version disponible[/yellow]: "
            f"[dim]{current}[/dim] → [cyan]{remote[: len(current)]}[/cyan]"
        )
    else:
        console.print(
            "[dim]Vérification distante impossible — on tente l'upgrade quand même.[/dim]"
        )
    return True


def _setup_logging() -> None:
    """Route logs to a rotating file plus stderr when available.

    dictonw.exe under pythonw has no usable stderr, so without a file
    handler the daemon is invisible when it misbehaves. systemd users
    on Linux still get logs via journalctl AND a local file.
    """
    from logging.handlers import RotatingFileHandler

    config.LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    file_h = RotatingFileHandler(config.LOG_PATH, maxBytes=512_000, backupCount=2, encoding="utf-8")
    file_h.setFormatter(fmt)
    handlers: list[logging.Handler] = [file_h]
    if sys.stderr is not None:
        stream_h = logging.StreamHandler()
        stream_h.setFormatter(fmt)
        handlers.append(stream_h)

    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True)


_ = Path  # reserved for future config-path printing
