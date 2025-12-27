"""Configuration web UI server for Dicton."""

import json
import webbrowser
from pathlib import Path
from threading import Timer
from typing import Any

from .config import Config, config

# HTML template (embedded for single-file deployment)
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dicton Configuration</title>
    <style>
        :root {
            --bg: #100F0F;
            --bg-2: #1C1B1A;
            --ui: #282726;
            --ui-2: #343331;
            --ui-3: #403E3C;
            --tx: #CECDC3;
            --tx-2: #878580;
            --tx-3: #575653;
            --orange: #DA702C;
            --green: #879A39;
            --cyan: #3AA99F;
            --blue: #4385BE;
            --purple: #8B7EC8;
            --magenta: #CE5D97;
            --red: #D14D41;
            --yellow: #D0A215;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--tx);
            min-height: 100vh;
            padding: 2rem;
        }
        .container { max-width: 800px; margin: 0 auto; }
        h1 {
            font-size: 1.5rem;
            margin-bottom: 0.5rem;
            color: var(--tx);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        h1::before { content: ""; }
        .subtitle { color: var(--tx-2); margin-bottom: 2rem; font-size: 0.9rem; }
        .section {
            background: var(--bg-2);
            border-radius: 8px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        }
        .section-title {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--tx-2);
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .form-group {
            margin-bottom: 1rem;
        }
        .form-group:last-child { margin-bottom: 0; }
        label {
            display: block;
            font-size: 0.9rem;
            color: var(--tx);
            margin-bottom: 0.5rem;
        }
        .hint {
            font-size: 0.75rem;
            color: var(--tx-3);
            margin-top: 0.25rem;
        }
        input[type="text"], input[type="password"], select {
            width: 100%;
            padding: 0.75rem;
            background: var(--ui);
            border: 1px solid var(--ui-2);
            border-radius: 6px;
            color: var(--tx);
            font-size: 0.9rem;
        }
        input:focus, select:focus {
            outline: none;
            border-color: var(--orange);
        }
        input::placeholder { color: var(--tx-3); }
        .checkbox-group {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        input[type="checkbox"] {
            width: 1.25rem;
            height: 1.25rem;
            accent-color: var(--orange);
        }
        .checkbox-label {
            font-size: 0.9rem;
            color: var(--tx);
        }
        .grid-2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 1rem;
        }
        @media (max-width: 600px) {
            .grid-2 { grid-template-columns: 1fr; }
        }
        .color-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 0.5rem;
        }
        .color-option {
            padding: 0.5rem;
            border: 2px solid transparent;
            border-radius: 6px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: var(--ui);
            transition: border-color 0.2s;
        }
        .color-option:hover { border-color: var(--ui-3); }
        .color-option.selected { border-color: var(--orange); }
        .color-swatch {
            width: 1.25rem;
            height: 1.25rem;
            border-radius: 50%;
        }
        .color-name { font-size: 0.8rem; color: var(--tx-2); }
        .btn-group {
            display: flex;
            gap: 1rem;
            margin-top: 2rem;
        }
        .btn {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 6px;
            font-size: 0.9rem;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.9; }
        .btn-primary {
            background: var(--orange);
            color: #fff;
        }
        .btn-secondary {
            background: var(--ui-2);
            color: var(--tx);
        }
        .status {
            padding: 0.75rem 1rem;
            border-radius: 6px;
            margin-bottom: 1rem;
            display: none;
        }
        .status.success { display: block; background: rgba(135, 154, 57, 0.2); color: var(--green); }
        .status.error { display: block; background: rgba(209, 77, 65, 0.2); color: var(--red); }
        .dictionary-entry {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
            align-items: center;
        }
        .dictionary-entry input { flex: 1; }
        .btn-icon {
            width: 2.5rem;
            height: 2.5rem;
            padding: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
        }
        .dictionary-list {
            max-height: 300px;
            overflow-y: auto;
            margin-bottom: 1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Dicton Configuration</h1>
        <p class="subtitle">Voice-to-text dictation settings</p>

        <div id="status" class="status"></div>

        <div class="section">
            <div class="section-title">API Keys</div>
            <div class="form-group">
                <label>ElevenLabs API Key</label>
                <input type="password" id="elevenlabs_api_key" placeholder="Enter your ElevenLabs API key">
                <div class="hint">Required for speech-to-text. Get it from elevenlabs.io</div>
            </div>
            <div class="grid-2">
                <div class="form-group">
                    <label>Gemini API Key</label>
                    <input type="password" id="gemini_api_key" placeholder="Gemini API key (optional)">
                </div>
                <div class="form-group">
                    <label>Anthropic API Key</label>
                    <input type="password" id="anthropic_api_key" placeholder="Anthropic API key (optional)">
                </div>
            </div>
            <div class="form-group">
                <label>LLM Provider</label>
                <select id="llm_provider">
                    <option value="gemini">Gemini (default)</option>
                    <option value="anthropic">Anthropic</option>
                </select>
                <div class="hint">Primary provider for reformulation and translation</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Visualizer</div>
            <div class="form-group">
                <label>Theme Color</label>
                <div class="color-grid" id="color-grid">
                    <div class="color-option" data-color="orange">
                        <div class="color-swatch" style="background: #DA702C"></div>
                        <span class="color-name">Orange</span>
                    </div>
                    <div class="color-option" data-color="green">
                        <div class="color-swatch" style="background: #879A39"></div>
                        <span class="color-name">Green</span>
                    </div>
                    <div class="color-option" data-color="cyan">
                        <div class="color-swatch" style="background: #3AA99F"></div>
                        <span class="color-name">Cyan</span>
                    </div>
                    <div class="color-option" data-color="blue">
                        <div class="color-swatch" style="background: #4385BE"></div>
                        <span class="color-name">Blue</span>
                    </div>
                    <div class="color-option" data-color="purple">
                        <div class="color-swatch" style="background: #8B7EC8"></div>
                        <span class="color-name">Purple</span>
                    </div>
                    <div class="color-option" data-color="magenta">
                        <div class="color-swatch" style="background: #CE5D97"></div>
                        <span class="color-name">Magenta</span>
                    </div>
                    <div class="color-option" data-color="red">
                        <div class="color-swatch" style="background: #D14D41"></div>
                        <span class="color-name">Red</span>
                    </div>
                    <div class="color-option" data-color="yellow">
                        <div class="color-swatch" style="background: #D0A215"></div>
                        <span class="color-name">Yellow</span>
                    </div>
                </div>
            </div>
            <div class="grid-2">
                <div class="form-group">
                    <label>Style</label>
                    <select id="visualizer_style">
                        <option value="toric">Toric Ring (default)</option>
                        <option value="minimalistic">Minimalistic</option>
                        <option value="classic">Classic</option>
                        <option value="legacy">Legacy</option>
                        <option value="terminal">Terminal</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Position</label>
                    <select id="animation_position">
                        <option value="top-right">Top Right</option>
                        <option value="top-left">Top Left</option>
                        <option value="top-center">Top Center</option>
                        <option value="bottom-right">Bottom Right</option>
                        <option value="bottom-left">Bottom Left</option>
                        <option value="bottom-center">Bottom Center</option>
                        <option value="center">Center</option>
                        <option value="center-upper">Center Upper</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label>Backend</label>
                <select id="visualizer_backend">
                    <option value="pygame">PyGame (default)</option>
                    <option value="vispy">VisPy (OpenGL)</option>
                    <option value="gtk">GTK (Cairo)</option>
                </select>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Hotkey Settings</div>
            <div class="form-group">
                <label>Base Hotkey</label>
                <select id="hotkey_base">
                    <option value="fn">FN Key (recommended)</option>
                    <option value="alt+g">Alt+G (legacy)</option>
                </select>
            </div>
            <div class="grid-2">
                <div class="form-group">
                    <label>Hold Threshold (ms)</label>
                    <input type="text" id="hotkey_hold_threshold_ms" placeholder="100">
                    <div class="hint">Press longer than this = push-to-talk</div>
                </div>
                <div class="form-group">
                    <label>Double-tap Window (ms)</label>
                    <input type="text" id="hotkey_double_tap_window_ms" placeholder="300">
                    <div class="hint">Second press within this = toggle mode</div>
                </div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Processing</div>
            <div class="grid-2">
                <div class="form-group">
                    <div class="checkbox-group">
                        <input type="checkbox" id="filter_fillers">
                        <label class="checkbox-label">Filter Filler Words</label>
                    </div>
                    <div class="hint">Remove um, uh, like, etc.</div>
                </div>
                <div class="form-group">
                    <div class="checkbox-group">
                        <input type="checkbox" id="enable_reformulation">
                        <label class="checkbox-label">Enable LLM Reformulation</label>
                    </div>
                    <div class="hint">Use LLM for text cleanup</div>
                </div>
            </div>
            <div class="form-group">
                <label>Language</label>
                <select id="language">
                    <option value="auto">Auto-detect</option>
                    <option value="en">English</option>
                    <option value="fr">French</option>
                    <option value="de">German</option>
                    <option value="es">Spanish</option>
                    <option value="it">Italian</option>
                    <option value="pt">Portuguese</option>
                    <option value="nl">Dutch</option>
                    <option value="pl">Polish</option>
                    <option value="ru">Russian</option>
                    <option value="ja">Japanese</option>
                    <option value="zh">Chinese</option>
                    <option value="ko">Korean</option>
                </select>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Dictionary</div>
            <div class="hint" style="margin-bottom: 1rem">Custom word replacements. Changes are saved automatically.</div>
            <div class="dictionary-list" id="dictionary-list"></div>
            <div class="dictionary-entry">
                <input type="text" id="new-from" placeholder="Original word">
                <input type="text" id="new-to" placeholder="Replacement">
                <button class="btn btn-secondary btn-icon" onclick="addDictionaryEntry()">+</button>
            </div>
        </div>

        <div class="section">
            <div class="section-title">Debug</div>
            <div class="checkbox-group">
                <input type="checkbox" id="debug">
                <label class="checkbox-label">Enable Debug Mode</label>
            </div>
            <div class="hint">Show latency info and detailed logs</div>
        </div>

        <div class="btn-group">
            <button class="btn btn-primary" onclick="saveConfig()">Save Configuration</button>
            <button class="btn btn-secondary" onclick="loadConfig()">Reset to Current</button>
        </div>
    </div>

    <script>
        const API_BASE = '';

        let currentConfig = {};
        let dictionary = {};

        async function loadConfig() {
            try {
                const res = await fetch(API_BASE + '/api/config');
                currentConfig = await res.json();
                populateForm(currentConfig);
                await loadDictionary();
            } catch (e) {
                showStatus('Failed to load configuration', 'error');
            }
        }

        async function loadDictionary() {
            try {
                const res = await fetch(API_BASE + '/api/dictionary');
                dictionary = await res.json();
                renderDictionary();
            } catch (e) {
                dictionary = { replacements: {}, case_sensitive: {} };
                renderDictionary();
            }
        }

        function renderDictionary() {
            const list = document.getElementById('dictionary-list');
            list.innerHTML = '';

            const all = { ...dictionary.replacements, ...dictionary.case_sensitive };
            for (const [from, to] of Object.entries(all)) {
                if (from.startsWith('_')) continue;
                const entry = document.createElement('div');
                entry.className = 'dictionary-entry';
                entry.innerHTML = `
                    <input type="text" value="${escapeHtml(from)}" readonly>
                    <input type="text" value="${escapeHtml(to)}" readonly>
                    <button class="btn btn-secondary btn-icon" onclick="removeDictionaryEntry('${escapeHtml(from)}')">-</button>
                `;
                list.appendChild(entry);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML.replace(/"/g, '&quot;');
        }

        async function addDictionaryEntry() {
            const from = document.getElementById('new-from').value.trim();
            const to = document.getElementById('new-to').value.trim();
            if (!from || !to) return;

            try {
                await fetch(API_BASE + '/api/dictionary', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ from, to })
                });
                document.getElementById('new-from').value = '';
                document.getElementById('new-to').value = '';
                await loadDictionary();
                showStatus('Dictionary entry added', 'success');
            } catch (e) {
                showStatus('Failed to add entry', 'error');
            }
        }

        async function removeDictionaryEntry(from) {
            try {
                await fetch(API_BASE + '/api/dictionary', {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ from })
                });
                await loadDictionary();
                showStatus('Dictionary entry removed', 'success');
            } catch (e) {
                showStatus('Failed to remove entry', 'error');
            }
        }

        function populateForm(cfg) {
            document.getElementById('elevenlabs_api_key').value = cfg.elevenlabs_api_key || '';
            document.getElementById('gemini_api_key').value = cfg.gemini_api_key || '';
            document.getElementById('anthropic_api_key').value = cfg.anthropic_api_key || '';
            document.getElementById('llm_provider').value = cfg.llm_provider || 'gemini';
            document.getElementById('visualizer_style').value = cfg.visualizer_style || 'toric';
            document.getElementById('animation_position').value = cfg.animation_position || 'top-right';
            document.getElementById('visualizer_backend').value = cfg.visualizer_backend || 'pygame';
            document.getElementById('hotkey_base').value = cfg.hotkey_base || 'fn';
            document.getElementById('hotkey_hold_threshold_ms').value = cfg.hotkey_hold_threshold_ms || '100';
            document.getElementById('hotkey_double_tap_window_ms').value = cfg.hotkey_double_tap_window_ms || '300';
            document.getElementById('filter_fillers').checked = cfg.filter_fillers !== false;
            document.getElementById('enable_reformulation').checked = cfg.enable_reformulation !== false;
            document.getElementById('language').value = cfg.language || 'auto';
            document.getElementById('debug').checked = cfg.debug === true;

            // Update color selection
            document.querySelectorAll('.color-option').forEach(el => {
                el.classList.toggle('selected', el.dataset.color === (cfg.theme_color || 'orange'));
            });
        }

        function getFormData() {
            return {
                elevenlabs_api_key: document.getElementById('elevenlabs_api_key').value,
                gemini_api_key: document.getElementById('gemini_api_key').value,
                anthropic_api_key: document.getElementById('anthropic_api_key').value,
                llm_provider: document.getElementById('llm_provider').value,
                theme_color: document.querySelector('.color-option.selected')?.dataset.color || 'orange',
                visualizer_style: document.getElementById('visualizer_style').value,
                animation_position: document.getElementById('animation_position').value,
                visualizer_backend: document.getElementById('visualizer_backend').value,
                hotkey_base: document.getElementById('hotkey_base').value,
                hotkey_hold_threshold_ms: document.getElementById('hotkey_hold_threshold_ms').value,
                hotkey_double_tap_window_ms: document.getElementById('hotkey_double_tap_window_ms').value,
                filter_fillers: document.getElementById('filter_fillers').checked,
                enable_reformulation: document.getElementById('enable_reformulation').checked,
                language: document.getElementById('language').value,
                debug: document.getElementById('debug').checked
            };
        }

        async function saveConfig() {
            try {
                const data = getFormData();
                const res = await fetch(API_BASE + '/api/config', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(data)
                });
                if (res.ok) {
                    showStatus('Configuration saved! Restart Dicton to apply changes.', 'success');
                } else {
                    showStatus('Failed to save configuration', 'error');
                }
            } catch (e) {
                showStatus('Failed to save configuration', 'error');
            }
        }

        function showStatus(message, type) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = 'status ' + type;
            setTimeout(() => { status.className = 'status'; }, 5000);
        }

        // Color selection
        document.getElementById('color-grid').addEventListener('click', (e) => {
            const option = e.target.closest('.color-option');
            if (option) {
                document.querySelectorAll('.color-option').forEach(el => el.classList.remove('selected'));
                option.classList.add('selected');
            }
        });

        // Load config on page load
        loadConfig();
    </script>
</body>
</html>
"""


def get_env_path() -> Path:
    """Get the .env file path (user config dir)."""
    return Config.CONFIG_DIR / ".env"


def read_env_file() -> dict[str, str]:
    """Read the .env file and return as dict."""
    env_path = get_env_path()
    if not env_path.exists():
        return {}

    env_vars: dict[str, str] = {}
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                # Strip quotes from value
                value = value.strip().strip("\"'")
                env_vars[key.strip()] = value

    return env_vars


def write_env_file(env_vars: dict[str, str]) -> None:
    """Write env vars to .env file."""
    env_path = get_env_path()
    env_path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["# Dicton configuration", "# Generated by dicton --config-ui", ""]

    for key, value in sorted(env_vars.items()):
        # Quote values with spaces
        if " " in value or not value:
            value = f'"{value}"'
        lines.append(f"{key}={value}")

    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def get_current_config() -> dict[str, Any]:
    """Get current configuration as dict."""
    env_vars = read_env_file()

    return {
        "elevenlabs_api_key": env_vars.get("ELEVENLABS_API_KEY", ""),
        "gemini_api_key": env_vars.get("GEMINI_API_KEY", ""),
        "anthropic_api_key": env_vars.get("ANTHROPIC_API_KEY", ""),
        "llm_provider": env_vars.get("LLM_PROVIDER", config.LLM_PROVIDER),
        "theme_color": env_vars.get("THEME_COLOR", config.THEME_COLOR),
        "visualizer_style": env_vars.get("VISUALIZER_STYLE", config.VISUALIZER_STYLE),
        "animation_position": env_vars.get("ANIMATION_POSITION", config.ANIMATION_POSITION),
        "visualizer_backend": env_vars.get("VISUALIZER_BACKEND", config.VISUALIZER_BACKEND),
        "hotkey_base": env_vars.get("HOTKEY_BASE", config.HOTKEY_BASE),
        "hotkey_hold_threshold_ms": env_vars.get(
            "HOTKEY_HOLD_THRESHOLD_MS", str(config.HOTKEY_HOLD_THRESHOLD_MS)
        ),
        "hotkey_double_tap_window_ms": env_vars.get(
            "HOTKEY_DOUBLE_TAP_WINDOW_MS", str(config.HOTKEY_DOUBLE_TAP_WINDOW_MS)
        ),
        "filter_fillers": env_vars.get("FILTER_FILLERS", "true").lower() == "true",
        "enable_reformulation": env_vars.get("ENABLE_REFORMULATION", "true").lower() == "true",
        "language": env_vars.get("LANGUAGE", config.LANGUAGE),
        "debug": env_vars.get("DEBUG", "false").lower() == "true",
    }


def save_config(data: dict[str, Any]) -> None:
    """Save configuration to .env file."""
    env_vars = read_env_file()

    # Map UI fields to env vars
    field_map = {
        "elevenlabs_api_key": "ELEVENLABS_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "llm_provider": "LLM_PROVIDER",
        "theme_color": "THEME_COLOR",
        "visualizer_style": "VISUALIZER_STYLE",
        "animation_position": "ANIMATION_POSITION",
        "visualizer_backend": "VISUALIZER_BACKEND",
        "hotkey_base": "HOTKEY_BASE",
        "hotkey_hold_threshold_ms": "HOTKEY_HOLD_THRESHOLD_MS",
        "hotkey_double_tap_window_ms": "HOTKEY_DOUBLE_TAP_WINDOW_MS",
        "filter_fillers": "FILTER_FILLERS",
        "enable_reformulation": "ENABLE_REFORMULATION",
        "language": "LANGUAGE",
        "debug": "DEBUG",
    }

    for ui_field, env_var in field_map.items():
        if ui_field in data:
            value = data[ui_field]
            if isinstance(value, bool):
                value = "true" if value else "false"
            env_vars[env_var] = str(value)

    write_env_file(env_vars)


def get_dictionary() -> dict[str, Any]:
    """Get dictionary contents."""
    dictionary_path = Config.CONFIG_DIR / "dictionary.json"
    if not dictionary_path.exists():
        return {"replacements": {}, "case_sensitive": {}, "patterns": []}

    try:
        with open(dictionary_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"replacements": {}, "case_sensitive": {}, "patterns": []}


def save_dictionary(data: dict[str, Any]) -> None:
    """Save dictionary to file."""
    dictionary_path = Config.CONFIG_DIR / "dictionary.json"
    dictionary_path.parent.mkdir(parents=True, exist_ok=True)

    with open(dictionary_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_dictionary_entry(from_word: str, to_word: str) -> None:
    """Add a dictionary entry."""
    data = get_dictionary()
    data["replacements"][from_word] = to_word
    save_dictionary(data)


def remove_dictionary_entry(from_word: str) -> None:
    """Remove a dictionary entry."""
    data = get_dictionary()
    if from_word in data.get("replacements", {}):
        del data["replacements"][from_word]
    if from_word in data.get("case_sensitive", {}):
        del data["case_sensitive"][from_word]
    save_dictionary(data)


def create_app():
    """Create FastAPI application."""
    try:
        from fastapi import FastAPI
        from fastapi.responses import HTMLResponse, JSONResponse
        from pydantic import BaseModel
    except ImportError as e:
        raise ImportError(
            "FastAPI not installed. Install with: pip install dicton[configui]"
        ) from e

    app = FastAPI(title="Dicton Configuration")

    class ConfigData(BaseModel):
        elevenlabs_api_key: str | None = None
        gemini_api_key: str | None = None
        anthropic_api_key: str | None = None
        llm_provider: str | None = None
        theme_color: str | None = None
        visualizer_style: str | None = None
        animation_position: str | None = None
        visualizer_backend: str | None = None
        hotkey_base: str | None = None
        hotkey_hold_threshold_ms: str | None = None
        hotkey_double_tap_window_ms: str | None = None
        filter_fillers: bool | None = None
        enable_reformulation: bool | None = None
        language: str | None = None
        debug: bool | None = None

    class DictionaryEntry(BaseModel):
        from_: str | None = None
        to: str | None = None

        class Config:
            populate_by_name = True
            extra = "allow"

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTML_TEMPLATE

    @app.get("/api/config")
    async def api_get_config():
        return JSONResponse(get_current_config())

    @app.post("/api/config")
    async def api_save_config(data: ConfigData):
        save_config(data.model_dump(exclude_none=True))
        return {"status": "ok"}

    @app.get("/api/dictionary")
    async def api_get_dictionary():
        return JSONResponse(get_dictionary())

    @app.post("/api/dictionary")
    async def api_add_dictionary_entry(data: dict):
        from_word = data.get("from", "")
        to_word = data.get("to", "")
        if from_word and to_word:
            add_dictionary_entry(from_word, to_word)
            return {"status": "ok"}
        return JSONResponse({"error": "Missing from/to"}, status_code=400)

    @app.delete("/api/dictionary")
    async def api_remove_dictionary_entry(data: dict):
        from_word = data.get("from", "")
        if from_word:
            remove_dictionary_entry(from_word)
            return {"status": "ok"}
        return JSONResponse({"error": "Missing from"}, status_code=400)

    return app


def run_config_server(port: int = 9876, open_browser: bool = True) -> None:
    """Run the configuration server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed.")
        print("Install with: pip install dicton[configui]")
        return

    app = create_app()

    print(f"\n{'='*50}")
    print("Dicton Configuration UI")
    print(f"{'='*50}")
    print(f"Open: http://localhost:{port}")
    print("Press Ctrl+C to stop")
    print(f"{'='*50}\n")

    if open_browser:
        Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
