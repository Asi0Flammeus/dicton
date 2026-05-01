# Refactor Decisions — 2026-05-01

> Source of decisions: grilling session synthesising the two architectural reviews
> (`2026-05-01_codex_improvement_proposal.md`, `2026-05-01_opus_improvement_proposal.md`)
> and their cross-reviews. This document is the single source of truth for Codex
> when slicing implementation issues. Each slice below maps to one GitHub issue.

## Scope of this round

Three slices, in order:

1. **Slice 1 — Delete ACT_ON_TEXT feature entirely.** (Issue-ready below.)
2. **Slice 2 — Controller/session posture refactor.** (Posture not yet locked; see Q5.)
3. **Slice 3 — Move `os.environ` reads out of `core/`.** (To be authored.)

Out of scope this round: config consolidation (`AppConfig` SSOT), LLM dispatch
refactor (`prompts.py` / `TextActions`), recording-pipeline split
(`SpeechRecognizer` god-object), FN handler state-machine extraction,
`adapters/config/` rename. These are deferred to a future round once the posture
decision is settled.

---

## Slice 1 — Delete ACT_ON_TEXT feature entirely

### Context

ACT_ON_TEXT was a mode where the user selected text, pressed FN+Shift, spoke an
instruction, and the LLM would replace the selection with the result. The feature
was retired by product decision; the README no longer references it. The code is
still present and the `replace_selection` plumbing is broken in two places:

- `SessionService.output_result(text, mode, replace_selection)`
  (`orchestration/session_service.py:267-281`) accepts the flag and ignores it,
  yet still notifies the user "✓ Text Replaced".
- The `TextOutput.replace_selection()` method exists on the abstract port and all
  4 platform adapters, but **nothing in the call path ever invokes it**. Even if
  `output_result` had honoured the flag, it would have called `insert_text`, not
  `replace_selection`. The platform `replace_selection` implementations are dead
  code.

The two architectural reviews flagged this as a bug to fix; the correct
resolution is to delete the feature, which removes the bug along with several
adjacent concerns (selection capture, secondary hotkey config, LLM prompt,
unused output methods).

### Decision

Delete ACT_ON_TEXT and all code reachable only from it. Single PR.

### Files to modify

**Removed code:**

- `src/dicton/core/processing_mode.py`
  - `ProcessingMode.ACT_ON_TEXT` enum entry (line 23)
  - `ProcessingMode.ACT_ON_TEXT` color mapping (line 33)
  - `ProcessingMode.ACT_ON_TEXT` spec (lines 86-87)
  - `requires_selection: bool` field on `ModeSpec` (line 43) — verify no remaining
    consumer; remove if vestigial
- `src/dicton/core/config_model.py`
  - `secondary_hotkey_act_on_text: str` field (line 45)
- `src/dicton/adapters/config/config_env.py`
  - `secondary_hotkey_act_on_text=...` line (67)
- `src/dicton/shared/config.py`
  - `SECONDARY_HOTKEY_ACT_ON_TEXT` env var (lines 173-174, 280)
  - (Note: `shared/config.py` is being deleted in a future config-consolidation
    round; this slice only removes the ACT_ON_TEXT field, leaves the file.)
- `src/dicton/interfaces/web/config_logic.py`
  - `SECONDARY_HOTKEY_ACT_ON_TEXT` defaults entry (line 34)
  - `secondary_hotkey_act_on_text` field map (line 60)
  - `secondary_hotkey_act_on_text` env_vars.get call (lines 136-137)
- `src/dicton/orchestration/session_service.py`
  - `selection_reader` constructor kwarg (line 25) and `self._selection`
    assignment (line 33)
  - ACT_ON_TEXT branch in `start_recording` (lines 85-94)
  - `_capture_selection_for_act_on_text` method (lines 205-224)
  - ACT_ON_TEXT branch in `_record_and_transcribe` (lines 164-167)
  - ACT_ON_TEXT mode-name entry (line 153)
  - ACT_ON_TEXT branch in `process_text` (lines 251-252)
  - `act_on_text` import (line 244 — kept import line, just remove the symbol)
  - ACT_ON_TEXT branch + "✓ Text Replaced" notify in `output_result` (lines 276-278)
  - `replace_selection: bool` parameter on `output_result` signature (line 271)
- `src/dicton/orchestration/runtime_service.py`
  - `secondary_hotkey_act_on_text=...` propagation (line 65)
- `src/dicton/orchestration/container.py`
  - `selection_reader` kwarg passed to `SessionService` (line 148)
  - (Container still needs `selection_reader` for `LinuxTextOutput` — keep that
    construction and injection at lines 112-114, only stop passing it to
    `SessionService`.)
- `src/dicton/adapters/llm/prompts.py`
  - `act_on_text` function (line 43) and any helpers used only by it
- `src/dicton/adapters/input/fn/handler.py`
  - `secondary_hotkey_act_on_text` constructor kwarg (line 60)
  - `self._secondary_hotkey_act_on_text_cfg` (line 86)
  - debug log mention (line 159)
  - propagation to parser (line 164)
  - FN+Shift docstring branch (line 656)
  - `ProcessingMode.ACT_ON_TEXT` return in mode detection (line 666)
- `src/dicton/adapters/input/fn/parser.py`
  - `secondary_hotkey_act_on_text` parameter (line 162)
  - hotkey wiring (lines 176-178)
- `src/dicton/core/ports.py`
  - `replace_selection: bool` parameter on `TextOutput.output(...)` (line 67)
- `src/dicton/adapters/config/text_processing.py`
  - `replace_selection: bool` parameter on output adapter (lines 27-28)
- `src/dicton/core/controller.py`
  - `replace_selection=session.selected_text is not None` arg (line 171) — call
    becomes `self._text_output.output(result, mode)`
  - `selected_text` field on `SessionContext` (line 30) becomes unused; remove
    the field (and the dataclass if it becomes empty)
- `src/dicton/adapters/output/base.py`
  - `replace_selection` abstract method (line 32)
- `src/dicton/adapters/output/linux.py`
  - `LinuxTextOutput.replace_selection` method (lines 86-109)
- `src/dicton/adapters/output/macos.py`
  - `MacosTextOutput.replace_selection` method (line 24)
  - inline `paste_text` body now that it no longer delegates (line 22)
- `src/dicton/adapters/output/windows.py`
  - `WindowsTextOutput.replace_selection` method (line 33)
  - inline `paste_text` body now that it no longer delegates (line 31)
- `src/dicton/adapters/output/fallback.py`
  - `PynputTextOutput.replace_selection` method (line 50)
- `src/dicton/adapters/output/selection_base.py`
  - `SelectionReader.get_selection` abstract method (lines 11-13)
  - `SelectionReader.has_selection` method (lines 15-18)
  - `NullSelectionReader.get_selection` (lines 32-33)
- `src/dicton/adapters/output/selection_x11.py`, `selection_wayland.py`,
  `selection_macos.py`, `selection_windows.py`
  - `get_selection` implementations on each

**Renamed in this slice (`SelectionReader` → `Clipboard`):**

After `get_selection`/`has_selection` are deleted, the class only handles
clipboard read/write. Renaming for accuracy now (instead of deferring) keeps
the slice cohesive — same PR, same review.

- Class names:
  - `SelectionReader` → `Clipboard`
  - `NullSelectionReader` → `NullClipboard`
  - `X11SelectionReader` → `X11Clipboard`
  - `WaylandSelectionReader` → `WaylandClipboard`
  - `MacOSSelectionReader` → `MacOSClipboard`
  - `WindowsSelectionReader` → `WindowsClipboard`
- File names:
  - `adapters/output/selection_base.py` → `clipboard_base.py`
  - `adapters/output/selection_x11.py` → `clipboard_x11.py`
  - `adapters/output/selection_wayland.py` → `clipboard_wayland.py`
  - `adapters/output/selection_macos.py` → `clipboard_macos.py`
  - `adapters/output/selection_windows.py` → `clipboard_windows.py`
  - `adapters/output/selection_factory.py` → `clipboard_factory.py`
- Factory function: `get_selection_reader()` → `get_clipboard()`
- Constructor kwarg on `LinuxTextOutput` (`adapters/output/linux.py:16`):
  `selection_reader=` → `clipboard=`
- Private attr on `LinuxTextOutput`: `self._selection` → `self._clipboard`
- Container variable (`orchestration/container.py:112-114, 148`):
  `selection_reader = get_selection_reader(...)` → `clipboard = get_clipboard(...)`
- Test files renamed:
  - `tests/test_selection_x11.py` → `tests/test_clipboard_x11.py`
  - `tests/test_selection_wayland.py` → `tests/test_clipboard_wayland.py`
- Method names on the class (`get_clipboard`, `set_clipboard`) **kept as-is** —
  they're already accurate.
- `tests/test_text_output_linux.py`
  - `test_replace_selection_uses_ctrl_v` (line 78)
- `tests/test_text_output_windows.py`
  - `test_replace_selection_copies_to_clipboard_and_pastes` (line 53)
- `tests/test_selection_x11.py`, `tests/test_selection_wayland.py`
  - All `get_selection*` tests (keep `set_clipboard`/`get_clipboard` tests)
- `tests/test_controller.py`
  - Update fake `output(...)` to drop `replace_selection` param (lines 51-52)
- Any test asserting on ACT_ON_TEXT mode behaviour (grep before deleting)

**Kept (do NOT touch):**

- `SelectionReader` class itself, plus `get_clipboard` / `set_clipboard` on every
  platform implementation. Used by `LinuxTextOutput.paste_text` for the
  long-text paste path (the strategy that avoids `xdotool type` for >10-word
  output and reads the clipboard back to verify async X11 propagation).
- `selection_reader` injection into `LinuxTextOutput` in `container.py:112-114`.
- All `paste_text` methods (renamed or restructured fine, but keep behaviour).

### Acceptance criteria

- `rg "ACT_ON_TEXT|act_on_text|replace_selection|_capture_selection|secondary_hotkey_act_on_text|SelectionReader|selection_reader|selection_base|selection_x11|selection_wayland|selection_macos|selection_windows|selection_factory|get_selection_reader"
  src/ tests/` returns zero hits.
- `./scripts/check.sh` passes.
- `LinuxTextOutput.paste_text` still works for long transcriptions (manual test:
  dictate a 200-word paragraph in BASIC mode, confirm clipboard-paste path
  triggers, output appears in target app).
- `set_clipboard` / `get_clipboard` tests in `test_selection_x11.py` and
  `test_selection_wayland.py` still pass.
- Tray icons still update on state changes (no regression in
  `add_state_observer` behaviour).
- Version bumped in `src/dicton/__init__.py` (project rule).

### Non-goals

- No restructuring of `paste_text` strategy or threshold logic (the long-text
  paste path stays exactly as is, just under the new `Clipboard` name).
- No changes to the controller/session split — that is Slice 2.
- No rename of method names on the clipboard class (`get_clipboard`,
  `set_clipboard` are already accurate).

### Dependencies

None. This slice is independent of Slice 2 and Slice 3 and should land first.

---

## Slice 2 — Controller/Session posture refactor

### Architecture decision

**Posture (c): Collapse + retire `core/controller.py`.** Fold
`DictationController.run_session` into `SessionService._record_and_transcribe`.
Delete `core/controller.py`. Keep `core/state_machine.py` (it has a real
external consumer — see use case below). Kill the bound-method ouroboros in
`container.py`.

### Consequences

**Removed:**

- `src/dicton/core/controller.py` — entire file
  - `DictationController` class
  - `SessionContext` dataclass (becomes empty after Slice 1, dies here)
  - `_NoopAudioSessionControl` (moves inline into `SessionService` if still
    needed, or dies)
- `tests/test_controller.py` — entire file (assertions migrate into
  `tests/test_session_service.py` as integration tests)
- The 5-step ouroboros wiring in `orchestration/container.py:153-163`:
  ```
  session_service.bind_controller(
      DictationController(
          audio_capture=AudioCaptureAdapter(recognizer, chunk_manager=chunk_manager),
          stt=STTAdapter(recognizer, chunk_manager=chunk_manager),
          text_processor=TextProcessorAdapter(session_service.process_text),
          text_output=TextOutputAdapter(session_service.output_result),
          ...
      )
  )
  ```
  Replaced with direct injection.
- `SessionService.bind_controller` two-step construction (lines 50-52)

**Adapter + port deletion table:**

| Adapter | Adapter file | Port (`core/ports.py`) |
|---|---|---|
| `TextProcessorAdapter` | DELETE (`adapters/config/text_processing.py`) | DELETE (`TextProcessor`) |
| `TextOutputAdapter` | DELETE (`adapters/config/text_processing.py`) | **KEEP** (`TextOutput` — 4 platform impls) |
| `AudioCaptureAdapter` | DELETE (`adapters/audio/capture_adapter.py`) | DELETE (`AudioCapture`) |
| `STTAdapter` | DELETE (`adapters/audio/stt_adapter.py`) | DELETE (`STTService`) |
| `MetricsAdapter` | DELETE (`adapters/config/metrics.py`) | DELETE (`MetricsSink`) |

Net: 5 adapter files deleted, 4 ports deleted, 1 port retained.

Rationale per port:

- `TextOutput` is a real seam — 4 platform impls (`LinuxTextOutput`,
  `MacosTextOutput`, `WindowsTextOutput`, `PynputTextOutput`) selected by
  `output_factory`. Earned its keep.
- `TextProcessor`, `AudioCapture`, `STTService`, `MetricsSink` are all
  single-impl with one in-house caller. No second impl exists, none planned.
  Protocol discipline is reserved for external boundaries (OS, vendor SDKs,
  file I/O); in-house collaborators can be imported concretely.
- The `STTProvider` chain (Whisper / Faster-Whisper / Cloud) inside
  `SpeechRecognizer` remains the real STT seam — the outer `STTService`
  port was a second seam over the same swap.

**Test consequences:**

- `test_session_service.py:51` `_DummyMetrics()` survives as a duck-typed fake
  (no `MetricsSink` Protocol inheritance needed).
- `test_wiring_smoke.py:111-127` adapter-conformance assertion deleted along
  with `MetricsAdapter`.
- `test_controller.py` deleted entirely (test logic migrates to
  `test_session_service.py`).
- `SessionService` imports `LatencyTracker`, `SpeechRecognizer`, `ChunkManager`
  concretely. Tests inject fakes via duck typing.

**Moved into `SessionService`:**

- The linear pipeline body from `controller.run_session()` becomes
  `SessionService._record_and_transcribe()` (or merges into it — `_record_and_transcribe`
  already calls into `run_session`).
- `cancel_token` ownership: was in controller, now in `SessionService`.
- State machine ownership: was in controller, now in `SessionService` (still
  observable via existing `add_state_observer` API — no change for callers).
- The `tracker.measure(...)` blocks for audio_capture / stt_transcription /
  text_processing / text_output stay; they now wrap inline calls instead of
  port calls.

**Kept (do NOT touch):**

- `src/dicton/core/state_machine.py` — `SessionState`, `SessionEvent`,
  `SessionStateMachine`. Real consumer: see use case.
- `src/dicton/core/processing_mode.py` — domain enums + mode specs.
- `src/dicton/core/cancel_token.py` — cooperative cancellation primitive.
- `src/dicton/core/ports.py` — `TextOutput`, `Notifications`, `LLMProvider`,
  `Metrics` etc. Some Protocols may become single-impl after the adapter
  deletion sub-decision; that's evaluated in Q6.
- `SessionService.add_state_observer(callback)` — public API, tray adapters
  depend on it.

**`core/` final shape after Slice 2:**

```
core/
├── cancel_token.py
├── ports.py
├── processing_mode.py
└── state_machine.py
```

Down from 5 modules to 4. Honest naming: this codebase's "core" is enums +
state + protocols, not domain logic. The hexagonal scaffolding stays where
it earns its keep (ports for swappable output/STT/LLM/notifications) and
retreats where it didn't (the controller-vs-orchestrator split was theatre).

### Use case validation

- **Tray icon updates**: 4 tray adapters (`tray_linux_gtk.py`,
  `tray_macos.py`, `tray_windows.py`, `tray_base.py`) call
  `SessionService.add_state_observer(self._tray.on_state_change)` via
  `runtime_service.py:173`. After Slice 2, `SessionService` still owns the
  state machine and exposes the same observer API. **Tray works unchanged.**
- **External (non-orchestrated) caller of `run_session()`**: none today, none
  planned in next 3 months (confirmed). The reusable-controller-as-primitive
  argument for posture (b) does not apply.
- **Cancel-on-tap**: `SessionService.cancel_recording()` currently delegates
  to `controller.cancel()`. After Slice 2, it cancels the inline cancel_token
  and stops `audio_capture`/`audio_control` directly. Behaviour-equivalent.
- **Cancel mid-processing**: same — `cancel_token.cancelled` checks happen at
  the same pipeline points, just inline now.

### Acceptance criteria

- `src/dicton/core/controller.py` does not exist.
- `src/dicton/core/` contains only `cancel_token.py`, `ports.py`,
  `processing_mode.py`, `state_machine.py`, `__init__.py`.
- `rg "DictationController|bind_controller|SessionContext"
  src/ tests/` returns zero hits (`SessionContext` only existed for the
  Slice-1-deleted `selected_text` field).
- `rg "from .*core.controller"` returns zero hits.
- `SessionService.add_state_observer` works unchanged; tray adapters
  receive `SessionState` transitions correctly.
- All existing `test_session_service.py` and `test_state_machine.py` tests pass.
- Tests previously in `test_controller.py` either migrate to
  `test_session_service.py` or are dropped if redundant; no behavioural test
  coverage lost.
- Manual smoke test: dictate in BASIC mode, REFORMULATION mode, RAW mode,
  TRANSLATION mode, TRANSLATE_REFORMAT mode. All produce expected output.
- Cancel-by-tap during recording works.
- Cancel during processing (rapid double-tap) works.
- `./scripts/check.sh` passes.
- Version bumped in `src/dicton/__init__.py`.

### Non-goals

- No port renaming or restructuring (`core/ports.py` content stays).
- No changes to LLM dispatch (`prompts.py` still does its own provider lookup —
  that is a future round).
- No changes to recording pipeline (`SpeechRecognizer` stays the god-object —
  future round).
- No changes to state machine internals (still pure enum + transition table).

### Dependencies

- **Hard dependency on Slice 1.** `SessionService` shape after Slice 1 is the
  starting point for the collapse. Doing Slice 2 first would have to re-do
  the ACT_ON_TEXT branch deletions inline.


---

## Slice 3 — Remove `os.environ` reads from `core/`

### Architecture decision

Thread `enable_advanced_modes: bool` as an explicit argument to
`is_mode_enabled`. **Delete** the `advanced_modes_enabled()` wrapper entirely
(no caller needs it once the bool is threaded). Add an architecture test that
asserts no `core/*.py` file imports `os`.

`is_mode_enabled` stays in `core/` — it's a pure function over the mode value,
domain logic that belongs next to the `ProcessingMode` enum. The fix isn't
*where* the function lives; it's that it secretly read the environment.

### Consequences

**`core/processing_mode.py` changes:**

- Remove `import os` (line 7).
- Delete `advanced_modes_enabled()` function (lines 102-104).
- Change `is_mode_enabled` signature:
  - From: `def is_mode_enabled(mode: ProcessingMode) -> bool`
  - To:   `def is_mode_enabled(mode: ProcessingMode, enable_advanced_modes: bool) -> bool`
- Body becomes:
  ```python
  if mode in {ProcessingMode.BASIC, ProcessingMode.TRANSLATION}:
      return True
  return enable_advanced_modes
  ```

**Caller updates (pass `app_config.enable_advanced_modes` explicitly):**

- `src/dicton/orchestration/session_service.py:79` —
  `if not is_mode_enabled(mode, self._app_config.enable_advanced_modes):`
- `src/dicton/orchestration/session_service.py:233` — same change in
  `process_text`.

**FN handler cascade (currently calls `advanced_modes_enabled()` directly):**

- `src/dicton/adapters/input/fn/handler.py:19` — drop
  `advanced_modes_enabled` from the import.
- `src/dicton/adapters/input/fn/handler.py` — add
  `enable_advanced_modes: bool` constructor kwarg (alongside existing
  `secondary_hotkey_*` config kwargs). Store as `self._enable_advanced_modes`.
- `src/dicton/adapters/input/fn/handler.py:165` — pass
  `advanced_modes_enabled=self._enable_advanced_modes` to parser (no more
  function call).
- `src/dicton/adapters/input/fn/handler.py:661, 665, 667, 669` — replace
  `advanced_modes_enabled()` with `self._enable_advanced_modes`.
- `src/dicton/orchestration/container.py` — at FN handler construction, pass
  `enable_advanced_modes=app_config.enable_advanced_modes`.

**`shared/processing_mode.py` shim:**

- Re-exports `advanced_modes_enabled` (line 7) and `is_mode_enabled` (line 10).
  Drop the `advanced_modes_enabled` re-export. Keep `is_mode_enabled` re-export
  for now (legacy callers will be cleaned up in the future config-consolidation
  round). Tests `test_processing_mode.py` import from
  `dicton.core.processing_mode` directly, so the shim's removal does not block
  this slice.

**Architecture test (new file):**

- `tests/test_core_no_env_reads.py`:
  - Walks every `*.py` file in `src/dicton/core/`.
  - Asserts none contains `import os`, `from os import`, `os.getenv`,
    `os.environ`, or `os.environ[`.
  - Skips `__init__.py` if empty.
  - Fails with the offending file path on first hit.

**Test updates:**

- `tests/test_processing_mode.py:5-29` — currently uses `monkeypatch.setenv`
  /`monkeypatch.delenv` for `ENABLE_ADVANCED_MODES`. Rewrite to call
  `is_mode_enabled(mode, enable_advanced_modes=False)` and
  `is_mode_enabled(mode, enable_advanced_modes=True)` directly. No env
  manipulation needed.
- `tests/test_session_service.py` — if any test exercised the
  enable-advanced-modes path, update to construct `app_config` with the
  desired bool instead of `monkeypatch.setenv`.

### Use case validation

- **Runtime behaviour**: `app_config` is already loaded once at startup from
  env (`adapters/config/config_env.py:92`
  `enable_advanced_modes=_env_bool("ENABLE_ADVANCED_MODES", "false")`). The
  same value flows to `SessionService` and FN handler — no behavioural change.
- **Tests**: stop needing `monkeypatch.setenv("ENABLE_ADVANCED_MODES", ...)`.
  Construct `AppConfig(enable_advanced_modes=True)` or pass the bool directly
  to `is_mode_enabled`. Faster, fewer module reloads, no global-state leak
  between tests.
- **CI enforcement**: `tests/test_core_no_env_reads.py` catches future
  regressions automatically. Any PR adding `import os` or env reads to
  `core/` fails the test suite.

### Acceptance criteria

- `rg "import os|from os|os\.getenv|os\.environ" src/dicton/core/` returns
  zero hits.
- `rg "advanced_modes_enabled" src/ tests/` returns zero hits (the function is
  fully deleted, no callers).
- `rg "is_mode_enabled" src/` shows only call sites with the new 2-arg
  signature.
- `tests/test_core_no_env_reads.py` exists and passes.
- `tests/test_processing_mode.py` no longer uses `monkeypatch.setenv` /
  `monkeypatch.delenv`.
- `./scripts/check.sh` passes.
- Manual smoke: with `ENABLE_ADVANCED_MODES=false`, REFORMULATION mode is
  rejected; with `ENABLE_ADVANCED_MODES=true`, it is accepted.
- FN handler still routes hotkeys correctly under both env values.
- Version bumped in `src/dicton/__init__.py`.

### Non-goals

- No fix for `interfaces/web/config_logic.py:117` env read (that's
  interfaces-layer, lives outside `core/`, and is already covered by the
  upcoming config-consolidation round).
- No fix for `shared/config.py:178, 281` env reads (also outside `core/`,
  and `shared/config.py` itself is slated for deletion in the
  config-consolidation round).
- No broader env-read audit across `adapters/` (out of scope).
- No `AppConfig` consolidation (separate future round).

### Dependencies

- **Independent of Slice 1 and Slice 2.** Can land in any order. Recommended
  order: Slice 1 → Slice 2 → Slice 3, but no hard ordering required.
- Slice 1 deletes `ProcessingMode.ACT_ON_TEXT`, which simplifies the
  `is_mode_enabled` test surface. If Slice 3 lands first, the test will assert
  `ACT_ON_TEXT` enablement and need updating in Slice 1. Cleaner to land
  Slice 1 first.

---

## Suggested Codex slicing

One GitHub issue per slice. Recommended PR order:

1. Slice 1 (ACT_ON_TEXT deletion + `Clipboard` rename) — independent, largest
   blast radius, lands first to clear the surface.
2. Slice 2 (controller/session collapse) — depends on Slice 1 having reduced
   `SessionService` surface area.
3. Slice 3 (`os.environ` out of core + arch test) — independent, can be
   parallelised with Slice 2 if desired.

After all three land, the next round (separately authored) covers: config
consolidation (`AppConfig` SSOT + `shared/config.py` deletion), LLM dispatch
(`prompts.py` purity + `TextActions`), recording-pipeline split
(`SpeechRecognizer` god-object), FN handler state-machine extraction.
