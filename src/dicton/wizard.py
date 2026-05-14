"""Rich terminal setup wizard."""

from __future__ import annotations

import asyncio
import time

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .cleanup import cleanup_text
from .config import CLEANUP_MODELS, Config, load_config, save_config
from .platform import install_autostart
from .stt import GroqClient

console = Console()
TEST_TEXT = "le rapide renard brun saute par dessus le chien paresseux"


async def _test_model(client: GroqClient, model: str) -> tuple[int, str, str]:
    t0 = time.monotonic()
    try:
        cleaned = await cleanup_text(client, TEST_TEXT, model)
        return round((time.monotonic() - t0) * 1000), cleaned, "ok"
    except Exception as exc:
        return 0, str(exc), "error"


async def run_wizard() -> Config:
    cfg = load_config()
    console.rule("dicton setup")
    key = Prompt.ask("Groq API key", password=True, default=cfg.groq_api_key)
    cfg.groq_api_key = key
    client = GroqClient(key)
    await client.prewarm()
    cfg.primary_hotkey = Prompt.ask("Primary hotkey", default=cfg.primary_hotkey)
    cfg.secondary_hotkey = Prompt.ask("Secondary hotkey", default=cfg.secondary_hotkey)

    table = Table(title="Cleanup models")
    for col in ["#", "Model", "Cleanup", "€/an", "Status"]:
        table.add_column(col)
    results = []
    for idx, model in enumerate(CLEANUP_MODELS, 1):
        latency, rendered, status = await _test_model(client, model)
        results.append((model, latency, rendered, status))
        annual = {1: "~2€", 2: "~4€", 3: "~9€", 4: "<1€"}[idx]
        table.add_row(str(idx), model, f"{latency}ms" if latency else "—", annual, status)
    console.print(table)
    for idx, (model, _latency, rendered, _status) in enumerate(results, 1):
        console.print(f"[bold]{idx} · {model}[/bold]\n{rendered}\n")
    pick = int(Prompt.ask("Default cleanup model", choices=["1", "2", "3", "4"], default="1"))
    cfg.cleanup_model = results[pick - 1][0]
    cfg.autostart = Confirm.ask("Enable autostart?", default=cfg.autostart)
    save_config(cfg)
    if cfg.autostart:
        install_autostart()
    await client.close()
    return cfg


def wizard() -> Config:
    return asyncio.run(run_wizard())
