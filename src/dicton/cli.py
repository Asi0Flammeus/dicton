"""Command line interface."""

from __future__ import annotations

import subprocess

import typer
from rich import print

from .config import CLEANUP_MODELS, load_config, save_config
from .pipeline import run_daemon
from .stats import summarize
from .wizard import wizard as run_wizard

app = typer.Typer(add_completion=False, invoke_without_command=True)


@app.callback()
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        run_daemon()


@app.command()
def wizard() -> None:
    """Run the full first-launch setup."""
    run_wizard()


@app.command("config")
def config_cmd() -> None:
    """Choose the cleanup model only."""
    cfg = load_config()
    for idx, (model, desc) in enumerate(CLEANUP_MODELS.items(), 1):
        print(f"{idx}. [bold]{model}[/bold] — {desc}")
    pick = typer.prompt("Cleanup model", default="1")
    cfg.cleanup_model = list(CLEANUP_MODELS)[int(pick) - 1]
    save_config(cfg)
    print(f"Saved {cfg.cleanup_model}")


@app.command()
def stats() -> None:
    """Show lifetime local stats."""
    for key, value in summarize().items():
        print(f"{key}: {value}")


@app.command()
def update() -> None:
    """Upgrade the uv tool and let the supervising daemon restart."""
    subprocess.run(["uv", "tool", "upgrade", "dicton"], check=True)
    print("dicton updated; restart the daemon if your supervisor did not do it automatically")
