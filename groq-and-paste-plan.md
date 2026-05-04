# Groq STT + Paste Enhancement Plan

> Two orthogonal latency wins, planned together because they share a release cycle.
> **Instructions only — no code.** Each change says *what*, *where*, and *why*.

Targets:
- **Groq `whisper-large-v3-turbo`** as STT provider — expected 0.3-0.5 s wall-clock for 10-18 s clips (vs 0.6-0.9 s on Voxtral) → ~300-500 ms saved.
- **Drop the clipboard-verify poll loop** + minor `xdotool` tweaks → ~150-250 ms saved.

End-state post-audio cost: **~1.1-1.4 s** (vs ~1.7-2.0 s today on a warm daemon).

---

## Part A — Switch STT to Groq Whisper Large v3 Turbo

### A.0 The API key — what you need

| Item | Value |
|---|---|
| Provider | **Groq Cloud** (the AI inference platform, not the chip company directly) |
| Sign-up URL | `https://console.groq.com` |
| Key type | Personal/org Bearer token, prefix `gsk_…` |
| Plan to use | Free tier is enough for personal dictation (rate-limited but generous on Whisper) — paid only if you hit RPM limits |
| Cost | $0.04/h (vs $0.06/h on Mistral; cheaper) |
| Env var name (proposed) | `GROQ_API_KEY` |

Steps to acquire:
1. Go to `https://console.groq.com`, sign in (Google/GitHub OAuth).
2. **API Keys** → **Create API Key** → name it `dicton`.
3. Copy the `gsk_…` token. It is shown **only once** — save it.
4. Add to `~/.env`: `GROQ_API_KEY=gsk_…` (this works automatically with the `~/.env` cascade we added in 1.13.3).
5. Verify with `curl`:
   ```
   curl -H "Authorization: Bearer $GROQ_API_KEY" https://api.groq.com/openai/v1/models | jq '.data[] | select(.id|contains("whisper")) | .id'
   ```
   Expected: at least `whisper-large-v3-turbo` in the list.

### A.1 Implementation strategy: new provider, not in-place rewrite

**Decision**: add a new `GroqSTTProvider` next to `MistralSTTProvider`, register it in the STT factory, and make it the default. Keep Voxtral around as fallback (already-built switch infrastructure).

**Why a new provider, not editing `mistral.py`**: Groq is OpenAI-compatible (`POST /openai/v1/audio/transcriptions`), Mistral has its own SDK. Mixing them in one file makes both sides messy. Two adapters, one factory, clean.

**Use case it unlocks**: user with a Groq key gets 300-500 ms faster STT. User without falls back to Voxtral seamlessly. User on Voxtral free tier hitting 1 RPS can also flip to Groq for higher throughput.

### A.2 Files to touch

| File | Action |
|---|---|
| `src/dicton/adapters/stt/groq.py` (NEW) | New module mirroring the structure of `mistral.py`. Class `GroqSTTProvider(STTProvider)`. Use the official `groq` Python package (`pip install groq`) — it provides a synchronous `Groq` client with `client.audio.transcriptions.create(model=..., file=...)`. Pin model id `whisper-large-v3-turbo` as a `DEFAULT_MODEL` constant; **do not** read it from env (per the hardcode-models policy from `reduce-latency.md`). Inject a custom `httpx.Client` with `keepalive_expiry=300, http2=True`, mirroring the Mistral provider — same connection-pooling logic. Add a `prewarm(n=2)` method that fires N HEAD/GET on `https://api.groq.com/openai/v1/` to seed warm sockets. |
| `pyproject.toml` | Add `groq>=0.16.0` as an optional dep under a new extra `groq = ["groq>=0.16.0"]` (mirror the `mistral` extra at line 55-57). Add `groq` to the `linux` and `all` aggregate extras at lines 108 and 111. |
| `src/dicton/adapters/stt/factory.py` | Register `"groq"` as a known provider name; instantiate `GroqSTTProvider` when configured. Ensure availability check (`is_available()`) gracefully handles missing `groq` package or missing `GROQ_API_KEY`. |
| `src/dicton/shared/config.py` | Add `STT_PROVIDER` to recognise `"groq"` as a valid value. The class already reads `STT_PROVIDER` env — verify the new value flows. Default behaviour: if `GROQ_API_KEY` is set and `STT_PROVIDER` is unset, prefer `groq` over `mistral`. (Optional refinement; could also keep `mistral` default and let users opt in via `STT_PROVIDER=groq`.) |
| `src/dicton/adapters/config/config_env.py` | If a knob like `stt_provider` is dataclass-based, no change beyond accepting `"groq"` as a string value. |
| `src/dicton/orchestration/session_service.py:_prewarm_cleaner_llm` (sibling: `_prewarm_stt`) | No code change, but verify that the prewarm path picks up the new `prewarm()` on `GroqSTTProvider` via the existing `getattr(stt, "prewarm", None)` pattern. It will — same shape as Mistral. |
| `.env.example` | Add `# GROQ_API_KEY=gsk_...` (commented) under the STT section. |
| `README.md` and `SETUP.md` | One-line note in the "STT providers" section: "Groq Whisper Large v3 Turbo for lowest latency; falls back to Voxtral if no Groq key." |

### A.3 Audio format

Groq's `/audio/transcriptions` accepts WAV, MP3, FLAC, OGG, M4A, WebM, MP4 — the same `wav_content` bytes we already build for Mistral pass through unchanged. **No audio re-encoding.**

Constraint to verify in code: Groq's free-tier audio file size limit is 25 MB and 7200 s of audio per minute (rate). For our 5-30 s clips this is irrelevant. The `voxtral-mini-2602` 25-min clip cap is *not* matched by Groq (Groq is more lenient). Document the limits as a one-liner in the new provider's docstring.

### A.4 Error & retry semantics

Mistral's provider has `_MAX_RETRIES = 3` with exponential backoff for `429` and `capacity_exceeded`. Groq returns standard HTTP errors:
- `429 Too Many Requests` → retry with backoff, same logic.
- `400 Invalid model` → fail fast (we burned an hour on this with Voxtral; pin the model in code).
- `5xx` → retry once, then fail.

Mirror Mistral's `_is_retryable` + retry loop verbatim — adjust only the exception types if `groq` SDK raises its own.

### A.5 Validation

1. `GROQ_API_KEY=gsk_… STT_PROVIDER=groq /opt/dicton/dicton`
2. Tail `~/.local/share/dicton/dicton.log`. Expect:
   ```
   STT Provider: Groq Whisper (whisper-large-v3-turbo)
   POST https://api.groq.com/openai/v1/audio/transcriptions "HTTP/1.1 200 OK"
   Chunk 0 transcribed: 0.3-0.5s latency, N chars
   ```
3. Run a 10-second French dictation. Confirm transcript quality is at least equivalent to Voxtral. Whisper Large v3 Turbo has known weaknesses on aggressive accents; if quality regresses, the user can fall back via `STT_PROVIDER=mistral` without code change.
4. Confirm prewarm is firing on FN press: log should show two GETs to `api.groq.com` before the POST.

### A.6 Rollback safety

Set `STT_PROVIDER=mistral` and restart — instant rollback. Voxtral provider stays compiled in.

---

## Part B — Paste step: kill the verify-clipboard poll loop

### B.1 The problem

`src/dicton/adapters/output/base.py` has a `_verify_clipboard()` polling loop that:
- Calls `xclip -o -selection clipboard` after the set
- Compares output to expected text (whitespace-normalised)
- Retries up to `clipboard_max_retries=5` with `clipboard_verify_delay_ms=50` between attempts
- Worst-case path: 5 × 50 ms + 5 × xclip-fork-overhead ≈ **250 ms** burned on every paste

### B.2 The reality on X11

`xclip -selection clipboard` is **synchronous on selection ownership**: by the time the `xclip` process exits, the X server has registered xclip as the selection owner. There is no async propagation — the verification is paranoia from a previous bug or untrusted clipboard backend. xdotool's `key ctrl+v` then triggers a paste that reads from the current owner.

The 50 ms × 5 poll defends against a race that doesn't exist on X11. On Wayland with bridge tools (`wl-paste`), the race *can* exist, but we're on X11.

### B.3 Plan

| File | Action |
|---|---|
| `src/dicton/adapters/output/base.py` (`_verify_clipboard` and its callers) | Replace the poll loop with a **single read-back** if `debug=True`, and **skip entirely** if `debug=False`. Default behaviour after this change: trust `xclip`'s exit code (0 = success). |
| `src/dicton/adapters/output/linux.py:60-72` (`paste_text`) | Drop the `_verify_clipboard` call from the happy path. Keep an opt-in via a constructor flag (`verify_clipboard: bool = False`) so power users can re-enable when debugging. |
| `src/dicton/shared/config.py:CLIPBOARD_VERIFY_DELAY_MS / CLIPBOARD_MAX_RETRIES` | Mark as deprecated in code comment; keep parsing for back-compat but ignore at the verify layer (since verify is gone). |
| `src/dicton/adapters/output/linux.py:48-58` (`xdotool key ctrl+v` invocation) | Today it inherits xdotool's default 12 ms inter-keystroke delay. Pass `--delay 0` explicitly: `xdotool key --clearmodifiers --delay 0 ctrl+v`. Saves ~12 ms and removes a hidden default. |

**Expected savings: 150-250 ms** on average paste, larger on slower hardware.

### B.4 Risk

If the user has an X11 clipboard manager intercepting selections (`clipit`, `parcellite`), the paste might race that manager's poll. Mitigation: keep the constructor flag `verify_clipboard` so it can be re-enabled per-installation if a regression appears. Document in the constructor docstring.

### B.5 Validation

1. Pre-fix baseline: dictate 5 short clips, average post-audio cost. Note current values (~1.7-2.0 s on warm daemon).
2. Apply fix, rebuild, restart.
3. Re-dictate same 5 clips. Average should drop by ~150-200 ms.
4. **Negative test**: paste into a known-flaky target (terminal, GTK app, Electron app like VS Code). Confirm no truncation or paste failure across 10 attempts.

---

## Part C — Optional follow-up (NOT in this batch)

If post-audio is still >1.0 s after Parts A+B and you want to push further:

- **In-process X11 paste via `python-xlib`**: replace the `xclip`/`xdotool` subprocess pair with `Xlib.ext.xfixes` (selection ownership) + `Xlib.ext.xtest.fake_input` (synthesise Ctrl+V keypress). Avoids 2× fork+exec ≈ 30-60 ms. Adds `python-xlib` as runtime dep. Skipped here because the gain is small relative to Parts A+B and the refactor surface is non-trivial. Track as a future ticket.

---

## Sequencing, versioning, validation

1. **One PR per Part** (A and B), bundled into one release.
2. **Bump rules** (per project memory `feedback_bump_version.md`): A is a feature → minor bump (`1.13.x` → `1.14.0`). B is a perf fix → already covered by the same minor bump if shipped together.
3. Run `./scripts/check.sh` (full check, not just lint) before each commit per `feedback_full_check.md`.
4. Atomic commits per `feedback_atomic_commits.md`: `feat(stt): add Groq Whisper provider`, `feat(stt): default to Groq when key present`, `perf(paste): drop clipboard verify poll`, `perf(paste): xdotool delay 0` — separate commits.

## Out of scope (explicit non-goals)

- Streaming STT (Voxtral Realtime, AssemblyAI Universal-3). Requires rewriting the recording loop. Bigger payoff, much bigger refactor.
- Replacing Gemini Flash-Lite cleaner with Groq-hosted Llama 3 (cheaper, likely faster). Track separately — orthogonal to STT change.
- Disabling Gemini Flash-Lite "thinking budget" — still on the backlog from `reduce-latency.md`.
