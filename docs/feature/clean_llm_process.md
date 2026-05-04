# Clean LLM Process — pre-output transcript cleaning step

**Status:** plan
**Created:** 2026-05-04
**Owner:** asi0
**Target version bump:** 1.12.0

## 1. Intent

Insert a **mandatory, low-latency LLM cleanup pass** between STT (Mistral Voxtral) and the existing mode-specific processing (`process_text`). The pass:

- Removes filler words / hesitations (`euh`, `um`, `genre`, `du coup`, …).
- Strips bracketed/parenthesised non-speech annotations the STT may emit (`[bruit]`, `(rires)`, `[music]`, `[silence]`, `[inaudible]`, …).
- Reconstructs the utterance with **faithful** lexical content but **correct grammar and syntax**.
- Preserves the speaker's voice, tone, register, and language — does **not** translate, summarise, or reformulate.

Model: **Gemini 3.1 Flash-Lite Preview** — picked from the 2026-05-04 Artificial Analysis leaderboard for its 356 tokens/s throughput and II 34, the best speed/intel ratio at sub-cent cost. Fallback to `gemini-2.5-flash-lite` if the preview alias fails.

## 2. Decision ⇔ consequences ⇔ use case

**Decision A — cleaner runs by default for every non-RAW mode (BASIC included).**

- *Consequences:* every dictation now has +1 LLM round-trip on the hot path. At 356 t/s and ~150 output tokens for typical dictations → ~0.4–0.6 s added latency. Fails open: if Gemini is unreachable, fall back to raw STT text. Adds a Gemini API key requirement for the cleaner role even when the user's main `LLM_PROVIDER` is `anthropic`.
- *Concrete use case:* asi0 dicte « euh… donc euh, je voulais te dire que, voilà, le, le truc que je voulais c'est, [tousse] qu'on, qu'on déploie ça demain » → output BASIC: « Je voulais te dire que je veux qu'on déploie ça demain. »

**Decision B — cleaner is a *separate* LLM role from the existing reformulator/translator.**

- *Consequences:* new pinned model (`flash-lite`) independent of `GEMINI_MODEL` (which the user may set to a heavier model for REFORMULATION). Adds one config field. Avoids paying Pro-tier latency on every BASIC dictation. Keeps the reformulate/translate prompts free of filler-removal duties — they shrink and become more focused.
- *Concrete use case:* user has `LLM_PROVIDER=anthropic` and `ANTHROPIC_MODEL=claude-opus-4-7` for heavy REFORMULATION work, but BASIC dictation still gets a 400 ms Gemini Flash-Lite cleanup instead of a 4 s Opus call.

**Decision C — RAW mode bypasses the cleaner.**

- *Consequences:* `RAW` keeps its contract (yellow ring = exactly what the STT emitted). Documented escape hatch when the cleaner over-edits.
- *Use case:* user dictates a code identifier or proper noun the cleaner mangles → switches to RAW mode (already exists), gets verbatim STT.

## 3. Pipeline change

### Current (`session_service._record_and_transcribe`)

```
record audio → STT → process_text(mode) → output
```

`process_text` branches:
- BASIC / RAW → return text as-is
- REFORMULATION → `reformulate(text)` (LLM)
- TRANSLATION → `translate(text)` (LLM, includes implicit cleanup in prompt step 1)
- TRANSLATE_REFORMAT → `translate` then `reformulate`

### Target

```
record audio → STT → clean_transcript() → process_text(mode) → output
                       └ NEW pinned Flash-Lite step, fail-open
```

Per-mode behaviour after the change:
- **RAW** → bypass cleaner entirely (unchanged contract).
- **BASIC** → cleaner only.
- **REFORMULATION** → cleaner → simplified `reformulate` (no longer responsible for filler stripping; focuses on structural rewrites, list formatting, dictation-command interpretation).
- **TRANSLATION** → cleaner → simplified `translate` (Step 1 of the current 2-step prompt is now redundant, prompt shrinks).
- **TRANSLATE_REFORMAT** → cleaner → translate → reformulate.

### Failure semantics

| Cleaner outcome           | What `process_text` sees |
|---------------------------|--------------------------|
| Returns cleaned string    | cleaned string           |
| Returns `None` (provider unavailable, network error, timeout) | raw STT text (fail-open) |
| Returns `"None"` literal (LLM judges input meaningless) | propagate as “No speech” path, same as today's `not text` branch |
| Cleaning disabled by config | raw STT text             |

Cleaner failure must **never** block output — log at `WARNING`, surface a debug-only toast.

## 4. Code-level plan

### 4.1 New file — `src/dicton/adapters/llm/cleaner.py`

```python
def clean_transcript(
    text: str,
    *,
    language: str | None = None,
    user_provider: str = "auto",
    model: str | None = None,   # pinned to Gemini Flash-Lite by default
    timeout_s: float = 8.0,
    debug: bool = False,
) -> str | None:
    ...
```

- Reuses `factory.get_llm_provider("gemini")` but with a model override.
- Falls back to `anthropic` (Claude Haiku 4.5, II 37 @ 106 t/s) if no Gemini key.
- Prompt: dedicated, narrow, ≤ ~30 lines (see §5).
- Returns `None` only on hard failure; returns `"None"` *string* if the LLM reports no meaningful content.

### 4.2 Provider extension — `LLMProvider.complete()` model override

Today `complete(prompt)` uses `self._model` set at construction. Two options:

- **(A)** Add an optional `model: str | None = None` arg to `complete()` on the ABC; Gemini/Anthropic implementations honour it per call.
- **(B)** Create dedicated `GeminiLLMProvider` instance with the cleaner model (separate cache key).

→ Pick **(A)**. Smaller surface, no parallel cache. Default arg `None` keeps existing call sites working.

### 4.3 Config — `AppConfig` + env reads

Add to `shared/app_config.py` (Text-processing section):

```python
enable_transcript_cleaning: bool          # default True
transcript_cleaner_provider: str          # "gemini" (default) | "anthropic" | "auto"
transcript_cleaner_model: str             # default "gemini-flash-lite-latest"
transcript_cleaner_timeout_s: float       # default 8.0
```

Add matching env reads in `adapters/config/config_env.py`:
- `ENABLE_TRANSCRIPT_CLEANING` (default `true`)
- `TRANSCRIPT_CLEANER_PROVIDER` (default `gemini`)
- `TRANSCRIPT_CLEANER_MODEL` (default `gemini-flash-lite-latest`; document that the explicit Gemini 3.1 Flash-Lite Preview ID may be used once GA)
- `TRANSCRIPT_CLEANER_TIMEOUT` (default `8`)

### 4.4 Web config UI

Surface the four fields in `interfaces/web/routes_config.py` + the corresponding template under a new “Transcript cleaning” section. Keep it collapsible / advanced.

### 4.5 Wiring in `SessionService`

In `_record_and_transcribe`, between the STT block and the `process_text` call:

```python
with tracker.measure("stt_transcription"):
    text = self._transcribe_audio(audio)

# NEW
if mode is not ProcessingMode.RAW and self._app_config.enable_transcript_cleaning:
    with tracker.measure("transcript_cleaning"):
        cleaned = clean_transcript(
            text,
            language=self._app_config.language,
            user_provider=self._app_config.transcript_cleaner_provider,
            model=self._app_config.transcript_cleaner_model,
            timeout_s=self._app_config.transcript_cleaner_timeout_s,
            debug=self._app_config.debug,
        )
    if cleaned is not None and cleaned.strip().lower() != "none":
        text = cleaned  # else fail-open: keep raw STT

with tracker.measure("text_processing", mode=...):
    result = self.process_text(text, mode, selected_text=None)
```

Tracker gets a new metric key `transcript_cleaning` — useful to confirm the latency budget post-deployment.

### 4.6 Prompt simplification

Trim `prompts.py::reformulate` and `translate` prompts: drop the explicit filler-list section, keep only structural rules (number conversion, list formatting, dictation commands, tone preservation). Smaller prompts → faster Pro/Opus calls → win-win.

## 5. Cleaner prompt (draft)

```
You are a transcript cleaner. The input is raw speech-to-text output.

YOUR JOB:
- Remove filler words and hesitation sounds in any language
  (euh, heu, um, uh, like, you know, en fait, du coup, voilà, genre, bah, ben, hein, …).
- Remove ALL bracketed or parenthesised non-speech annotations the STT may have
  emitted: [bruit], [noise], [music], [silence], [inaudible], (rires), (laughs), …
- Repair grammar and syntax so the output is a well-formed sentence (or several),
  in the SAME language as the input.
- Preserve faithfully WHAT was said: do not paraphrase, do not summarise, do not
  add ideas, do not change the tone or register, do not translate.
- Keep proper nouns, technical terms, code identifiers verbatim.
- Light punctuation only (commas, periods, question marks). No reformatting into
  lists, no markdown.
- If the input is empty, only static, or has no meaningful speech, output
  exactly: None

OUTPUT: only the cleaned text, nothing else.

INPUT:
{text}

CLEANED:
```

Stay <300 input tokens; pinned Flash-Lite reads it in <50 ms.

## 6. Tests

Add `tests/test_transcript_cleaner.py`:

1. **Happy path** — fake `LLMProvider` returns canned cleaned text; assert `clean_transcript` returns it.
2. **Fail-open** — provider raises → `clean_transcript` returns `None`, caller keeps raw STT.
3. **Provider unavailable** — `is_available()` returns False → `None`, caller keeps raw STT.
4. **`"None"` sentinel** — provider returns the literal string `"None"`; `clean_transcript` returns `"None"` and session_service treats it as no-speech (parity with existing path).
5. **Bracket stripping** — fake provider asserts the prompt embeds the bracket-removal rule (regression on prompt drift).
6. **RAW mode bypass** — extend `tests/test_session_service.py` to assert RAW skips the cleaner call entirely.
7. **Disabled flag** — `enable_transcript_cleaning=False` → cleaner not invoked.
8. **Provider override** — `complete(prompt, model="…")` override is propagated to Gemini/Anthropic adapters.

Update `tests/test_llm_processor.py` and `test_llm_provider.py` for the `model` parameter on `complete()`.

## 7. Atomic commit sequence (branch `feat/clean-llm-process`)

1. `feat(llm): add per-call model override on LLMProvider.complete`
   - ABC + Gemini + Anthropic + Null + tests.
2. `feat(config): add transcript-cleaning config fields`
   - `AppConfig`, env reader, defaults, tests.
3. `feat(llm): add clean_transcript() with pinned Flash-Lite`
   - New `cleaner.py`, prompt, unit tests.
4. `feat(session): wire transcript cleaner before process_text`
   - `SessionService`, latency tracker key, fail-open path, tests.
5. `refactor(llm): simplify reformulate/translate prompts (cleaner now upstream)`
   - Prompt slimming + assert tests still green.
6. `feat(web): expose transcript-cleaning settings in config UI`
7. `docs: README + windows-packaging.md note on the new env vars`
8. `chore: bump dicton to 1.12.0`

Each commit must pass `./scripts/check.sh` (full, not just lint).

## 8. Open questions / risks

- **Model ID stability.** “Gemini 3.1 Flash-Lite Preview” has no documented stable Google AI Studio alias yet. Plan: default to `gemini-flash-lite-latest`, document that pinning to the explicit preview ID is encouraged when available, fall back to `gemini-2.5-flash-lite` on 404. Verify with `google-genai` SDK before commit #3.
- **Latency cost on BASIC.** Today BASIC has zero LLM cost. Adding ~0.5 s may bother power users. Mitigation: env opt-out + a UI toggle. If telemetry shows median > 800 ms, demote default to `false`.
- **Cleaner over-edits.** If asi0 dictates a quote, citation, or technical jargon, the cleaner may smooth it. RAW mode is the escape valve. Consider a per-utterance escape (e.g. dictation prefix “raw — …”) only if this becomes a real pain point — out of scope for v1.
- **Gemini key bootstrap.** A user running only Anthropic today will see the cleaner silently fall back to Claude Haiku. Document clearly. Possibly print a one-time hint on startup if the cleaner provider is unavailable.
- **Privacy.** Adds a third-party hop (Gemini API) for every BASIC dictation, which previously stayed local-ish (only the STT call left the box). Document in README. No new audio leaves — just text — but worth being explicit.

## 9. Out of scope (for this feature)

- A local model (whisper-style refiner running on-device).
- Per-language cleaner prompt variants.
- Adaptive cleaner intensity (heavy/light).
- Streaming cleaner that runs on partial STT chunks.

These can come in a v1.13+ if the simple version proves valuable.
