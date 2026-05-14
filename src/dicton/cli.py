"""dicton CLI — five commands via typer."""

from __future__ import annotations

import logging
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
) -> None:
    if version:
        console.print(f"dicton {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _run_daemon()


@app.command()
def run() -> None:
    """Run the dictation daemon (default when no command given)."""
    _run_daemon()


@app.command(name="wizard")
def wizard_cmd() -> None:
    """Re-run the first-launch wizard (system check, Groq key, hotkey, self-test)."""
    cfg = wizard.run_wizard(config.load() if config.exists() else None)
    cfg.save()
    console.print(f"[green]Saved[/green] {config.CONFIG_PATH}")


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
    console.print(f"Avg end-to-end:    [cyan]{s.avg_e2e_ms:.0f} ms[/cyan]")


@app.command(name="update")
def update_cmd() -> None:
    """Upgrade dicton via uv and ask the user to restart the daemon."""
    if not _which("uv"):
        console.print("[red]uv not found.[/red] Install: https://docs.astral.sh/uv/")
        raise typer.Exit(1)
    console.print("Running [cyan]uv tool upgrade dicton[/cyan]…")
    r = subprocess.run(["uv", "tool", "upgrade", "dicton"], check=False)
    if r.returncode != 0:
        raise typer.Exit(r.returncode)
    console.print("[green]Upgraded.[/green] Restart the daemon to pick up the new version.")


# ---- internal ----


def _run_daemon() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not config.exists():
        console.print("[yellow]No config yet — running first-launch wizard.[/yellow]")
        cfg = wizard.run_wizard(None)
        cfg.save()
    else:
        cfg = config.load()
    if not cfg.groq_api_key:
        console.print("[red]Missing Groq API key.[/red] Run [cyan]dicton wizard[/cyan].")
        raise typer.Exit(1)
    from .pipeline import run as run_pipeline

    run_pipeline(cfg)


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


_ = Path  # reserved for future config-path printing
_ = sys
