# Codex Improvement Proposal — Codebase Architecture Deepening

Date: 2026-05-01

## Context

This proposal captures architectural friction found in the Dicton codebase and suggests **deepening opportunities**: refactors that turn shallow modules into deeper modules with better **Locality**, more **Leverage**, and cleaner test **Seams**.

No `CONTEXT.md`, `docs/adr/`, or `tasks/lessons.md` existed at review time. The analysis used `README.md`, `docs/architecture-refactor-plan.md`, current source files, and tests as the source of project language.

The earlier architecture refactor plan has partly landed already: `orchestration/container.py`, `orchestration/session_service.py`, web route splits, and FN parser/device extraction exist. The remaining friction is now more specific than the original broad layering problem.

## Architecture Vocabulary

- **Module** — anything with an interface and implementation.
- **Interface** — everything a caller must know to use the module correctly.
- **Implementation** — the code inside a module.
- **Seam** — where an interface lives; a place behavior can be altered without editing in place.
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Depth** — leverage at the interface: lots of behavior behind a small interface.
- **Locality** — change, bugs, knowledge, and verification concentrated in one place.
- **Leverage** — what callers get from a deeper module.

## Proposed Deepening Opportunities

### 1. Deepen the active text target module

#### Files

- `src/dicton/orchestration/session_service.py`
- `src/dicton/core/ports.py`
- `src/dicton/adapters/config/text_processing.py`
- `src/dicton/adapters/output/linux.py`
- `src/dicton/adapters/output/base.py`
- `src/dicton/adapters/output/selection_*.py`

#### Problem

The current output **Interface** says output can replace selected text:

```python
TextOutput.output(text, mode, replace_selection)
```

But the actual **Implementation** discards that information:

```python
TextOutputAdapter.output(...) -> self._output_fn(...)
SessionService.output_result(...) -> self._text_output.insert_text(...)
```

So `ACT_ON_TEXT` captures selected text, processes it, then uses plain insertion. Selection knowledge is split between the session orchestration module and platform output adapters. Clipboard timing, selection replacement, paste thresholds, and mode-specific output semantics are scattered.

#### Deletion test

Deleting `TextOutputAdapter` mostly removes indirection. The complexity does not concentrate; it reveals that the current **Seam** is too shallow.

#### Solution

Deepen the active text target module so “insert at cursor”, “paste long text”, and “replace selected text” live in one place. The session orchestration module should not need to know clipboard mechanics or platform selection behavior.

#### Benefits

- **Locality**: clipboard race handling, paste fallback, selection replacement, and verification live together.
- **Leverage**: all modes get reliable output behavior through one deeper module.
- Tests improve: `ACT_ON_TEXT` can be tested through the output **Interface** instead of relying on private assumptions about `SessionService`.

---

### 2. Remove the false split between audio capture and STT transcription

#### Files

- `src/dicton/adapters/audio/recognizer.py`
- `src/dicton/adapters/audio/capture_adapter.py`
- `src/dicton/adapters/audio/stt_adapter.py`
- `src/dicton/adapters/audio/chunk_manager.py`
- `src/dicton/orchestration/container.py`
- `src/dicton/core/ports.py`

#### Problem

The core currently has two apparent **Seams**:

- `AudioCapture`
- `STTService`

But both adapters wrap the same `SpeechRecognizer`, and chunking spans both:

- `AudioCaptureAdapter.record()` starts and feeds `ChunkManager`
- `STTAdapter.transcribe()` finalizes `ChunkManager`
- `SpeechRecognizer` owns device discovery, recording, WAV conversion, provider selection, provider availability, filtering, and cleanup

The **Interface** suggests separation, but the **Implementation** is coupled by ordering and shared state. Callers must preserve an implicit sequence: start chunking during capture, finalize during transcription, then filter through recognizer.

#### Deletion test

Deleting `capture_adapter.py` and `stt_adapter.py` would not remove domain complexity; it would just expose the real coupled module underneath.

#### Solution

Deepen the recording pipeline module. The behavior “record audio → optionally chunk → transcribe → filter” should have one cohesive home, or the capture and STT modules should become genuinely independent. The current halfway split is the expensive shape.

#### Benefits

- **Locality**: chunk lifecycle bugs stop being split across two adapters.
- **Leverage**: tests can exercise full recording/transcription flow without patching private recognizer fields.
- Cleaner failure modes: provider unavailable, no audio, chunk partial result, and transcription failure can become explicit pipeline outcomes.

---

### 3. Deepen the dictation session module around lifecycle, state, and mode policy

#### Files

- `src/dicton/orchestration/session_service.py`
- `src/dicton/core/controller.py`
- `src/dicton/core/state_machine.py`
- `src/dicton/core/ports.py`
- `tests/test_controller.py`
- `tests/test_session_service.py`

#### Problem

Understanding one dictation session requires bouncing between `SessionService`, `DictationController`, the state machine, ports, text output adapters, LLM prompts, visualizer setup, and metrics.

The split is not clean:

- `SessionService.add_state_observer()` reaches into `self._controller._state`
- `DictationController.run_session()` accepts `mode_names` and `pre_output`, which are UI/runtime concerns leaking into its **Interface**
- `DictationController` prints user-facing messages directly
- cancellation and state reset live partly in controller, partly in session orchestration
- mode-specific selected-text policy lives in `SessionService`, while output replacement intent is passed through core and then lost

The core controller earns some keep, but its **Interface** is carrying too much incidental knowledge.

#### Deletion test

Deleting `DictationController` would spread real complexity, so it is not useless. But deleting `SessionService` or `DictationController` individually shows their responsibilities are interleaved; neither module owns the whole session concept with strong **Locality**.

#### Solution

Deepen the dictation session module so session lifecycle, cancellation, state observation, mode-specific context, visualizer handoff, and session result handling are concentrated. Keep lower-level recording/text/provider behavior behind adapters, but stop making callers coordinate session internals.

#### Benefits

- **Locality**: one place to reason about “what happens during a dictation session”.
- **Leverage**: tests can cover full session scenarios instead of checking private state or staging callbacks.
- The state machine can become an implementation detail rather than something callers indirectly depend on.

---

### 4. Deepen the configuration module; remove duplicated config schema

#### Files

- `src/dicton/core/config_model.py`
- `src/dicton/adapters/config/config_env.py`
- `src/dicton/shared/config.py`
- `src/dicton/interfaces/web/config_logic.py`
- `src/dicton/interfaces/web/env_io.py`
- `src/dicton/interfaces/config_server.py`
- `tests/test_config.py`
- `tests/test_packaging_surface.py`
- `tests/test_processing_mode.py`

#### Problem

The configuration concept is spread across several modules:

- `AppConfig` defines runtime fields
- `config_env.py` parses environment variables
- `shared/config.py` remains as a legacy singleton
- `config_logic.py` duplicates defaults in `_DEFAULTS`
- `CONFIG_FIELD_MAP`, `CONFIG_BOOL_FIELDS`, and `CONFIG_STRING_FIELDS` define a second schema for the web UI
- `save_config()` mutates `os.environ`, writes `.env`, reloads legacy config, clears STT cache, clears LLM cache, and resets setup state indirectly

The **Interface** is wide: callers must know env names, default values, parsing rules, persistence details, cache invalidation rules, and legacy reload behavior.

Tests show the friction: many tests reload modules, patch `os.environ`, patch private setup state, or patch `Config.CONFIG_DIR`.

#### Deletion test

Deleting `AppConfig` would make typed runtime settings disappear and re-spread config reads. It earns keep. But deleting `config_logic._DEFAULTS` or `CONFIG_FIELD_MAP` would reveal duplicated schema knowledge. Those parts are shallow.

#### Solution

Deepen the configuration module so schema, defaults, env parsing, persistence, setup projections, and post-save invalidation are owned together. The web setup module should consume configuration knowledge, not redefine it.

#### Benefits

- **Locality**: adding `FOO_ENABLED` happens in one module, not four.
- **Leverage**: CLI, runtime, and setup UI share the same config semantics.
- Tests improve: config tests can exercise one settings module instead of module reload gymnastics.

---

### 5. Finish deepening the FN/custom hotkey module

#### Files

- `src/dicton/adapters/input/fn/handler.py`
- `src/dicton/adapters/input/fn/state_machine.py`
- `src/dicton/adapters/input/fn/parser.py`
- `src/dicton/adapters/input/fn/device_registry.py`
- `tests/test_fn_key_handler.py`
- `tests/test_fn_key_hotplug.py`

#### Problem

The previous refactor extracted a parser and a device registry, but the central module is still 813 lines. `state_machine.py` is mostly an enum; the actual transition rules remain inside `FnKeyHandler`.

`FnKeyHandler` owns:

- evdev availability
- pyudev monitoring
- self-pipe wakeup
- select loop
- device refresh debounce
- modifier tracking
- custom hotkey matching
- secondary hotkey matching
- double-tap timing
- mode detection
- callback queue
- lifecycle cleanup

That makes the **Interface** deceptively small but the **Implementation** a multi-concern tangle. Tests patch `sys.modules`, private fields, and import state because the useful behavior is not behind a pure **Seam**.

#### Deletion test

Deleting `state_machine.py` would remove almost no complexity. That module is shallow. The real state machine lives inside the handler.

#### Solution

Deepen the hotkey decision module: timing transitions and mode decisions should be testable without evdev, pyudev, threads, or real devices. The evdev listener should be an adapter around that deeper module.

#### Benefits

- **Locality**: timing bugs and mode bugs become isolated from Linux device bugs.
- **Leverage**: the same transition logic covers FN, custom hotkey, and secondary hotkeys.
- Tests improve: most hotkey behavior can be tested as pure event sequences; only device hotplug needs low-level mocks.

---

### 6. Deepen the LLM text action module; stop bypassing injected provider state

#### Files

- `src/dicton/orchestration/session_service.py`
- `src/dicton/adapters/llm/prompts.py`
- `src/dicton/adapters/llm/factory.py`
- `src/dicton/adapters/llm/provider.py`
- `tests/test_llm_factory.py`
- `tests/test_llm_processor.py`

#### Problem

`SessionService` receives an `llm_provider`, but uses it only for availability:

```python
if self._llm is None or not self._llm.is_available():
    ...
```

Then it imports `act_on_text`, `reformulate`, and `translate`, and those functions call the global LLM factory again. So the injected provider is not the provider that performs the work. That is a broken **Seam**: there is an adapter-shaped thing, but the behavior crosses around it.

`prompts.py` also mixes:

- prompt construction
- use-case policy
- provider fallback
- error fallback
- debug printing

#### Deletion test

Deleting the injected `llm_provider` from `SessionService` would barely change behavior beyond the availability check. That is a signal the **Seam** is hypothetical.

#### Solution

Deepen the text action module so reformulation, translation, and act-on-text each run through one coherent module that owns prompt construction and provider fallback. The session orchestration module should not know how prompt fallback works.

#### Benefits

- **Locality**: provider fallback and prompt behavior stop drifting apart.
- **Leverage**: new text actions reuse the same execution path.
- Tests improve: mode behavior can be tested with a fake LLM adapter instead of patching global provider caches.

## Recommended Priority Order

1. **Active text target module** — likely hides a real behavior bug around selected-text replacement.
2. **LLM text action module** — clear broken **Seam**, contained blast radius.
3. **Configuration module** — high leverage, but wider migration.
4. **Recording/STT pipeline** — important, but touches latency-critical runtime behavior.
5. **Dictation session module** — high leverage, needs careful design.
6. **FN/custom hotkey module** — valuable, but low-level and risky; do after stronger tests.

## Recommended Next Step

Start with the active text target module. It is the best first refactor because the **Seam** is clearly shallow, the blast radius is limited, and the current shape likely causes incorrect `ACT_ON_TEXT` behavior.

Suggested acceptance criteria for that first slice:

- `ACT_ON_TEXT` replaces the selected text when replacement is requested.
- Plain dictation still inserts at cursor.
- Long-text paste fallback still works.
- Tests exercise output behavior through the output **Interface**, not private session internals.
