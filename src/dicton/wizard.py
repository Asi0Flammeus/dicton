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
from . import stt
from .config import CLEANUP_MODELS, ChunkParams, Config
from .os_ import autostart as platform_mod
from .os_ import fn_key
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

    _step_system_check(cfg)
    cfg.groq_api_key = _step_api_key(cfg.groq_api_key)
    cfg.hotkey_primary, cfg.hotkey_secondary, cfg.hotkey_fn_keycode = _step_hotkeys(cfg)
    cfg.cleanup_model = asyncio.run(_step_self_test(cfg))
    cfg.autostart = _step_autostart(cfg.autostart)

    secondary_label = cfg.hotkey_secondary or "—"
    console.print(
        Panel.fit(
            f"[green]Configuration prête.[/green]\n"
            f"Primaire [cyan]{cfg.hotkey_primary}[/cyan] (double-tap) · "
            f"secondaire [cyan]{secondary_label}[/cyan] (simple) · "
            f"cleanup [cyan]{cfg.cleanup_model}[/cyan]",
            border_style="green",
        )
    )
    return cfg


# ---- 1. system check ----


def _step_system_check(cfg: Config) -> None:
    console.rule("[bold]1 · Système[/bold]")
    py_ok = sys.version_info >= (3, 11)
    console.print(
        f"  Python {sys.version_info.major}.{sys.version_info.minor}: "
        + ("[green]OK[/green]" if py_ok else "[red]≥3.11 requis[/red]")
    )
    if not py_ok:
        raise SystemExit(1)

    try:
        default = sd.query_devices(kind="input")
        console.print(f"  Audio (sounddevice): [green]OK[/green] — défaut: {default['name']}")
    except sd.PortAudioError as exc:
        console.print(f"  Audio: [yellow]défaut indisponible ({exc})[/yellow]")
        cfg.input_device = _pick_input_device(cfg.input_device)
    except Exception as exc:
        console.print(f"  Audio: [red]{exc}[/red]")
        raise SystemExit(1) from exc
    else:
        # Default mic is fine, but offer a picker if there's more than one
        # input so the user can switch (e.g. webcam mic vs headset). The
        # picker defaults to "système par défaut" (None) — the stable choice.
        inputs = _list_input_devices()
        if len(inputs) > 1:
            cfg.input_device = _pick_input_device(cfg.input_device)

    if sys.platform == "linux":
        missing = [c for c in ("wl-copy", "xclip") if not shutil.which(c)]
        if len(missing) == 2:
            console.print("  Clipboard: [yellow]installez wl-clipboard ou xclip[/yellow]")
        else:
            console.print("  Clipboard: [green]OK[/green]")


def _list_input_devices() -> list[tuple[int, dict]]:
    return [(i, d) for i, d in enumerate(sd.query_devices()) if d.get("max_input_channels", 0) > 0]


def _pick_input_device(current: int | None) -> int | None:
    """Offer the input picker. Choice 0 = follow the system default mic
    (returns None — the stable, recommended option, since PortAudio device
    indices shift across reboots and hot-plugs). Returns a fixed index only
    if the user explicitly pins one."""
    inputs = _list_input_devices()
    if not inputs:
        console.print("  [red]Aucun périphérique d'entrée détecté.[/red]")
        raise SystemExit(1)

    table = Table(title="Périphériques d'entrée disponibles")
    table.add_column("#")
    table.add_column("Nom")
    table.add_column("Canaux", justify="right")
    table.add_row("0", "Micro système par défaut [dim](recommandé)[/dim]", "—")
    default_choice = "0"
    for n, (idx, d) in enumerate(inputs, 1):
        marker = " [dim](actuel)[/dim]" if idx == current else ""
        table.add_row(str(n), d["name"] + marker, str(d["max_input_channels"]))
        if idx == current:
            default_choice = str(n)
    console.print(table)

    raw = Prompt.ask(
        "Quel micro veux-tu utiliser ?",
        choices=[str(i) for i in range(0, len(inputs) + 1)],
        default=default_choice,
    )
    return None if raw == "0" else inputs[int(raw) - 1][0]


# ---- 2. Groq API key ----


def _step_api_key(current: str) -> str:
    console.rule("[bold]2 · Clé Groq[/bold]")
    console.print("Crée une clé sur [link]https://console.groq.com/keys[/link]")
    default = current or None
    key = Prompt.ask("Colle ta clé Groq", default=default, password=True)
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


def _step_hotkeys(cfg: Config) -> tuple[str, str, int | None]:
    console.rule("[bold]3 · Hotkey[/bold]")
    console.print(
        "Touche [bold]primaire[/bold] : [cyan]double-tap[/cyan] pour démarrer "
        "(comme la touche Fn).\n"
        "Touche [bold]secondaire[/bold] (optionnelle) : une touche Fx en "
        "[cyan]simple appui[/cyan]."
    )

    primary, keycode = _capture_primary(cfg.hotkey_primary, cfg.hotkey_fn_keycode)
    secondary = _ask_secondary(cfg.hotkey_secondary)
    return primary, secondary, keycode


def _capture_primary(current: str, current_code: int | None) -> tuple[str, int | None]:
    """Live-capture the primary trigger on Linux (any key, including Fn) and
    learn its evdev keycode. Falls back to a typed key name elsewhere or when
    nothing is captured."""
    if sys.platform != "linux":
        name = Prompt.ask("Touche primaire (double-tap)", default=current or "fn")
        return name, None

    Prompt.ask("⏎ puis appuie une fois sur ta touche primaire", default="")
    console.print("  [red]●[/red] en écoute (5 s)...")
    captured = fn_key.capture_keycode(timeout_s=5.0)
    if captured is None:
        console.print(
            "  [yellow]rien capturé[/yellow] "
            "(droits /dev/input ? ajoute-toi au groupe `input`) — saisie manuelle"
        )
        name = Prompt.ask("Touche primaire (double-tap)", default=current or "fn")
        return name, current_code if name == current else None

    code, label = captured
    console.print(f"  capturé : [cyan]{label}[/cyan] [dim](code {code})[/dim]")
    return label, code


def _ask_secondary(current: str) -> str:
    if not Confirm.ask("Ajouter une touche secondaire (Fx, simple appui) ?", default=bool(current)):
        return ""
    while True:
        raw = Prompt.ask("Touche secondaire (ex. f2, f9)", default=current or "f2")
        name = raw.strip().lower()
        if len(name) >= 2 and name[0] == "f" and name[1:].isdigit() and 1 <= int(name[1:]) <= 12:
            return name
        console.print("  [yellow]Entre une touche fonction F1–F12 (ex. f2).[/yellow]")


# ---- 4. self-test ----


async def _step_self_test(cfg: Config) -> str:
    console.rule("[bold]4 · Self-test[/bold]")
    console.print(
        f"Appuie sur Entrée puis parle [bold]{RECORD_SECONDS:.0f} secondes[/bold] — "
        f"essaie « [italic]{TEST_PHRASE_HINT}[/italic] »"
    )
    Prompt.ask("⏎ pour démarrer", default="")

    pcm = _record_seconds(RECORD_SECONDS, cfg.sample_rate, cfg.input_device)
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
        raw_text = transcript.clean_text()
        stt_ms = int((time.monotonic() - t) * 1000)
        console.print(f"  STT         {stt_ms} ms")
        console.print(f"  prewarm     {prewarm_ms} ms")
        console.print(f"  brut: [italic]{raw_text}[/italic]")

        rows = []
        for model in CLEANUP_MODELS:
            t = time.monotonic()
            cleaned = await cleanup_mod.cleanup(
                client,
                raw_text,
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


def _record_seconds(seconds: float, sample_rate: int, device: int | None) -> np.ndarray:
    samples = int(seconds * sample_rate)
    console.print(f"  [red]●[/red] recording {seconds:.0f}s...")
    audio = sd.rec(samples, samplerate=sample_rate, channels=1, dtype="int16", device=device)
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
