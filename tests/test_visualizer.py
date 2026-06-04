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
    samples = np.arange(1024)
    frame = (np.sin(2 * np.pi * 300 * samples / 16_000) * 12000).astype(np.int16)

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
    assert float(model.bar_levels().max()) >= 0.5


def test_level_model_reduces_loud_microphones_to_avoid_saturation() -> None:
    model = _drive_level_model(amplitude=30_000)

    assert model.global_level <= 0.35
    # Bar length is a [0, 1] fraction — loud input can never exceed full length.
    assert float(model.bar_levels().max()) <= 1.0


def test_log_band_positions_are_geometric() -> None:
    positions = visualizer._log_band_positions(401, 32)

    assert np.all(np.diff(positions) > 0)  # strictly increasing
    assert positions[0] == visualizer.BAND_BIN_MIN
    # Constant geometric ratio (log-frequency spacing).
    ratios = positions[1:] / positions[:-1]
    assert float(ratios.std()) < 1e-6


def test_tonal_input_produces_a_localized_peak_bar() -> None:
    # A pure tone must concentrate into a few tall bars, not a flat ring.
    model = _drive_level_model(amplitude=3000, frequency_hz=220, iterations=80)
    bars = model.bar_levels()

    assert float(bars.max()) >= float(bars.mean()) * 3.0


def test_level_model_exposes_decibel_drive_for_quiet_speech() -> None:
    model = _drive_level_model(amplitude=100)

    assert -56.0 <= model.input_dbfs <= -50.0
    assert model.visual_drive >= 0.5


def test_bar_levels_map_quiet_speech_to_visible_bars() -> None:
    model = _drive_level_model(amplitude=100)

    assert float(model.bar_levels().max()) >= 0.2


def test_bar_levels_are_zero_in_silence() -> None:
    model = visualizer._LevelModel(wave_points=visualizer.WAVE_POINTS)
    for _ in range(40):
        model.accept(np.zeros(800, dtype=np.int16))
        model.smooth()

    assert float(model.bar_levels().max()) == 0.0


def test_level_model_keeps_spectrum_stable_across_input_volume() -> None:
    # The AGC's whole point: at steady state a soft speaker and a loud speaker
    # drive the same bar heights — only the spectral shape, not volume, matters.
    quiet = _drive_level_model(amplitude=600, iterations=80)
    loud = _drive_level_model(amplitude=20_000, iterations=80)

    ratio = float(loud.bar_levels().max()) / float(quiet.bar_levels().max())

    assert 0.9 <= ratio <= 1.1


def test_presence_gate_does_not_grow_with_loudness() -> None:
    # Above the gate's full-open point, getting louder must not open it further.
    assert visualizer._presence_gate(-30.0) == 1.0
    assert visualizer._presence_gate(-10.0) == 1.0
    assert visualizer._presence_gate(visualizer.GATE_FLOOR_DBFS - 5.0) == 0.0


def test_broadband_input_renders_short_bars_not_a_solid_disc() -> None:
    # Real microphone audio (speech + room tone) is broadband: a roughly flat
    # spectrum must keep the bars short, not fill the disc. This is the
    # live-saturation regression that the tonal-only tests missed.
    model = visualizer._LevelModel(wave_points=visualizer.WAVE_POINTS)
    rng = np.random.default_rng(0)
    for _ in range(150):
        frame = (rng.standard_normal(800) * 4000).astype(np.int16)
        model.accept(frame)
        model.smooth()

    bars = model.bar_levels()

    assert float(bars.max()) <= 0.5
    assert float(bars.mean()) <= 0.3


def test_gain_relaxes_toward_unity_during_silence() -> None:
    model = _drive_level_model(amplitude=20_000)
    assert model.adaptive_gain < 0.9  # loud input pulled gain well below unity

    for _ in range(60):
        model.decay()

    assert model.adaptive_gain > 0.95
