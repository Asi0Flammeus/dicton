"""First-launch wizard — rich terminal, 5 steps, with 4-model self-test."""

from __future__ import annotations

import asyncio
import shutil
import sys
import time

import httpx
import numpy as np
import sounddevice as sd
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import cleanup as cleanup_mod
from . import platform as platform_mod
from . import stt
from .config import CLEANUP_MODELS, ChunkParams, Config
from .stt import GROQ_BASE, pcm16_to_wav

console = Console()

TEST_PHRASE_HINT = "le rapide renard brun saute par-dessus le chien paresseux"
RECORD_SECONDS = 3.0


def run_wizard(existing: Config | None) -> Config:
    """Walk asi0 through the 5 wizard steps. Returns the resulting Config."""
    cfg = existing or Config()
    cfg.chunk = cfg.chunk or ChunkParams()

    console.print(
        Panel.fit(
            "[bold]dicton — premier lancement[/bold]\n"
            "Cinq étapes : système · clé Groq · hotkey · self-test · autostart",
            border_style="cyan",
        )
    )

    _step_system_check()
    cfg.groq_api_key = _step_api_key(cfg.groq_api_key)
    cfg.hotkey_primary, cfg.hotkey_secondary = _step_hotkeys(
        cfg.hotkey_primary, cfg.hotkey_secondary
    )
    cfg.cleanup_model = asyncio.run(_step_self_test(cfg))
    cfg.autostart = _step_autostart(cfg.autostart)

    console.print(
        Panel.fit(
            f"[green]Configuration prête.[/green]\n"
            f"Hotkey [cyan]{cfg.hotkey_primary}[/cyan] / [cyan]{cfg.hotkey_secondary}[/cyan] · "
            f"cleanup [cyan]{cfg.cleanup_model}[/cyan]",
            border_style="green",
        )
    )
    return cfg


# ---- 1. system check ----


def _step_system_check() -> None:
    console.rule("[bold]1 · Système[/bold]")
    py_ok = sys.version_info >= (3, 11)
    console.print(
        f"  Python {sys.version_info.major}.{sys.version_info.minor}: "
        + ("[green]OK[/green]" if py_ok else "[red]≥3.11 requis[/red]")
    )
    if not py_ok:
        raise SystemExit(1)

    try:
        sd.query_devices()
        console.print("  Audio (sounddevice): [green]OK[/green]")
    except Exception as exc:
        console.print(f"  Audio: [red]{exc}[/red]")
        raise SystemExit(1) from exc

    if sys.platform == "linux":
        missing = [c for c in ("wl-copy", "xclip") if not shutil.which(c)]
        if len(missing) == 2:
            console.print("  Clipboard: [yellow]installez wl-clipboard ou xclip[/yellow]")
        else:
            console.print("  Clipboard: [green]OK[/green]")


# ---- 2. Groq API key ----


def _step_api_key(current: str) -> str:
    console.rule("[bold]2 · Clé Groq[/bold]")
    console.print("Crée une clé sur [link]https://console.groq.com/keys[/link]")
    default = current or None
    key = Prompt.ask("Colle ta clé Groq", default=default, password=False)
    if not key:
        raise SystemExit("Clé Groq requise.")
    console.print("  Test [cyan]GET /models[/cyan] ...", end=" ")
    try:
        with httpx.Client(http2=True, timeout=8.0) as c:
            r = c.get(f"{GROQ_BASE}/models", headers={"Authorization": f"Bearer {key}"})
            r.raise_for_status()
        console.print("[green]OK[/green]")
    except httpx.HTTPError as exc:
        console.print(f"[red]échec — {exc}[/red]")
        raise SystemExit(1) from exc
    return key


# ---- 3. hotkey ----


def _step_hotkeys(primary: str, secondary: str) -> tuple[str, str]:
    console.rule("[bold]3 · Hotkey[/bold]")
    console.print("Raccourcis globaux. Défaut [cyan]F2[/cyan] sur les deux.")
    p = Prompt.ask("Touche primaire", default=primary or "f2")
    s = Prompt.ask("Touche secondaire", default=secondary or "f2")
    return p, s


# ---- 4. self-test ----


async def _step_self_test(cfg: Config) -> str:
    console.rule("[bold]4 · Self-test[/bold]")
    console.print(
        f"Appuie sur Entrée puis parle [bold]{RECORD_SECONDS:.0f} secondes[/bold] — "
        f"essaie « [italic]{TEST_PHRASE_HINT}[/italic] »"
    )
    Prompt.ask("⏎ pour démarrer", default="")

    pcm = _record_seconds(RECORD_SECONDS, cfg.sample_rate)
    wav = pcm16_to_wav(pcm, cfg.sample_rate)
    console.print("  recording   [green]done[/green]")

    async with httpx.AsyncClient(http2=True, timeout=30.0) as client:
        prewarm_t = time.monotonic()
        await stt.prewarm(client, api_key=cfg.groq_api_key)
        prewarm_ms = int((time.monotonic() - prewarm_t) * 1000)

        t = time.monotonic()
        transcript = await stt.transcribe(
            client,
            wav,
            api_key=cfg.groq_api_key,
            model=cfg.stt_model,
            language=cfg.language,
        )
        stt_ms = int((time.monotonic() - t) * 1000)
        console.print(f"  STT         {stt_ms} ms")
        console.print(f"  prewarm     {prewarm_ms} ms")
        console.print(f"  brut: [italic]{transcript}[/italic]")

        rows = []
        for model in CLEANUP_MODELS:
            t = time.monotonic()
            cleaned = await cleanup_mod.cleanup(
                client,
                transcript,
                api_key=cfg.groq_api_key,
                model=model,
            )
            cleanup_ms = int((time.monotonic() - t) * 1000)
            e2e = prewarm_ms + stt_ms + cleanup_ms + 30  # +30 paste budget
            rows.append((model, cleanup_ms, e2e, cleaned))

    fastest = min(rows, key=lambda r: r[1])[0]

    table = Table(title="Cleanup self-test")
    table.add_column("#")
    table.add_column("Modèle")
    table.add_column("Cleanup", justify="right")
    table.add_column("E2E budget", justify="right")
    table.add_column("Status")
    for i, (model, cl_ms, e2e_ms, _) in enumerate(rows, 1):
        status = "[red]>2s[/red]" if e2e_ms > 2000 else "[green]ok[/green]"
        style = "bold" if model == fastest else None
        table.add_row(
            str(i),
            model,
            f"{cl_ms} ms",
            f"{e2e_ms} ms",
            status,
            style=style or "",
        )
    console.print(table)

    console.print("Rendus :")
    for i, (_model, _, _, text) in enumerate(rows, 1):
        console.print(f"  {i} · [italic]{text or '(vide)'}[/italic]")

    default_idx = CLEANUP_MODELS.index(fastest) + 1
    raw = Prompt.ask(
        "Quel modèle veux-tu par défaut ?",
        choices=[str(i) for i in range(1, len(rows) + 1)],
        default=str(default_idx),
    )
    return CLEANUP_MODELS[int(raw) - 1]


def _record_seconds(seconds: float, sample_rate: int) -> np.ndarray:
    samples = int(seconds * sample_rate)
    console.print(f"  [red]●[/red] recording {seconds:.0f}s...")
    audio = sd.rec(samples, samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()
    return audio[:, 0]


# ---- 5. autostart ----


def _step_autostart(current: bool) -> bool:
    console.rule("[bold]5 · Autostart[/bold]")
    if Confirm.ask("Lancer dicton au démarrage du système ?", default=current):
        ok = platform_mod.enable_autostart()
        console.print("  [green]activé[/green]" if ok else "  [yellow]non supporté[/yellow]")
        return ok
    platform_mod.disable_autostart()
    return False
