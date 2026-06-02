"""Circular donut audio visualizer backed by PySide6/QPainter."""

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

SIZE = 160
WAVE_POINTS = 90

COLOR_MAIN = (188, 82, 21)
COLOR_MID = (150, 65, 17)
COLOR_DIM = (95, 42, 11)
COLOR_GLOW = (218, 112, 44)
BACKGROUND = (20, 20, 24)

VISUAL_TARGET_RMS = 0.22
VISUAL_MIN_GAIN = 0.35
VISUAL_MAX_GAIN = 14.0
VISUAL_GAIN_ATTACK = 0.28
VISUAL_GAIN_RELEASE = 0.18
BASS_BOOST = 0.18
PEAK_HOLD_FRAMES = 30
RMS_NORMALIZATION = 32768
SPECTRUM_NORMALIZATION = 40_000_000

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
        self.adaptive_gain = 1.0
        self.peak_level = 0.0
        self.peak_hold_counter = 0
        self._angles = np.linspace(math.pi / 2, math.pi / 2 + math.tau, wave_points, endpoint=False)
        self.cos = np.cos(self._angles)
        self.sin = np.sin(self._angles)

    def accept(self, frame: np.ndarray) -> None:
        if frame.size == 0:
            self.decay()
            return
        data = frame.astype(np.float32, copy=False)
        raw_rms = float(np.sqrt(np.mean(data * data))) / RMS_NORMALIZATION
        if raw_rms > self.peak_level:
            self.peak_level = raw_rms
            self.peak_hold_counter = PEAK_HOLD_FRAMES
        elif self.peak_hold_counter > 0:
            self.peak_hold_counter -= 1
        else:
            self.peak_level *= 0.995
        target_gain = VISUAL_TARGET_RMS / max(raw_rms, 0.001)
        target_gain = max(VISUAL_MIN_GAIN, min(VISUAL_MAX_GAIN, target_gain))
        rate = VISUAL_GAIN_ATTACK if target_gain > self.adaptive_gain else VISUAL_GAIN_RELEASE
        self.adaptive_gain += (target_gain - self.adaptive_gain) * rate
        self.adaptive_gain = max(VISUAL_MIN_GAIN, min(VISUAL_MAX_GAIN, self.adaptive_gain))
        rms = _soft_compress(raw_rms * self.adaptive_gain)
        self.global_level = self.global_level * 0.7 + rms * 0.3

        fft = np.abs(np.fft.rfft(data))
        fft_size = len(fft)
        bass_end = min(max(2, fft_size // 24), fft_size)
        bass = 0.0
        if bass_end > 1:
            bass = _soft_compress(
                (float(np.max(fft[1:bass_end])) / SPECTRUM_NORMALIZATION) * self.adaptive_gain
            )
        floor = max(rms * 0.15, bass * BASS_BOOST)
        cap = min(1.0, rms * 2.2 + 0.15)
        for i in range(self.wave_points):
            idx = min(1 + int((i / self.wave_points) * (fft_size - 1) * 0.7), fft_size - 1)
            level = _soft_compress((float(fft[idx]) / SPECTRUM_NORMALIZATION) * self.adaptive_gain)
            self.levels[i] = self.levels[i] * 0.4 + min(max(level, floor), cap) * 0.6

    def decay(self) -> None:
        self.levels *= 0.9
        self.global_level *= 0.9
        self.peak_level *= 0.995

    def smooth(self) -> None:
        self.smooth_levels = self.smooth_levels * 0.82 + self.levels * 0.18


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
            painter.fillRect(self.rect(), _qcolor(qt, BACKGROUND))
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
            outer_radius = SIZE / 2 - 10
            inner_radius = 20
            mid_radius = (outer_radius + inner_radius) / 2
            max_amplitude = (outer_radius - inner_radius) / 2 - 2
            global_level = self._model.global_level
            outer = qt.QtGui.QPolygonF()
            inner = qt.QtGui.QPolygonF()
            for i in range(self._model.wave_points):
                level = float(self._model.smooth_levels[i])
                angle = float(self._model._angles[i])
                wave_phase = self._frame * 0.05
                wave1 = math.sin(wave_phase + angle * 3) * 0.15
                wave2 = math.sin(wave_phase * 0.7 + angle * 5) * 0.1
                wave3 = math.sin(wave_phase * 1.2 + angle * 2) * 0.08
                base_wave = (wave1 + wave2 + wave3) * max_amplitude * 0.3
                amplitude = level * max_amplitude * 0.9 + base_wave
                amplitude *= 0.4 + global_level * 0.9
                cos_value = float(self._model.cos[i])
                sin_value = float(self._model.sin[i])
                outer_r = mid_radius + amplitude
                inner_r = max(inner_radius, mid_radius - amplitude)
                outer.append(
                    qt.QtCore.QPointF(
                        center_x + cos_value * outer_r, center_y + sin_value * outer_r
                    )
                )
                inner.append(
                    qt.QtCore.QPointF(
                        center_x + cos_value * inner_r, center_y + sin_value * inner_r
                    )
                )

            if outer.size() <= 2 or inner.size() <= 2:
                return
            shape = qt.QtGui.QPolygonF(outer)
            for i in range(inner.size() - 1, -1, -1):
                shape.append(inner.at(i))
            painter.setPen(qt.QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(_qcolor(qt, COLOR_MID))
            painter.drawPolygon(shape)

            intensity = min(1.0, 0.5 + global_level * 0.6)
            line_color = (
                int(COLOR_DIM[0] + (COLOR_MAIN[0] - COLOR_DIM[0]) * intensity),
                int(COLOR_DIM[1] + (COLOR_MAIN[1] - COLOR_DIM[1]) * intensity),
                int(COLOR_DIM[2] + (COLOR_MAIN[2] - COLOR_DIM[2]) * intensity),
            )
            painter.setBrush(qt.QtCore.Qt.BrushStyle.NoBrush)
            painter.setPen(qt.QtGui.QPen(_qcolor(qt, line_color), 2))
            painter.drawPolygon(outer)
            painter.setPen(qt.QtGui.QPen(_qcolor(qt, COLOR_DIM), 2))
            painter.drawPolygon(inner)
            painter.setBrush(_qcolor(qt, BACKGROUND))
            painter.setPen(qt.QtCore.Qt.PenStyle.NoPen)
            painter.drawEllipse(
                qt.QtCore.QPointF(center_x, center_y), inner_radius - 8, inner_radius - 8
            )
            if global_level > 0.25:
                painter.setBrush(qt.QtCore.Qt.BrushStyle.NoBrush)
                painter.setPen(qt.QtGui.QPen(_qcolor(qt, COLOR_GLOW, int(global_level * 120)), 1))
                painter.drawPolygon(outer)

    return DonutWindow()


def _qcolor(qt: _QtBindings, color: tuple[int, int, int], alpha: int = 255) -> Any:
    return qt.QtGui.QColor(color[0], color[1], color[2], alpha)


def _soft_compress(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value <= 0.5:
        return value
    return min(1.0, 0.5 + 0.5 * (1.0 - math.exp(-(value - 0.5) * 2.0)))
