# Reduce-Latency Plan

> Plan for shaving end-to-end latency on the dictation pipeline. **Instructions only — no code.** Each section says *what to change*, *where*, and *why*.
>
> File saved as `reduce-latency.md` (interpreted from voice input `radius latency.md`).

---

## 0. Scope summary

Three orthogonal changes, in increasing risk order:

1. **Hard-code the latest STT and LLM model IDs** — drop env-var indirection.
2. **Pre-warm provider connections** the moment recording starts (FN press / audio click).
3. **Maintain a small connection pool (n=2) for Voxtral** so a parallel chunk dispatch never pays a fresh handshake.

All three target the same root cause: cold TCP+TLS handshakes (~100-200 ms each) currently visible in `~/.local/share/dicton/dicton.log` on every dictation.

---

## 1. Hard-code Voxtral & Gemini models, drop env-var override

### 1.1 Target model IDs

| Provider | Old default | New hard-coded value | Rationale |
|---|---|---|---|
| Mistral STT | `voxtral-mini-latest` | `voxtral-mini-2602` | Mini Transcribe V2 (Feb 2026), batch-transcribe-optimized, sub-200 ms server-side. **NB:** the doc URL slug is `voxtral-mini-transcribe-26-02` but the API model ID is `voxtral-mini-2602` — verified via `GET /v1/models`. Also note that `voxtral-mini-latest` aliases to the older `2507`, not to `2602`, so the date suffix must be hard-coded to actually get V2. See `https://docs.mistral.ai/models/model-cards/voxtral-mini-transcribe-26-02`. |
| Gemini (general LLM) | `gemini-2.5-flash-lite` | `gemini-flash-lite-latest` | Aligns with the cleaner pin already in `cleaner.py` (`_DEFAULT_CLEANER_MODELS["gemini"]`); `-latest` keeps us on the freshest stable Flash-Lite without bumps. |
| Gemini (cleaner) | already pinned to `gemini-flash-lite-latest` | unchanged | Confirm the pin remains the source of truth. |

### 1.2 Files to change

| File | Lines | Action |
|---|---|---|
| `src/dicton/adapters/stt/mistral.py` | `41` | Replace `DEFAULT_MODEL = "voxtral-mini-latest"` with `DEFAULT_MODEL = "voxtral-mini-2602"`. |
| `src/dicton/adapters/stt/mistral.py` | `57-60` | Remove the `os.getenv("MISTRAL_STT_MODEL", ...)` lookup; always use `DEFAULT_MODEL`. The whole `if not self._config.model:` branch becomes a single assignment from the constant, since `self._config.model` is no longer overrideable. |
| `src/dicton/adapters/llm/gemini.py` | `22` | Drop `os.getenv("GEMINI_MODEL", ...)`; replace with module-level constant `DEFAULT_GEMINI_MODEL = "gemini-flash-lite-latest"`. The `model` constructor arg can stay for tests but should no longer fall back to env. |
| `src/dicton/adapters/llm/cleaner.py` | `26-29` | No code change. Add a one-line comment confirming this dict is the **single source of truth** for cleaner model IDs. |
| `src/dicton/shared/config.py` | `131, 142, 261, 266` | Delete the `GEMINI_MODEL` and `MISTRAL_STT_MODEL` keys (initial assignment + `reload()` reassignment). They are now dead code. |
| `src/dicton/adapters/config/config_env.py` | `50, 56` | Delete the `mistral_stt_model=...` and `gemini_model=...` lines. Whatever consumes those fields downstream (search for `mistral_stt_model`, `gemini_model` across the repo before deleting) must be cleaned up too. |
| Any web/CLI config UI surface that displays these models | grep for `MISTRAL_STT_MODEL` / `GEMINI_MODEL` | Remove the inputs. The user explicitly does **not** want runtime overrides. |
| `.env.example`, `README.md`, docs | grep | Strip references to these env vars and document the hard-coded IDs in a "Pinned model versions" section. |

### 1.3 Constraint

After this change, `MISTRAL_STT_MODEL` and `GEMINI_MODEL` env vars become **silently ignored**. Add a one-line note in the project README ("Models are pinned in code; env overrides removed in vX.Y.Z") to avoid user confusion.

---

## 2. Pre-warm provider connections at recording start

### 2.1 Hook point

`SessionService.start_recording()` at `src/dicton/orchestration/session_service.py:86` is the single, already-wired entry-point fired the instant FN is pressed (path: `fn/handler.py:325-326` → `runtime_service.py:58` → here).

The prewarm calls must:
- run in **background daemon threads** (never block the recording start path);
- be **idempotent and best-effort** (silent on failure — recording continues regardless);
- fire **once per session start**, not per chunk.

### 2.2 What "pre-warm" means concretely

For each provider, open the TCP socket, complete the TLS handshake, and leave the socket parked in the SDK's HTTP connection pool with a long `keepalive_expiry` (≥ 300 s). When the actual transcribe / cleaner request fires moments later, httpx reuses that warm socket — saving the connect + TLS round-trip(s).

### 2.3 Mistral side

| Where | Action |
|---|---|
| `src/dicton/adapters/stt/mistral.py:125` (client init) | Replace the bare `Mistral(api_key=..., timeout_ms=...)` construction with one that injects a custom `httpx.Client`. The custom client must set `limits=httpx.Limits(max_keepalive_connections=2, max_connections=4, keepalive_expiry=300)` and `http2=True`. The `Mistral` SDK accepts an injected client — verify the exact kwarg name (`client=` or `async_client=`) against the installed `mistralai` version. If injection isn't supported, monkey-patch the SDK's internal client after construction (acceptable fallback, but flag in code). |
| `src/dicton/adapters/stt/mistral.py` (new method) | Add `prewarm(self, n: int = 2) -> None`. Implementation: spin `n` background threads that each issue a cheap `HEAD` (or `OPTIONS`) on `https://api.mistral.ai/` using the pooled httpx client. Swallow exceptions. The goal is to populate the pool with `n` warm sockets. |
| `src/dicton/orchestration/session_service.py:start_recording` | After the lock-section that flips `_starting=True`, fire-and-forget a thread that calls `self._recognizer.prewarm(n=2)` (assuming the recognizer exposes the underlying provider via a passthrough; otherwise inject the Mistral provider directly into `SessionService.__init__` and call `self._mistral.prewarm(n=2)`). |

### 2.4 Gemini side

| Where | Action |
|---|---|
| `src/dicton/adapters/llm/gemini.py:49` (client init) | When constructing `genai.Client(api_key=...)`, pass `http_options=types.HttpOptions(...)` configured with the same keepalive policy. The current `google-genai` SDK exposes `HttpOptions(client_args={...})` or similar — verify against the installed version. Worst case: post-construct, replace the SDK's internal `_api_client._httpx_client` with a tuned one (mark as "implementation detail of google-genai vX" so future SDK bumps catch the change). |
| `src/dicton/adapters/llm/gemini.py` (new method) | Add `prewarm(self) -> None`. One background thread issuing a cheap `GET` on `https://generativelanguage.googleapis.com/` (or even a TCP-only socket open on port 443 if the SDK refuses to expose its client) to seed one warm connection. |
| `src/dicton/orchestration/session_service.py:start_recording` | Same fire-and-forget pattern as Mistral. The Gemini provider is reachable through `self._llm` (already injected). If `self._llm` is None (Gemini not configured), skip silently. |

### 2.5 Concurrency note

The two prewarms (Mistral + Gemini) **must run in parallel**, not sequentially. Use two daemon threads (or a tiny thread pool) so the slowest of the two — not the sum — bounds the prewarm completion time. Both must complete (or time out) well before the user releases FN; for typical recordings (>1 s of audio) this is trivially the case.

---

## 3. Voxtral connection pool of 2

### 3.1 Why 2

Two reasons:

1. `chunk_manager.py:66` is currently `max_workers=1` (sequential dispatch by design, capped to free-tier RPS). The user expects this to evolve toward **parallel chunk dispatch** for long recordings; the pool needs to be ready when that flip happens.
2. Even today, observation in logs: each request opens a fresh TCP connection. With `max_keepalive_connections=2` and `n=2` prewarmed sockets, the second chunk (and any retry) reuses an already-warm second socket instead of paying a new handshake.

### 3.2 Where

This falls out of section 2.3 — the `httpx.Limits(max_keepalive_connections=2, max_connections=4, keepalive_expiry=300)` config plus `prewarm(n=2)` already implements it. The `n=2` knob should live as a module-level constant in `src/dicton/adapters/stt/mistral.py` (e.g. `_PREWARM_POOL_SIZE = 2`) so it's tweakable in one place without diving into the orchestration layer.

### 3.3 When to revisit `max_workers`

The `chunk_manager.py:66` comment says the constraint is Mistral's free-tier 1 RPS limit. **Keep `max_workers=1` for now** — pool prewarming doesn't change rate-limit semantics. The pool benefits the **single-chunk** case (warm socket on first call) and prepares for a future bump to `max_workers=2`. Document this explicitly in a code comment so future-you knows the pool size and worker count are coupled.

---

## 4. Validation & rollout

### 4.1 Local validation steps

1. Restart the daemon (`/opt/dicton/dicton`).
2. Run 3 dictations in a row, separated by 30 s, then 5 min, then 30 min.
3. Tail `~/.local/share/dicton/dicton.log` and confirm:
   - For dictations 2 and 3: **no** `connect_tcp.started host='api.mistral.ai'` line between the FN-press timestamp and the `POST .../v1/audio/transcriptions` line. (The connect happens during FN-press prewarm, not during the actual transcribe call.)
   - Same for `generativelanguage.googleapis.com`.
   - The first dictation may still show a connect_tcp because the daemon has just started; that's expected.
4. Confirm `transcript cleaner: gemini ok in <Xms>` is consistently below the current 900-1100 ms band — target ≤ 700 ms.
5. Confirm `Chunk 0 transcribed: <Xs> latency` is consistently below 0.7 s for short clips — target ≤ 0.5 s.

### 4.2 Failure modes to guard

- **SDK refuses custom httpx client** → fall back to monkey-patching, isolated to the provider file, with a `# TODO: revisit on SDK bump` comment.
- **Prewarm thread crashes** → the daemon must keep running. Wrap the prewarm body in a broad `try/except` that only logs at DEBUG.
- **User hits FN before previous prewarm finishes** → harmless; httpx pools dedup connections.

### 4.3 Versioning

Per project memory rule (`feedback_bump_version.md`): bump `src/dicton/__init__.py` to the next minor (this is a feature, not a bug fix). Conventional-commit prefix: `feat(perf)` or `perf:`.

---

## 5. Out of scope (explicit non-goals)

- **Disabling Gemini Flash-Lite "thinking budget"** — separate optimization, not requested in this round; track as a follow-up.
- **Streaming `streamGenerateContent`** — useless until we implement speculative cleaning.
- **Vertex AI regional endpoints** — adds SA auth complexity for marginal gain in EU.
- **Voxtral Realtime streaming STT** — requires rewriting the recording loop; deferred.
