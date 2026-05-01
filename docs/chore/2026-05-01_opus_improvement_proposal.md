# Architectural Deepening Proposal — 2026-05-01

> Author: Claude Opus 4.7, via `/improve-codebase-architecture`
> Informed by `docs/architecture-refactor-plan.md` and `CODE_REVIEW.md`.
> Vocabulary: Ousterhout's *deep / shallow / deletion test / seam* + the project's *core / orchestration / adapters / interfaces / port / `AppConfig` / `SessionService` / `DictationController`*.

## Summary

The hexagonal scaffolding from PR #51/#52 is in place, but several modules are **shallow** — interface nearly as complex as implementation, or extracted in name without responsibility transfer. Below are seven candidate **deepening opportunities**, ranked by how much friction they're causing today.

The recurring pattern: extraction has produced *files* that pass through to a single underlying object (one adapter at a seam → hypothetical seam, not a real one), and responsibility has stayed with the original module under a new name.

---

## Candidate 1 — Collapse the `DictationController` ↔ `SessionService` callback ouroboros

**Files**

- `core/controller.py`
- `orchestration/session_service.py`
- `orchestration/container.py:153-163`
- `adapters/audio/capture_adapter.py`, `adapters/audio/stt_adapter.py`
- `adapters/config/metrics.py`, `adapters/config/text_processing.py`

**Problem**

`container.py` builds a `DictationController` whose `text_processor` and `text_output` ports are `TextProcessorAdapter(session_service.process_text)` and `TextOutputAdapter(session_service.output_result)`. So `SessionService._record_and_transcribe` calls `controller.run_session(...)`, which calls back into `session_service.process_text` and `session_service.output_result` through one-method adapters. Two of the five port adapters wrap *bound methods of the caller*. `MetricsAdapter`, `AudioCaptureAdapter`, `STTAdapter` are 25-line classes that delegate every method to a single underlying object.

Apply the **deletion test**: delete those five adapters — does complexity reappear elsewhere? `recognizer`, `chunk_manager`, and `latency_tracker` already expose the right methods. They're shallow because there is exactly one adapter at each seam, and three of those seams have no second adapter coming.

The session lifecycle is split across two state machines (`controller._state` and `session_service._recording` / `_record_thread`), so any session-policy change touches both.

**Solution (one of two postures — this is the grilling question)**

- **(a) Collapse**: merge `DictationController` into `SessionService`. The controller is a procedural template that calls back through ports the same orchestrator built — locality wins by merging.
- **(b) Push policy into the controller**: move mode resolution, selection capture, `_filter_fillers_local`, and the LLM dispatch in `process_text` into the controller. The controller becomes genuinely deep; `SessionService` shrinks to a thin runtime-state holder for thread + visualizer.

**Benefits**

- One place owns "what happens during a dictation."
- **The interface becomes the test surface** instead of the controller-vs-service indirection.
- Five files of pass-through code disappear (or are justified with real second adapters).

---

## Candidate 2 — Make `AppConfig` the single source of truth; delete `shared/config.py` and the four shims

**Files**

- `core/config_model.py` (`AppConfig`)
- `adapters/config/config_env.py`
- `interfaces/web/config_logic.py`
- `shared/config.py` and `shared/{processing_mode,text_processor,latency_tracker,update_checker}.py`
- `interfaces/config_server.py`

**Problem**

The same env keys and defaults are enumerated in **three** places: `core/config_model.py`, `adapters/config/config_env.py`, and `interfaces/web/config_logic.py` (`_DEFAULTS` + `CONFIG_FIELD_MAP` + `env_vars.get("FOO", _default("FOO"))` calls). And `shared/config.py:Config` still lives, with its own copy of every default and a `reload_config()` that `save_config()` (line 168) invokes to keep the legacy global in sync.

Adding a setting means editing four files in agreement, with no enforcement.

The four `shared/*` modules whose first line is `"""Backward-compat shim..."""` exist purely so ~5 test imports keep working. Deletion test on `shared/config.py`: `Config.reload_config` is dead in the long run because new code reads `AppConfig`; `FLEXOKI_COLORS` and `POSITION_PRESETS` already exist in `adapters/ui/theme_constants.py`; `_load_env_files` belongs alongside `config_env.load_app_config`.

**Solution**

- Make `AppConfig` (or a sibling settings descriptor) the single source of truth for env keys, defaults, types, and UI metadata.
- `config_logic.get_current_config` and `save_config` derive their field map from it.
- Delete `shared/config.py` and the four shim files; fix the ~5 test imports in one PR.

**Benefits**

- **Locality**: adding an env var becomes one edit.
- **Leverage**: the settings model can grow (validation, secret-vs-public, UI metadata) and every consumer benefits.
- Tests stop needing to monkey-patch `Config` *and* `os.environ`.

---

## Candidate 3 — Make `HotkeyStateMachine` real; the listener loop becomes thin I/O

**Files**

- `adapters/input/fn/handler.py` (813 lines)
- `adapters/input/fn/state_machine.py` (26 lines — just an enum)
- `adapters/input/fn/parser.py`
- `adapters/input/fn/device_registry.py`

**Problem**

`state_machine.py` is 26 lines of `Enum` with no transition logic. The actual transitions — `_on_fn_key_down`, `_on_fn_key_up`, `_start_double_tap_timer`, `_detect_mode`, the modifier-state booleans, the timer thread, the "RECORDING_TOGGLE + key_down → IDLE" decision — all live inline in `handler.py`, intermixed with `evdev`/`select`/`pyudev`/wake-pipe plumbing.

This is the **pure-extraction-without-locality** trap: the file boundary moved, the responsibility didn't. The interface (`start()`, `stop()`, three callbacks) is deep on the surface, but a bug in double-tap timing means reading 800 lines of device-loop code before reaching the timing.

This is exactly what `architecture-refactor-plan.md` Phase 5 calls for; it's been started in name only.

**Solution**

A real `HotkeyStateMachine` class owning `(state, last_key_up_ts, modifiers, mode_lock)` and exposing:

```
on_event(event_kind, time_now) -> Action
```

where `Action` is `start_recording(mode) | stop_recording | cancel_recording | none`. The listener loop becomes a thin event reader that asks the pure machine "what now?".

Modifier tracking, mode detection, double-tap window, secondary-hotkey lock-in all become testable without `evdev`.

**Benefits**

- "Double-tap within 280 ms after a 320 ms gap fires correctly" becomes a parametric unit test, not an integration test with mocked devices.
- Listener loop shrinks to ~50 lines of I/O.
- Hot-plug, callback-queue, and timing concerns stop fighting in the same module.

---

## Candidate 4 — `prompts.py` should hold prompts, not re-implement LLM fallback

**Files**

- `adapters/llm/prompts.py`
- `adapters/llm/factory.py`
- `orchestration/session_service.py:226-265`
- `orchestration/container.py:130`

**Problem**

`container.py` calls `get_llm_provider_with_fallback(...)` and passes the resolved `llm_provider` into `SessionService`. But `SessionService.process_text` calls `act_on_text(...)` / `reformulate(...)` / `translate(...)` from `prompts.py`, which **completely ignore** the injected provider and run their own fallback chain in `_call()` (lines 8-40), re-walking `DEFAULT_FALLBACK_ORDER` and calling `get_llm_provider(name)`.

The injection is theatre: the real lookup happens via the module-level cache in `factory.py`. Two parallel paths to "which LLM should I use," both bypassing each other. `_call` is also where prompts and provider routing meet — a 3-purpose module.

**Solution**

- `prompts.py` holds *prompts only* (pure strings/templates).
- LLM dispatch becomes a `TextActions` use-case sitting in `orchestration/` (or a new `application/text_actions.py`), constructed with the already-resolved `LLMProvider`.
- The fallback chain lives **once**, in `factory.get_llm_provider_with_fallback`.

**Benefits**

- Prompts become testable without any SDK or env.
- The `LLMProvider` injection finally means something — swapping providers in tests is one constructor arg, not a global cache reset.
- Locality: prompt edits stop touching dispatch logic.

---

## Candidate 5 — Stop reading `os.environ` from `core/`

**Files**

- `core/processing_mode.py:104` (`advanced_modes_enabled()`)

**Problem**

`advanced_modes_enabled()` calls `os.getenv("ENABLE_ADVANCED_MODES", ...)` directly from the `core/` layer. The refactor plan's dependency table forbids exactly this:

> Core layer ... Forbidden: import config globals.

The violation propagates: `is_mode_enabled` (in core) is called from `SessionService.start_recording` and `SessionService.process_text`, so the core function reaches around the `app_config` injection that the orchestration layer carefully threads through.

**Solution**

Take `enable_advanced_modes: bool` as an argument to `is_mode_enabled` (and `advanced_modes_enabled`) — or move both functions to `orchestration/` since they're policy, not domain. `AppConfig.enable_advanced_modes` already exists.

**Benefits**

- Small change, large symbolic value: an `import os` ban in `core/` becomes enforceable (catches future regressions automatically).
- Tests stop needing `monkeypatch.setenv` to switch modes.

---

## Candidate 6 — Split `SpeechRecognizer`; it is the real audio god-object

**Files**

- `adapters/audio/recognizer.py` (411 lines)
- `adapters/audio/capture_adapter.py`, `adapters/audio/stt_adapter.py`
- `adapters/text/processor.py` (filter logic duplicated)

**Problem**

`SpeechRecognizer` owns: PyAudio device discovery (`_find_input_device`, `_select_best_device`), the recording loop with visualizer ticks (`record`), fixed-duration recording (`record_for_duration`), WAV encoding (`_audio_to_wav`), STT dispatch via `_stt_provider`, noise/dictionary filtering (`_filter`, `filter_text`), and the visualizer factory hook.

The two adapters wrapping it (`AudioCaptureAdapter`, `STTAdapter`) are forced to also wrap `chunk_manager`, splitting pipeline state across three objects. Filter logic is duplicated between `recognizer._filter` and `adapters/text/processor.py`.

**Solution**

Split `SpeechRecognizer` into:

- **`MicrophoneCapture`** — device discovery + record loop. No STT, no filter.
- **`STTProvider` chain** — already exists; let it stand alone.
- **`TranscriptionFilter`** — noise/dictionary cleanup; consolidate with `text/processor.py`.

`chunk_manager` then plugs into `MicrophoneCapture`'s `on_chunk` hook directly, and the two pass-through adapters (`AudioCaptureAdapter`, `STTAdapter`) disappear.

**Benefits**

- Each piece testable alone (today the recognizer requires `pyaudio` even to import-test the filter).
- `chunk_manager` integration stops being a special case threaded through two adapters.
- Locality: noise filtering lives in one place, not two.

---

## Candidate 7 _(lower priority, naming-only)_ — `adapters/config/` is a junk drawer

**Files**

- `adapters/config/{latency,metrics,text_processing,update_checker,config_env}.py`

**Problem**

`latency.py` (metrics infrastructure), `metrics.py` (metrics port adapter), `text_processing.py` (text-processing port adapters), `update_checker.py` (ops), `config_env.py` (settings loader). None of these is configuration.

**Recommendation**

Skip unless Candidate 2 happens, which would naturally re-home things. Otherwise: rename `adapters/config/` → split into `adapters/metrics/`, `adapters/ops/`, and merge the port adapters into the modules they wrap (or delete them per Candidate 1).

---

## Suggested grilling order

1. **Candidate 1 + Candidate 5 together** — they touch the same conceptual question: *what does "core" mean in this codebase?* Resolving it shapes Candidates 2 and 6 downstream.
2. **Candidate 3** if FN-key behaviour is being actively touched — highest concrete-pain item.
3. **Candidate 2** as a high-leverage cleanup once the core/orchestration boundary is clear.
4. **Candidates 4 and 6** are localised wins that can land independently.
5. **Candidate 7** only as a side effect of Candidate 2.

## Cross-cutting observation

Every candidate above is a variant of the same pattern: **extraction was performed at the file level but not at the responsibility level.** A second pass through the codebase asking "which module *owns* this decision?" — rather than "which module *contains* this code?" — would catch most of these in code review.
