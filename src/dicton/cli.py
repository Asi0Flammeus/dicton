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
        help="Local path (development install). Omit to upgrade from PyPI.",
    ),
    no_restart: bool = typer.Option(
        False, "--no-restart", help="Skip restarting the systemd unit after install."
    ),
) -> None:
    """Reinstall dicton, then restart the daemon to pick up the new code.

    Without arguments, upgrades the published release via ``uv tool upgrade``.
    With a path, rebuilds from local sources via ``uv tool install --force
    --reinstall`` — the standard dev loop. Either way, if the systemd unit is
    active it is restarted automatically so the new binary takes effect.
    """
    if not _which("uv"):
        console.print("[red]uv not found.[/red] Install: https://docs.astral.sh/uv/")
        raise typer.Exit(1)

    _kill_stale_dicton_on_windows()

    if source:
        path = Path(source).expanduser().resolve()
        if not (path / "pyproject.toml").exists():
            console.print(f"[red]{path} has no pyproject.toml[/red]")
            raise typer.Exit(1)
        console.print(f"Running [cyan]uv tool install --force --reinstall {path}[/cyan]…")
        cmd = ["uv", "tool", "install", "--force", "--reinstall", str(path)]
    else:
        console.print("Running [cyan]uv tool upgrade dicton[/cyan]…")
        cmd = ["uv", "tool", "upgrade", "dicton"]

    r = subprocess.run(cmd, check=False)
    if r.returncode != 0:
        raise typer.Exit(r.returncode)

    if no_restart:
        console.print("[green]Installed.[/green]  Skipped daemon restart (--no-restart).")
        return
    if _systemd_unit_active():
        console.print("Restarting [cyan]systemctl --user dicton.service[/cyan]…")
        if _restart_systemd_unit():
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

    if not foreground and cfg.autostart and _restart_systemd_unit():
        console.print("[green]Daemon running via systemd[/green] — terminal is free.")
        console.print("  status:  [cyan]systemctl --user status dicton[/cyan]")
        console.print("  logs:    [cyan]journalctl --user -u dicton -f[/cyan]")
        console.print("  stop:    [cyan]systemctl --user stop dicton[/cyan]")
        return

    # Skip the "unit already running" check when we *are* the unit's ExecStart.
    if "INVOCATION_ID" not in os.environ and _systemd_unit_active():
        console.print(
            "[yellow]dicton.service is already running.[/yellow]\n"
            "Stop it first ([cyan]systemctl --user stop dicton[/cyan]) "
            "to run inline."
        )
        raise typer.Exit(1)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    console.print("[cyan]Starting daemon in foreground…[/cyan]  (Ctrl+C to stop)")
    from .runtime import run as run_pipeline

    run_pipeline(cfg)


def _systemd_unit_active() -> bool:
    if sys.platform != "linux" or not _which("systemctl"):
        return False
    r = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", "dicton.service"],
        check=False,
    )
    return r.returncode == 0


def _restart_systemd_unit() -> bool:
    if sys.platform != "linux" or not _which("systemctl"):
        return False
    r = subprocess.run(
        ["systemctl", "--user", "restart", "dicton.service"],
        check=False,
    )
    return r.returncode == 0


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def _kill_stale_dicton_on_windows() -> None:
    """Kill any other dicton.exe still holding the launcher shim open.

    Windows refuses to overwrite an .exe whose process is alive, so
    ``uv tool upgrade`` fails with ERROR_SHARING_VIOLATION. We exclude
    our own PID — the running ``dicton update`` is itself dicton.exe.
    """
    if sys.platform != "win32":
        return
    subprocess.run(
        ["taskkill", "/F", "/IM", "dicton.exe", "/FI", f"PID ne {os.getpid()}"],
        check=False,
        capture_output=True,
    )


_ = Path  # reserved for future config-path printing
