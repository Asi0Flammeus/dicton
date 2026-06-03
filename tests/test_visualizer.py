from __future__ import annotations

import numpy as np

from dicton import visualizer


class _FakeApp:
    def __init__(self) -> None:
        self.exec_calls = 0
        self.quit_calls = 0

    def exec(self) -> int:
        self.exec_calls += 1
        return 0

    def quit(self) -> None:
        self.quit_calls += 1


class _FakeWindow:
    def __init__(self) -> None:
        self.states: list[str] = []
        self.frames: list[np.ndarray] = []
        self.stop_calls = 0
        self.visible = True

    def apply_state(self, state: str) -> None:
        self.states.append(state)
        self.visible = state in {"recording", "processing"}

    def push_frame(self, frame: np.ndarray) -> None:
        self.frames.append(frame)

    def stop(self) -> None:
        self.stop_calls += 1


def test_visualizer_initializes_qt_window_hidden(monkeypatch) -> None:
    app = _FakeApp()
    window = _FakeWindow()

    monkeypatch.setattr(visualizer.Visualizer, "_create_app", lambda _self: app, raising=False)
    monkeypatch.setattr(
        visualizer.Visualizer,
        "_create_window",
        lambda _self: window,
        raising=False,
    )

    viz = visualizer.Visualizer()
    viz.initialize()

    assert viz._app is app
    assert viz._window is window
    assert window.states == ["idle"]
    assert window.visible is False


def test_visualizer_state_changes_show_recording_processing_and_hide_idle(monkeypatch) -> None:
    app = _FakeApp()
    window = _FakeWindow()
    monkeypatch.setattr(visualizer.Visualizer, "_create_app", lambda _self: app, raising=False)
    monkeypatch.setattr(
        visualizer.Visualizer,
        "_create_window",
        lambda _self: window,
        raising=False,
    )

    viz = visualizer.Visualizer()
    viz.initialize()

    viz.set_state("recording")
    viz.set_state("processing")
    viz.set_state("idle")

    assert window.states == ["idle", "recording", "processing", "idle"]
    assert window.visible is False


def test_visualizer_push_frame_reaches_qt_window_without_copying(monkeypatch) -> None:
    app = _FakeApp()
    window = _FakeWindow()
    monkeypatch.setattr(visualizer.Visualizer, "_create_app", lambda _self: app, raising=False)
    monkeypatch.setattr(
        visualizer.Visualizer,
        "_create_window",
        lambda _self: window,
        raising=False,
    )
    frame = np.arange(256, dtype=np.int16)

    viz = visualizer.Visualizer()
    viz.initialize()
    viz.push_frame(frame)

    assert window.frames == [frame]
    assert window.frames[0] is frame


def test_visualizer_stop_quits_qt_event_loop(monkeypatch) -> None:
    app = _FakeApp()
    window = _FakeWindow()
    monkeypatch.setattr(visualizer.Visualizer, "_create_app", lambda _self: app, raising=False)
    monkeypatch.setattr(
        visualizer.Visualizer,
        "_create_window",
        lambda _self: window,
        raising=False,
    )

    viz = visualizer.Visualizer()
    viz.initialize()
    viz.stop()
    viz.run()

    assert window.stop_calls == 1
    assert app.quit_calls == 1
    assert app.exec_calls == 0
    assert viz.quit_requested is True


def test_level_model_updates_from_audio_and_decays_without_frames() -> None:
    model = visualizer._LevelModel(wave_points=16)
    frame = np.full(1024, 12000, dtype=np.int16)

    model.accept(frame)
    active_level = model.global_level

    assert active_level > 0.0
    assert np.any(model.levels > 0.0)

    model.decay()

    assert 0.0 < model.global_level < active_level


def _drive_level_model(
    amplitude: int, frequency_hz: int = 220, iterations: int = 12
) -> visualizer._LevelModel:
    model = visualizer._LevelModel(wave_points=32)
    samples = np.arange(2400)
    frame = (np.sin(2 * np.pi * frequency_hz * samples / 48_000) * amplitude).astype(np.int16)
    for _ in range(iterations):
        model.accept(frame)
        model.smooth()
    return model


def test_level_model_amplifies_quiet_microphones_to_visible_motion() -> None:
    model = _drive_level_model(amplitude=1000)

    assert model.global_level >= 0.12
    assert float(model.smooth_levels.max()) >= 0.02


def test_level_model_reduces_loud_microphones_to_avoid_saturation() -> None:
    model = _drive_level_model(amplitude=30_000)

    assert model.global_level <= 0.35
    assert float(model.smooth_levels.max()) <= 0.5


def test_level_model_boosts_bass_energy() -> None:
    bass = _drive_level_model(amplitude=3000, frequency_hz=120)
    treble = _drive_level_model(amplitude=3000, frequency_hz=2000)

    assert float(bass.smooth_levels.max()) >= float(treble.smooth_levels.max()) * 1.2


def test_level_model_keeps_spike_contrast_for_tonal_voice_energy() -> None:
    model = _drive_level_model(amplitude=3000, frequency_hz=220)

    assert float(model.smooth_levels.max()) >= float(model.smooth_levels.mean()) * 2.0


def test_level_model_exposes_decibel_drive_for_quiet_speech() -> None:
    model = _drive_level_model(amplitude=100)

    assert -56.0 <= model.input_dbfs <= -50.0
    assert model.visual_drive >= 0.5


def test_visual_model_maps_quiet_speech_to_visible_motion() -> None:
    model = _drive_level_model(amplitude=100)

    assert float(model.amplitude_ratios().max()) >= 0.2


def _rendered_envelope(model: visualizer._LevelModel) -> float:
    return float(model.amplitude_ratios().max())


def test_level_model_keeps_envelope_stable_across_input_volume() -> None:
    # The whole point of the AGC: at steady state a soft speaker and a loud
    # speaker drive the donut to the same size — only the spectral shape differs.
    quiet = _drive_level_model(amplitude=600, iterations=80)
    loud = _drive_level_model(amplitude=20_000, iterations=80)

    ratio = _rendered_envelope(loud) / _rendered_envelope(quiet)

    assert 0.9 <= ratio <= 1.1


def test_presence_gate_does_not_grow_with_loudness() -> None:
    # Above the gate's full-open point, getting louder must not open it further.
    assert visualizer._presence_gate(-30.0) == 1.0
    assert visualizer._presence_gate(-10.0) == 1.0
    assert visualizer._presence_gate(visualizer.GATE_FLOOR_DBFS - 5.0) == 0.0


def test_ring_never_saturates_and_keeps_a_hole() -> None:
    # Even very loud input must leave the donut below the saturation ceiling so a
    # central hole always remains.
    for amplitude in (3_000, 20_000, 32_000):
        loud = _drive_level_model(amplitude=amplitude, iterations=80)
        assert float(loud.amplitude_ratios().max()) <= visualizer.SPIKE_MAX_RATIO + 1e-6
    assert visualizer.SPIKE_MAX_RATIO < 1.0


def test_ring_shape_keeps_band_contrast() -> None:
    # The per-frame spectral normalization must keep visible band-to-band
    # variation rather than collapsing into a uniform (saturated) ring.
    model = _drive_level_model(amplitude=6_000, frequency_hz=220, iterations=80)
    ratios = model.amplitude_ratios()

    assert float(ratios.max()) >= float(ratios.min()) * 1.5


def test_gain_relaxes_toward_unity_during_silence() -> None:
    model = _drive_level_model(amplitude=20_000)
    assert model.adaptive_gain < 0.9  # loud input pulled gain well below unity

    for _ in range(60):
        model.decay()

    assert model.adaptive_gain > 0.95
