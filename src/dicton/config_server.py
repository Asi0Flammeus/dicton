"""Configuration web UI server for Dicton."""

import json
import webbrowser
from pathlib import Path
from threading import Timer
from typing import Any

from .config import Config, config

# Small logo as base64 (200x66 resized)
LOGO_BASE64 = "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45S//zTf/+V/+1//6zHA4PHnHKZ///F994xs3zszMiLUh0GjUgrIkUGHVEhqnc6i0Wq0sy1Z6y2U5XjqydM873z0/t7Dp+GccPnLo9Zdfdujg4Ve/+nW7n3rqtNNO/dSn/uSmm771pf/91+94xx8c2L//ve99z4++/5M3X3n15Zddum7t2uOPO+6nt9z6pje/5TWvedX69evVpwIAYdAfnn76KW9/+++8/fd/98wzz1zpLT372ef+/jt+9x3v+L2tJ24ZT8bGcMgiVaxccP5zv/iFL5cTe/KO7aR08sk73vWu/3brrbe98Y1vWDq6DBi1BOKjR5YuuuiF20866ZprrplbM/+GK15PROs3bMjyLM+yo0eXL73stSLyrj9498UvfdmvXnTR3Nz8N75xw+Lioe997/snn7zj0stes7i4+O53vfs1r3nVyTt2bNu6be/eA2+96m2XXHLJ8ccf/553v/eWW378J5/6k/e+9/2ZMSL6Z5/9889//otve9tbJ+PxiSdue/jhR6666m2vfvWrRsPJ3Jq5k07ads45Zy0vLy0eONhoNphhDA8Gw1NPOeVZ5559+eWvv+eX901PzUzGxX+95j2Liwe3bz/p6NKh5z//ec985pmXXnr59773/ec857yv/M1X/uoLX/zed7/75jdd/cjDj83Orrnp29/7w2s/cNZZz7zoohd+8pOfvOGb3/jKV//ut9/2ew8+8OB7/9v7Nm7YuLCwsLK8/M53vP32f7/jta997fOff8HGjes2btzw+BNPXnnlVS+7+OItJ2yejCcgo6JihUj379//8T+6/nOf+/O3vOXKZrN5/vnn33jjTe/7ww/+7u/+NojOOP20z//lFz/0oevedOVvhto0DtXywxitaqZ+7AaBDDs9SXIytapOxpOyLItJOTU1TUqjwbjXGxRlSVS2Ws2f//xutbj22g+sW7tehQmZLXU8LBqNnMF33Xnn4sF9jzz84Lp1a5eWlvfu2Tcajg4sHmw2mv3ewBg3gJVB1Gw0Z9fMEmmjkVuRdqczvzBHSlmWiTvGSiyRktWp7tR55z17enr27LPP/tkdd97609see+zR5eWjO3fuOvnkHSYI09RSLctGnovoW9/61kcfeez+Bx5s5E1SHQ6H41FhTJaZfHpq5i1vect3bvrO7t17iqKcjCfD4bDXW1GVbqfb6Fbkum5uOHr06MzM9HAw1Jm5o2lINlZqKEqrHXbbeyPZx9/66b8/Z6ty14sAAAAASUVORK5CYII="

# HTML template with dashboard
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dicton Dashboard</title>
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
        .container { max-width: 900px; margin: 0 auto; }
        .header {
            display: flex;
            align-items: center;
            gap: 1.5rem;
            margin-bottom: 2rem;
        }
        .logo { height: 50px; }
        .header-text h1 {
            font-size: 1.5rem;
            color: var(--tx);
            font-weight: 600;
        }
        .subtitle { color: var(--tx-2); font-size: 0.9rem; }
        .tabs {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid var(--ui-2);
            padding-bottom: 0.5rem;
        }
        .tab {
            padding: 0.5rem 1rem;
            background: transparent;
            border: none;
            color: var(--tx-2);
            cursor: pointer;
            border-radius: 6px 6px 0 0;
            font-size: 0.9rem;
            transition: all 0.2s;
        }
        .tab:hover { color: var(--tx); background: var(--ui); }
        .tab.active { color: var(--orange); background: var(--ui); }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
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
        .form-group { margin-bottom: 1rem; }
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
        .input-with-status {
            position: relative;
        }
        .input-status {
            position: absolute;
            right: 12px;
            top: 50%;
            transform: translateY(-50%);
            font-size: 0.75rem;
            padding: 2px 8px;
            border-radius: 4px;
        }
        .input-status.set {
            background: rgba(135, 154, 57, 0.2);
            color: var(--green);
        }
        .input-status.not-set {
            background: rgba(87, 86, 83, 0.3);
            color: var(--tx-3);
        }
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
            margin-top: 1.5rem;
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
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .btn-primary { background: var(--orange); color: #fff; }
        .btn-secondary { background: var(--ui-2); color: var(--tx); }
        .btn-large {
            padding: 1rem 2rem;
            font-size: 1rem;
        }
        .status {
            padding: 0.75rem 1rem;
            border-radius: 6px;
            margin-bottom: 1rem;
            display: none;
        }
        .status.success { display: block; background: rgba(135, 154, 57, 0.2); color: var(--green); }
        .status.error { display: block; background: rgba(209, 77, 65, 0.2); color: var(--red); }
        .status.info { display: block; background: rgba(67, 133, 190, 0.2); color: var(--blue); }
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
            max-height: 200px;
            overflow-y: auto;
            margin-bottom: 1rem;
        }
        /* Latency Test Panel */
        .test-panel {
            text-align: center;
            padding: 2rem;
        }
        .test-btn {
            width: 120px;
            height: 120px;
            border-radius: 50%;
            font-size: 1rem;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            margin: 0 auto 2rem;
        }
        .test-btn .icon { font-size: 2rem; }
        .test-btn.recording {
            background: var(--red);
            animation: pulse 1s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); }
            50% { transform: scale(1.05); }
        }
        .test-status {
            font-size: 1.1rem;
            color: var(--tx-2);
            margin-bottom: 1.5rem;
        }
        .latency-results {
            display: none;
            text-align: left;
            margin-top: 1.5rem;
        }
        .latency-results.show { display: block; }
        .latency-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.75rem 1rem;
            background: var(--ui);
            border-radius: 6px;
            margin-bottom: 0.5rem;
        }
        .latency-label { color: var(--tx-2); }
        .latency-value {
            font-family: monospace;
            font-size: 1rem;
            color: var(--orange);
        }
        .latency-total {
            background: var(--ui-2);
            font-weight: bold;
        }
        .latency-total .latency-value { color: var(--green); font-size: 1.1rem; }
        .transcription-result {
            margin-top: 1.5rem;
            padding: 1rem;
            background: var(--ui);
            border-radius: 6px;
            text-align: left;
            display: none;
        }
        .transcription-result.show { display: block; }
        .transcription-label {
            font-size: 0.8rem;
            color: var(--tx-3);
            margin-bottom: 0.5rem;
        }
        .transcription-text {
            font-size: 1rem;
            color: var(--tx);
            line-height: 1.5;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <img src="data:image/png;base64,""" + LOGO_BASE64 + """" alt="Dicton" class="logo">
            <div class="header-text">
                <h1>Dicton Dashboard</h1>
                <p class="subtitle">Voice-to-text dictation</p>
            </div>
        </div>

        <div class="tabs">
            <button class="tab active" onclick="switchTab('test')">Latency Test</button>
            <button class="tab" onclick="switchTab('config')">Configuration</button>
            <button class="tab" onclick="switchTab('dictionary')">Dictionary</button>
        </div>

        <div id="status" class="status"></div>

        <!-- Latency Test Tab -->
        <div id="tab-test" class="tab-content active">
            <div class="section test-panel">
                <button id="test-btn" class="btn btn-primary test-btn" onclick="toggleTest()">
                    <span class="icon">🎤</span>
                    <span id="test-btn-text">Start Test</span>
                </button>
                <div id="test-status" class="test-status">Click to start a transcription test</div>

                <div id="latency-results" class="latency-results">
                    <div class="latency-item">
                        <span class="latency-label">Recording</span>
                        <span id="lat-recording" class="latency-value">--</span>
                    </div>
                    <div class="latency-item">
                        <span class="latency-label">STT (ElevenLabs)</span>
                        <span id="lat-stt" class="latency-value">--</span>
                    </div>
                    <div class="latency-item">
                        <span class="latency-label">LLM Processing</span>
                        <span id="lat-llm" class="latency-value">--</span>
                    </div>
                    <div class="latency-item latency-total">
                        <span class="latency-label">Total</span>
                        <span id="lat-total" class="latency-value">--</span>
                    </div>
                </div>

                <div id="transcription-result" class="transcription-result">
                    <div class="transcription-label">Transcription Result</div>
                    <div id="transcription-text" class="transcription-text"></div>
                </div>
            </div>
        </div>

        <!-- Configuration Tab -->
        <div id="tab-config" class="tab-content">
            <div class="section">
                <div class="section-title">API Keys</div>
                <div class="form-group">
                    <label>ElevenLabs API Key</label>
                    <div class="input-with-status">
                        <input type="password" id="elevenlabs_api_key" placeholder="Enter your ElevenLabs API key">
                        <span id="elevenlabs-status" class="input-status not-set">Not Set</span>
                    </div>
                    <div class="hint">Required for speech-to-text. Get it from elevenlabs.io</div>
                </div>
                <div class="grid-2">
                    <div class="form-group">
                        <label>Gemini API Key</label>
                        <div class="input-with-status">
                            <input type="password" id="gemini_api_key" placeholder="Gemini API key">
                            <span id="gemini-status" class="input-status not-set">Not Set</span>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Anthropic API Key</label>
                        <div class="input-with-status">
                            <input type="password" id="anthropic_api_key" placeholder="Anthropic API key">
                            <span id="anthropic-status" class="input-status not-set">Not Set</span>
                        </div>
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
                            <option value="toric">Toric Ring</option>
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
                        <option value="pygame">PyGame</option>
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
                        <option value="fn">FN Key</option>
                        <option value="alt+g">Alt+G (legacy)</option>
                    </select>
                </div>
                <div class="grid-2">
                    <div class="form-group">
                        <label>Hold Threshold (ms)</label>
                        <input type="text" id="hotkey_hold_threshold_ms" placeholder="100">
                        <div class="hint">Press longer = push-to-talk</div>
                    </div>
                    <div class="form-group">
                        <label>Double-tap Window (ms)</label>
                        <input type="text" id="hotkey_double_tap_window_ms" placeholder="300">
                        <div class="hint">Second press within = toggle</div>
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

        <!-- Dictionary Tab -->
        <div id="tab-dictionary" class="tab-content">
            <div class="section">
                <div class="section-title">Custom Dictionary</div>
                <div class="hint" style="margin-bottom: 1rem">Custom word replacements. Changes are saved automatically.</div>
                <div class="dictionary-list" id="dictionary-list"></div>
                <div class="dictionary-entry">
                    <input type="text" id="new-from" placeholder="Original word">
                    <input type="text" id="new-to" placeholder="Replacement">
                    <button class="btn btn-secondary btn-icon" onclick="addDictionaryEntry()">+</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = '';
        let currentConfig = {};
        let dictionary = {};
        let isRecording = false;
        let testAbortController = null;

        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
            document.getElementById(`tab-${tabName}`).classList.add('active');
        }

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
                    <button class="btn btn-secondary btn-icon" onclick="removeDictionaryEntry('${escapeHtml(from)}')">−</button>
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

        function updateApiKeyStatus(id, hasValue) {
            const statusEl = document.getElementById(id + '-status');
            if (hasValue) {
                statusEl.textContent = 'Set';
                statusEl.className = 'input-status set';
            } else {
                statusEl.textContent = 'Not Set';
                statusEl.className = 'input-status not-set';
            }
        }

        function populateForm(cfg) {
            // API keys - show masked if set, empty if not
            const elevenlabsSet = cfg.elevenlabs_api_key_set || false;
            const geminiSet = cfg.gemini_api_key_set || false;
            const anthropicSet = cfg.anthropic_api_key_set || false;

            document.getElementById('elevenlabs_api_key').value = elevenlabsSet ? '••••••••••••••••' : '';
            document.getElementById('gemini_api_key').value = geminiSet ? '••••••••••••••••' : '';
            document.getElementById('anthropic_api_key').value = anthropicSet ? '••••••••••••••••' : '';

            updateApiKeyStatus('elevenlabs', elevenlabsSet);
            updateApiKeyStatus('gemini', geminiSet);
            updateApiKeyStatus('anthropic', anthropicSet);

            // Other values
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
            const data = {
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

            // Only include API keys if they were changed (not masked)
            const elevenlabs = document.getElementById('elevenlabs_api_key').value;
            const gemini = document.getElementById('gemini_api_key').value;
            const anthropic = document.getElementById('anthropic_api_key').value;

            if (elevenlabs && !elevenlabs.startsWith('••')) data.elevenlabs_api_key = elevenlabs;
            if (gemini && !gemini.startsWith('••')) data.gemini_api_key = gemini;
            if (anthropic && !anthropic.startsWith('••')) data.anthropic_api_key = anthropic;

            return data;
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
                    loadConfig(); // Reload to update statuses
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

        // Latency test functions
        async function toggleTest() {
            if (isRecording) {
                stopTest();
            } else {
                startTest();
            }
        }

        async function startTest() {
            const btn = document.getElementById('test-btn');
            const btnText = document.getElementById('test-btn-text');
            const status = document.getElementById('test-status');
            const results = document.getElementById('latency-results');
            const transcription = document.getElementById('transcription-result');

            isRecording = true;
            btn.classList.add('recording');
            btnText.textContent = 'Stop';
            status.textContent = '🎤 Recording... Click to stop';
            results.classList.remove('show');
            transcription.classList.remove('show');

            // Reset latency values
            document.getElementById('lat-recording').textContent = '--';
            document.getElementById('lat-stt').textContent = '--';
            document.getElementById('lat-llm').textContent = '--';
            document.getElementById('lat-total').textContent = '--';

            testAbortController = new AbortController();

            try {
                const res = await fetch(API_BASE + '/api/test/start', {
                    method: 'POST',
                    signal: testAbortController.signal
                });
                const data = await res.json();

                if (data.status === 'recording') {
                    status.textContent = '🎤 Recording... Click to stop';
                }
            } catch (e) {
                if (e.name !== 'AbortError') {
                    showStatus('Failed to start test: ' + e.message, 'error');
                    resetTestUI();
                }
            }
        }

        async function stopTest() {
            const btn = document.getElementById('test-btn');
            const btnText = document.getElementById('test-btn-text');
            const status = document.getElementById('test-status');

            btn.classList.remove('recording');
            btnText.textContent = 'Processing...';
            btn.disabled = true;
            status.textContent = '⏳ Processing transcription...';

            try {
                const res = await fetch(API_BASE + '/api/test/stop', { method: 'POST' });
                const data = await res.json();

                if (data.error) {
                    showStatus(data.error, 'error');
                    resetTestUI();
                    return;
                }

                // Show results
                showTestResults(data);
            } catch (e) {
                showStatus('Test failed: ' + e.message, 'error');
                resetTestUI();
            }
        }

        function showTestResults(data) {
            const results = document.getElementById('latency-results');
            const transcription = document.getElementById('transcription-result');
            const status = document.getElementById('test-status');

            // Update latency values
            document.getElementById('lat-recording').textContent = formatMs(data.latency?.recording);
            document.getElementById('lat-stt').textContent = formatMs(data.latency?.stt);
            document.getElementById('lat-llm').textContent = formatMs(data.latency?.llm);
            document.getElementById('lat-total').textContent = formatMs(data.latency?.total);

            results.classList.add('show');

            // Show transcription
            if (data.text) {
                document.getElementById('transcription-text').textContent = data.text;
                transcription.classList.add('show');
            }

            status.textContent = '✓ Test complete';
            resetTestUI();
        }

        function formatMs(ms) {
            if (ms === undefined || ms === null) return '--';
            return ms.toFixed(0) + ' ms';
        }

        function resetTestUI() {
            const btn = document.getElementById('test-btn');
            const btnText = document.getElementById('test-btn-text');

            isRecording = false;
            btn.classList.remove('recording');
            btn.disabled = false;
            btnText.textContent = 'Start Test';
            testAbortController = null;
        }

        // Clear API key field when focused (to allow entering new value)
        ['elevenlabs_api_key', 'gemini_api_key', 'anthropic_api_key'].forEach(id => {
            document.getElementById(id).addEventListener('focus', function() {
                if (this.value.startsWith('••')) {
                    this.value = '';
                    this.type = 'text';
                }
            });
            document.getElementById(id).addEventListener('blur', function() {
                this.type = 'password';
            });
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
        # API keys - only indicate if set, don't expose values
        "elevenlabs_api_key_set": bool(env_vars.get("ELEVENLABS_API_KEY", "")),
        "gemini_api_key_set": bool(env_vars.get("GEMINI_API_KEY", "")),
        "anthropic_api_key_set": bool(env_vars.get("ANTHROPIC_API_KEY", "")),
        # Other config values
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


# Test recording state
_test_state = {
    "recording": False,
    "audio_data": None,
    "start_time": None,
}


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

    app = FastAPI(title="Dicton Dashboard")

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

    @app.post("/api/test/start")
    async def api_test_start():
        """Start recording for latency test."""
        import time

        _test_state["recording"] = True
        _test_state["audio_data"] = None
        _test_state["start_time"] = time.time()
        return {"status": "recording"}

    @app.post("/api/test/stop")
    async def api_test_stop():
        """Stop recording and run transcription test."""
        import time

        if not _test_state["recording"]:
            return JSONResponse({"error": "Not recording"}, status_code=400)

        _test_state["recording"] = False
        record_end_time = time.time()
        record_duration = (record_end_time - _test_state["start_time"]) * 1000

        # Run actual transcription test
        try:
            result = run_transcription_test(record_duration)
            return JSONResponse(result)
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    return app


def run_transcription_test(record_duration_ms: float) -> dict[str, Any]:
    """Run a transcription test and return timing data."""
    import time

    from .speech_recognition_engine import SpeechRecognizer

    result = {
        "latency": {
            "recording": record_duration_ms,
            "stt": 0,
            "llm": 0,
            "total": 0,
        },
        "text": "",
    }

    try:
        recognizer = SpeechRecognizer()

        # Record audio (simulated with short duration for test)
        record_start = time.time()
        audio = recognizer.record_for_duration(min(record_duration_ms / 1000, 5.0))
        record_actual = (time.time() - record_start) * 1000
        result["latency"]["recording"] = record_actual

        if audio is None or len(audio) == 0:
            result["error"] = "No audio captured"
            return result

        # Transcribe
        stt_start = time.time()
        text = recognizer.transcribe(audio)
        result["latency"]["stt"] = (time.time() - stt_start) * 1000

        if not text:
            result["error"] = "No speech detected"
            return result

        # LLM processing (if enabled)
        llm_start = time.time()
        try:
            from . import llm_processor

            if config.ENABLE_REFORMULATION and llm_processor.is_available():
                text = llm_processor.reformulate(text) or text
        except ImportError:
            pass
        result["latency"]["llm"] = (time.time() - llm_start) * 1000

        result["text"] = text
        result["latency"]["total"] = (
            result["latency"]["recording"]
            + result["latency"]["stt"]
            + result["latency"]["llm"]
        )

        recognizer.cleanup()

    except Exception as e:
        result["error"] = str(e)

    return result


def find_available_port(start_port: int = 6873, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    import socket

    for offset in range(max_attempts):
        port = start_port + offset
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue

    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")


def run_config_server(port: int = 6873, open_browser: bool = True) -> None:
    """Run the configuration server."""
    try:
        import uvicorn
    except ImportError:
        print("Error: FastAPI/uvicorn not installed.")
        print("Install with: pip install dicton[configui]")
        return

    # Find available port if requested port is in use
    try:
        actual_port = find_available_port(port)
        if actual_port != port:
            print(f"Port {port} in use, using {actual_port}")
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    app = create_app()

    print(f"\n{'='*50}")
    print("Dicton Dashboard")
    print(f"{'='*50}")
    print(f"Open: http://localhost:{actual_port}")
    print("Press Ctrl+C to stop")
    print(f"{'='*50}\n")

    if open_browser:
        Timer(1.0, lambda: webbrowser.open(f"http://localhost:{actual_port}")).start()

    uvicorn.run(app, host="127.0.0.1", port=actual_port, log_level="warning")
