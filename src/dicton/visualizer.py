"""Circular audio spectrum visualizer (radial bars) backed by PySide6/QPainter."""

from __future__ import annotations

import contextlib
import logging
import math
import os
import queue
import sys
import threading
from dataclasses import dataclass
from typing import Any

import numpy as np

log = logging.getLogger("dicton")

SIZE = 200
WAVE_POINTS = 90

COLOR_MAIN = (188, 82, 21)
COLOR_MID = (150, 65, 17)
COLOR_DIM = (95, 42, 11)
COLOR_GLOW = (218, 112, 44)
BACKGROUND = (20, 20, 24)

# Automatic gain control: the visual envelope is normalized toward a constant
# target loudness so the donut keeps roughly the same shape whatever the input
# volume — quiet input is amplified, loud input is attenuated. The wide gain
# range lets soft speech reach the target without leaving loud speech saturated.
VISUAL_TARGET_RMS = 0.22
VISUAL_MIN_GAIN = 0.35
VISUAL_MAX_GAIN = 40.0
VISUAL_GAIN_ATTACK = 0.28
VISUAL_GAIN_RELEASE = 0.18
VISUAL_GAIN_RELAX = 0.08
PEAK_HOLD_FRAMES = 30
RMS_NORMALIZATION = 32768
SPECTRUM_NORMALIZATION = 40_000_000
DBFS_FLOOR = -55.0
ACTIVE_RMS_THRESHOLD = 0.001
# Presence gate: drive stays ≈1 while speech is present and only fades for
# genuine silence, so loudness no longer scales the visualization.
GATE_FLOOR_DBFS = -54.0
GATE_FULL_DBFS = -42.0
MIN_ACTIVE_VISUAL_DRIVE = 0.8
VISUAL_DRIVE_ATTACK = 0.35
VISUAL_DRIVE_RELEASE = 0.12
# Below this gate value the ring is treated as fully retracted (silent).
GATE_SILENCE_EPS = 0.02
# Circular spectrum. Bands are spaced geometrically over the FFT bins
# (log-frequency — equal visual width per octave, so bass does not dominate),
# each band's magnitude is taken in dB (20·log10) and mapped from a
# [floor, ceiling] dBFS window onto a [0, 1] bar length. The AGC has already
# volume-normalized the magnitude, so the same window works at any input level.
# Tuned from measured speech/noise: peaks land near -22 dB, noise floor ~-45 dB.
BAND_BIN_MIN = 2
BAND_BIN_FRACTION = 0.55
SPECTRUM_DB_FLOOR = -50.0
SPECTRUM_DB_CEILING = -28.0
# Every bar keeps a small minimum length while sound is present, so the whole
# circle stays populated (a spectrum, not a lopsided arc); louder bands grow on
# top. The bands are also mirrored (see _log_band_edges / accept) so the ring is
# left/right symmetric rather than energy piling up on one side.
BAR_BASELINE = 0.14
# Bar layout (px, within the SIZE×SIZE widget centered at SIZE/2): bars radiate
# outward from a central circle of radius BAR_INNER_RADIUS, up to BAR_MAX_LENGTH.
BAR_INNER_RADIUS = 48
BAR_MAX_LENGTH = 46
BAR_WIDTH = 2.6
# Translucent circular backdrop (needs an X11 compositor for true transparency,
# e.g. picom): a dark disc behind the spectrum, transparent at the corners, so
# the widget reads as a circle on the desktop instead of a black square.
BACKDROP_RADIUS = 96
BACKDROP_ALPHA = 205

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = sys.platform.startswith("win")
IS_X11 = IS_LINUX and bool(os.environ.get("DISPLAY"))
ACTIVE_STATES = {"recording", "processing"}


@dataclass(frozen=True)
class _QtBindings:
    QtCore: Any
    QtGui: Any
    QtWidgets: Any


def _load_qt() -> _QtBindings:
    from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore[import-not-found]

    return _QtBindings(QtCore=QtCore, QtGui=QtGui, QtWidgets=QtWidgets)


class _LevelModel:
    def __init__(self, wave_points: int = WAVE_POINTS) -> None:
        self.wave_points = wave_points
        self.levels = np.zeros(wave_points, dtype=np.float32)
        self.smooth_levels = np.zeros(wave_points, dtype=np.float32)
        self.global_level = 0.0
        self.input_dbfs = DBFS_FLOOR
        self.visual_drive = 0.0
        self.adaptive_gain = 1.0
        self.peak_level = 0.0
        self.peak_hold_counter = 0
        self._angles = np.linspace(math.pi / 2, math.pi / 2 + math.tau, wave_points, endpoint=False)
        self.cos = np.cos(self._angles)
        self.sin = np.sin(self._angles)
        # Half the bars carry unique bands; the ring is mirrored for symmetry.
        # Band edges are rebuilt when the FFT size changes.
        self._n_half = (wave_points + 1) // 2
        self._band_edges = np.zeros(self._n_half + 1, dtype=np.float64)
        self._band_fft_size = -1

    def accept(self, frame: np.ndarray) -> None:
        if frame.size == 0:
            self.decay()
            return
        data = frame.astype(np.float32, copy=False)
        raw_rms = float(np.sqrt(np.mean(data * data))) / RMS_NORMALIZATION
        self.input_dbfs = _dbfs(raw_rms)
        active = raw_rms > ACTIVE_RMS_THRESHOLD

        # Presence gate: ≈1 while speech is present, fades only for true silence.
        target_drive = _presence_gate(self.input_dbfs)
        if active:
            target_drive = max(MIN_ACTIVE_VISUAL_DRIVE, target_drive)
        drive_rate = (
            VISUAL_DRIVE_ATTACK if target_drive > self.visual_drive else VISUAL_DRIVE_RELEASE
        )
        self.visual_drive += (target_drive - self.visual_drive) * drive_rate

        if raw_rms > self.peak_level:
            self.peak_level = raw_rms
            self.peak_hold_counter = PEAK_HOLD_FRAMES
        elif self.peak_hold_counter > 0:
            self.peak_hold_counter -= 1
        else:
            self.peak_level *= 0.995

        # Automatic gain control: amplify quiet input, attenuate loud input toward
        # a constant target. Gain only tracks while sound is present; during
        # silence it relaxes back to unity so the next onset is not over-amplified.
        if active:
            target_gain = VISUAL_TARGET_RMS / max(raw_rms, 1e-6)
            target_gain = max(VISUAL_MIN_GAIN, min(VISUAL_MAX_GAIN, target_gain))
            rate = VISUAL_GAIN_ATTACK if target_gain > self.adaptive_gain else VISUAL_GAIN_RELEASE
            self.adaptive_gain += (target_gain - self.adaptive_gain) * rate
        else:
            self.adaptive_gain += (1.0 - self.adaptive_gain) * VISUAL_GAIN_RELAX
        self.adaptive_gain = max(VISUAL_MIN_GAIN, min(VISUAL_MAX_GAIN, self.adaptive_gain))
        rms = _soft_compress(raw_rms * self.adaptive_gain)
        self.global_level = self.global_level * 0.7 + rms * 0.3

        fft = np.abs(np.fft.rfft(data))
        fft_size = len(fft)
        if fft_size != self._band_fft_size:
            self._band_edges = _log_band_edges(fft_size, self._n_half)
            self._band_fft_size = fft_size
        # Aggregate each log band by its peak bin (catches sharp tones), in dB,
        # mapped from a fixed dBFS window onto [0, 1]. The AGC keeps the
        # magnitude volume-normalized, so the window is volume-independent.
        edges = self._band_edges
        mag = np.empty(self._n_half, dtype=np.float64)
        for j in range(self._n_half):
            lo = int(edges[j])
            hi = max(lo + 1, int(edges[j + 1]))
            mag[j] = fft[lo:hi].max()
        scaled = (mag / SPECTRUM_NORMALIZATION) * self.adaptive_gain
        db = 20.0 * np.log10(scaled + 1e-9)
        half = np.clip(
            (db - SPECTRUM_DB_FLOOR) / (SPECTRUM_DB_CEILING - SPECTRUM_DB_FLOOR), 0.0, 1.0
        )
        # Mirror the bands so the ring is left/right symmetric.
        norm = np.concatenate([half, half[::-1]])[: self.wave_points]
        self.levels = self.levels * 0.4 + norm.astype(np.float32) * 0.6

    def decay(self) -> None:
        self.levels *= 0.9
        self.global_level *= 0.9
        self.visual_drive *= 0.9
        self.peak_level *= 0.995
        self.adaptive_gain += (1.0 - self.adaptive_gain) * VISUAL_GAIN_RELAX

    def smooth(self) -> None:
        self.smooth_levels = self.smooth_levels * 0.82 + self.levels * 0.18

    def bar_levels(self) -> np.ndarray:
        """Per-bar length as a fraction [0, 1] of ``BAR_MAX_LENGTH``.

        While speech is present every bar keeps at least ``BAR_BASELINE`` so the
        whole circle stays populated, with louder bands rising on top; the gate
        scales the whole ring so it retracts to nothing in silence.
        Volume-independent thanks to the AGC.
        """
        if self.visual_drive <= GATE_SILENCE_EPS:
            return np.zeros(self.wave_points, dtype=np.float32)
        shaped = BAR_BASELINE + (1.0 - BAR_BASELINE) * self.smooth_levels
        return np.clip(shaped * self.visual_drive, 0.0, 1.0).astype(np.float32)


class Visualizer:
    """Thread-safe public visualizer API used by the runtime and pipeline."""

    def __init__(self) -> None:
        self._state = "idle"
        self._state_lock = threading.Lock()
        self._visible = False
        self._stop = threading.Event()
        self._preinit_frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=128)
        self.quit_requested = False
        self._app: Any | None = None
        self._window: Any | None = None
        self._bridge: Any | None = None
        self._qt_stop_requested = False

    def push_frame(self, frame: np.ndarray) -> None:
        if self._window is None:
            with contextlib.suppress(queue.Full):
                self._preinit_frames.put_nowait(frame)
            return
        if self._bridge is not None:
            self._bridge.frame_received.emit(frame)
        else:
            self._window.push_frame(frame)

    def set_state(self, state: str) -> None:
        with self._state_lock:
            previous = self._state
            if state == previous:
                return
            self._state = state
        log.info("visualizer state: %s -> %s", previous, state)
        self._publish_state(state)

    def stop(self) -> None:
        self._stop.set()
        self.quit_requested = True
        self._request_qt_stop()

    def initialize(self) -> None:
        if self._app is not None and self._window is not None:
            return
        log.info(
            "visualizer starting: platform linux=%s x11=%s windows=%s backend=qt",
            IS_LINUX,
            IS_X11,
            IS_WINDOWS,
        )
        self._app = self._create_app()
        self._window = self._create_window()
        app = self._app
        if self._bridge is not None and app is not None:
            self._bridge.stop_requested.connect(app.quit)
        self._publish_state(self._state)
        self._drain_preinit_frames()
        log.info("visualizer qt initialized")

    def run(self) -> None:
        if self._app is None or self._window is None:
            self.initialize()
        app = self._app
        if self._stop.is_set() or app is None:
            return
        try:
            log.info("visualizer qt loop begin")
            app.exec()
            self.quit_requested = self._stop.is_set()
            log.info("visualizer qt loop exited")
        except Exception:
            self.quit_requested = False
            log.exception("visualizer loop crashed — daemon continues without animation")
        finally:
            self._request_qt_stop()

    def _create_app(self) -> Any:
        qt = _load_qt()
        app = qt.QtWidgets.QApplication.instance()
        if app is None:
            app = qt.QtWidgets.QApplication(["dicton"])
        app.setApplicationName("dicton")
        app.setQuitOnLastWindowClosed(False)
        return app

    def _create_window(self) -> Any:
        qt = _load_qt()
        bridge = _new_bridge(qt)
        window = _new_window(qt, bridge)
        self._bridge = bridge
        return window

    def _publish_state(self, state: str) -> None:
        visible = state in ACTIVE_STATES
        if visible != self._visible:
            log.info("visualizer visibility transition: visible=%s state=%s", visible, state)
            self._visible = visible
        if self._window is None:
            return
        if self._bridge is not None:
            self._bridge.state_changed.emit(state)
        else:
            self._window.apply_state(state)

    def _request_qt_stop(self) -> None:
        if self._qt_stop_requested:
            return
        self._qt_stop_requested = True
        if self._bridge is not None:
            self._bridge.stop_requested.emit()
            return
        if self._window is not None:
            self._window.stop()
        if self._app is not None:
            self._app.quit()

    def _drain_preinit_frames(self) -> None:
        while True:
            try:
                frame = self._preinit_frames.get_nowait()
            except queue.Empty:
                return
            self.push_frame(frame)


def _new_bridge(qt: _QtBindings) -> Any:
    class Bridge(qt.QtCore.QObject):
        state_changed = qt.QtCore.Signal(str)
        frame_received = qt.QtCore.Signal(object)
        stop_requested = qt.QtCore.Signal()

    return Bridge()


def _new_window(qt: _QtBindings, bridge: Any) -> Any:
    class DonutWindow(qt.QtWidgets.QWidget):
        def __init__(self) -> None:
            super().__init__()
            self._qt = qt
            self._state = "idle"
            self._model = _LevelModel(WAVE_POINTS)
            self._frame = 0
            self._frame_since_tick = False
            self._configure_window()
            self._timer = qt.QtCore.QTimer(self)
            self._timer.setTimerType(qt.QtCore.Qt.TimerType.PreciseTimer)
            self._timer.timeout.connect(self._tick)
            self._timer.start(33)
            bridge.state_changed.connect(self.apply_state)
            bridge.frame_received.connect(self.push_frame)
            bridge.stop_requested.connect(self.stop)
            self.hide()

        @qt.QtCore.Slot(str)
        def apply_state(self, state: str) -> None:
            self._state = state
            if state in ACTIVE_STATES:
                self._position_near_top_right()
                self.show()
                self.raise_()
            else:
                self.hide()
            self.update()

        @qt.QtCore.Slot(object)
        def push_frame(self, frame: object) -> None:
            if isinstance(frame, np.ndarray):
                self._model.accept(frame)
                self._frame_since_tick = True
                if self._state == "recording":
                    self.update()

        @qt.QtCore.Slot()
        def stop(self) -> None:
            self._timer.stop()
            self.hide()
            self.close()

        def _configure_window(self) -> None:
            flags = (
                qt.QtCore.Qt.WindowType.FramelessWindowHint
                | qt.QtCore.Qt.WindowType.WindowStaysOnTopHint
                | qt.QtCore.Qt.WindowType.Tool
            )
            no_focus = getattr(qt.QtCore.Qt.WindowType, "WindowDoesNotAcceptFocus", None)
            if no_focus is not None:
                flags |= no_focus
            self.setWindowFlags(flags)
            self.setWindowTitle("dicton")
            self.setFixedSize(SIZE, SIZE)
            self.setAttribute(qt.QtCore.Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            # Transparent window background: the dark backdrop is drawn as a
            # circle in paintEvent, so the widget reads as a circle (corners see
            # through to the desktop on a compositor) instead of a black square.
            self.setAttribute(qt.QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setFocusPolicy(qt.QtCore.Qt.FocusPolicy.NoFocus)
            self._position_near_top_right()

        def _position_near_top_right(self) -> None:
            screen = self.screen() or qt.QtWidgets.QApplication.primaryScreen()
            if screen is None:
                self.move(24, 48)
                return
            geo = screen.availableGeometry()
            self.move(max(0, geo.right() - SIZE - 24), max(0, geo.top() + 48))

        def _tick(self) -> None:
            active = self._state in ACTIVE_STATES
            if active:
                if self._state == "recording" and not self._frame_since_tick:
                    self._model.decay()
                self._model.smooth()
                self._frame += 1
                self.update()
            self._frame_since_tick = False

        def paintEvent(self, _event: object) -> None:  # noqa: N802
            painter = qt.QtGui.QPainter(self)
            painter.setRenderHint(qt.QtGui.QPainter.RenderHint.Antialiasing, True)
            # Clear to fully transparent, then lay down a circular dark backdrop.
            painter.setCompositionMode(qt.QtGui.QPainter.CompositionMode.CompositionMode_Source)
            painter.fillRect(self.rect(), qt.QtGui.QColor(0, 0, 0, 0))
            painter.setCompositionMode(qt.QtGui.QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(qt.QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(_qcolor(qt, BACKGROUND, BACKDROP_ALPHA))
            painter.drawEllipse(
                qt.QtCore.QPointF(SIZE / 2, SIZE / 2), BACKDROP_RADIUS, BACKDROP_RADIUS
            )
            if self._state == "processing":
                self._paint_processing(painter)
            elif self._state == "recording":
                self._paint_recording(painter)
            painter.end()

        def _paint_processing(self, painter: Any) -> None:
            center = qt.QtCore.QPointF(SIZE / 2, SIZE / 2)
            pulse = (math.sin(self._frame * 0.09) + 1.0) / 2.0
            radius = 35.0 + pulse * 35.0
            glow = _qcolor(qt, COLOR_DIM, int(40 + pulse * 30))
            painter.setPen(qt.QtGui.QPen(glow, 10))
            painter.drawEllipse(center, radius + 3, radius + 3)
            painter.setPen(qt.QtGui.QPen(_qcolor(qt, COLOR_MAIN), 4))
            painter.drawEllipse(center, radius, radius)

        def _paint_recording(self, painter: Any) -> None:
            center_x = SIZE / 2
            center_y = SIZE / 2
            center = qt.QtCore.QPointF(center_x, center_y)
            levels = self._model.bar_levels()
            global_level = self._model.global_level

            # Central circle the spectrum bars radiate from; brightens with level.
            ring_intensity = min(1.0, 0.45 + global_level * 0.6)
            painter.setBrush(qt.QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(
                qt.QtGui.QPen(_qcolor(qt, _lerp_color(COLOR_DIM, COLOR_MAIN, ring_intensity)), 2)
            )
            painter.drawEllipse(center, BAR_INNER_RADIUS, BAR_INNER_RADIUS)

            # Radial spectrum bars: one per frequency band, length = its level.
            pen = qt.QtGui.QPen()
            pen.setWidthF(BAR_WIDTH)
            pen.setCapStyle(qt.QtCore.Qt.PenCapStyle.RoundCap)
            r0 = BAR_INNER_RADIUS + 1.0
            for i in range(self._model.wave_points):
                level = float(levels[i])
                length = level * BAR_MAX_LENGTH
                if length < 0.6:
                    continue
                cos_value = float(self._model.cos[i])
                sin_value = float(self._model.sin[i])
                r1 = r0 + length
                pen.setColor(_qcolor(qt, _lerp_color(COLOR_MID, COLOR_GLOW, level)))
                painter.setPen(pen)
                painter.drawLine(
                    qt.QtCore.QPointF(center_x + cos_value * r0, center_y + sin_value * r0),
                    qt.QtCore.QPointF(center_x + cos_value * r1, center_y + sin_value * r1),
                )

    return DonutWindow()


def _qcolor(qt: _QtBindings, color: tuple[int, int, int], alpha: int = 255) -> Any:
    return qt.QtGui.QColor(color[0], color[1], color[2], alpha)


def _lerp_color(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def _dbfs(raw_rms: float) -> float:
    if raw_rms <= 0.0:
        return DBFS_FLOOR
    return max(-120.0, 20.0 * math.log10(raw_rms))


def _log_band_edges(fft_size: int, nbands: int) -> np.ndarray:
    """``nbands + 1`` geometrically (log-frequency) spaced FFT-bin edges.

    Bin index is proportional to frequency, so geometric spacing of bins is
    geometric spacing of frequency — independent of the sample rate. Each band
    aggregates the bins between consecutive edges (see ``accept``), giving the
    bass/mids fine resolution and compressing the sparse high end. Edges are
    contiguous so every bin belongs to exactly one band (no peak is missed).
    """
    bin_max = max(BAND_BIN_MIN + 1, int(fft_size * BAND_BIN_FRACTION))
    return BAND_BIN_MIN * (bin_max / BAND_BIN_MIN) ** np.linspace(0.0, 1.0, nbands + 1)


def _presence_gate(dbfs: float) -> float:
    """Smooth speech-presence gate — saturates to 1.0 once sound is clearly present.

    Unlike a loudness ramp, the gate does not keep growing with volume: above
    ``GATE_FULL_DBFS`` it is fully open, so the rendered amplitude stops tracking
    how loud the speaker is and only the spectral shape modulates the wave.
    """
    if dbfs <= GATE_FLOOR_DBFS:
        return 0.0
    if dbfs >= GATE_FULL_DBFS:
        return 1.0
    t = (dbfs - GATE_FLOOR_DBFS) / (GATE_FULL_DBFS - GATE_FLOOR_DBFS)
    return t * t * (3.0 - 2.0 * t)


def _soft_compress(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value <= 0.5:
        return value
    return min(1.0, 0.5 + 0.5 * (1.0 - math.exp(-(value - 0.5) * 2.0)))
