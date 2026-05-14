"""Local TOML-ish configuration for dicton."""

from __future__ import annotations

import os
import stat
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

CONFIG_DIR = Path(user_config_dir("dicton", appauthor=False))
CONFIG_PATH = CONFIG_DIR / "config.toml"

CLEANUP_MODELS = {
    "openai/gpt-oss-20b": "Vitesse pure — default, très bas coût.",
    "openai/gpt-oss-120b": "Équilibre vitesse/qualité.",
    "llama-3.3-70b-versatile": "Qualité maximale FR.",
    "llama-3.1-8b-instant": "Mode économie — latence/coût minimum.",
}


@dataclass(slots=True)
class Config:
    groq_api_key: str = ""
    cleanup_model: str = "openai/gpt-oss-20b"
    primary_hotkey: str = "<f2>"
    secondary_hotkey: str = "<f2>"
    autostart: bool = False
    sample_rate: int = 16_000
    frame_ms: int = 50
    min_chunk_s: float = 6.0
    max_chunk_s: float = 20.0
    overlap_s: float = 0.4
    silence_threshold_dbfs: float = -40.0
    silence_window_s: float = 0.35


def _coerce(raw: str, typ: type) -> Any:
    raw = raw.strip().strip('"')
    if typ is bool:
        return raw.lower() in {"1", "true", "yes", "on"}
    if typ is int:
        return int(raw)
    if typ is float:
        return float(raw)
    return raw


def load_config(path: Path = CONFIG_PATH) -> Config:
    cfg = Config(groq_api_key=os.getenv("GROQ_API_KEY", ""))
    if not path.exists():
        return cfg
    values: dict[str, Any] = {}
    types = {f.name: f.type for f in fields(Config)}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        key = key.strip()
        if key in types:
            typ = types[key]
            values[key] = _coerce(raw, typ if isinstance(typ, type) else str)
    return Config(**{**asdict(cfg), **values})


def save_config(cfg: Config, path: Path = CONFIG_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for key, value in asdict(cfg).items():
        if isinstance(value, str):
            escaped = value.replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        elif isinstance(value, bool):
            lines.append(f"{key} = {str(value).lower()}")
        else:
            lines.append(f"{key} = {value}")
    path.write_text("\n".join(lines) + "\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
