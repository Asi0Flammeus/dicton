"""Circular donut audio visualizer — pygame on the main thread.

Drawing code ported verbatim from the main branch
(`adapters/ui/visualizer.py`) so the look/feel stays identical: FFT-driven
wave points around a Flexoki-orange donut, soft-compressed adaptive gain,
glow polygon, pulsing concentric ring during processing.

The window is initially hidden and only shown when the pipeline state is
``recording`` or ``processing``; it is hidden again on ``idle``.
"""

from __future__ import annotations

import contextlib
import math
import os
import queue
import sys
import threading

import numpy as np

SIZE = 160
WAVE_POINTS = 90

TRANSPARENT_COLORKEY = (255, 0, 255)

# Flexoki "orange" palette — exact RGB values from main's theme_constants.py.
COLOR_MAIN = (188, 82, 21)
COLOR_MID = (150, 65, 17)
COLOR_DIM = (95, 42, 11)
COLOR_GLOW = (218, 112, 44)

DEFAULT_GAIN = 0.7
MIN_GAIN = 0.3
MAX_GAIN = 1.5
GAIN_ATTACK = 0.02
GAIN_RELEASE = 0.005
PEAK_HOLD_FRAMES = 30
RMS_NORMALIZATION = 32768

IS_LINUX = sys.platform.startswith("linux")
IS_WINDOWS = sys.platform.startswith("win")
IS_X11 = IS_LINUX and bool(os.environ.get("DISPLAY"))


class Visualizer:
    """Same draw code as main; hide/show driven by state."""

    def __init__(self) -> None:
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=128)
        self._state = "idle"  # idle | recording | processing
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.levels = np.zeros(WAVE_POINTS, dtype=np.float32)
        self.smooth_levels = np.zeros(WAVE_POINTS, dtype=np.float32)
        self.global_level = 0.0
        self.adaptive_gain = DEFAULT_GAIN
        self.peak_level = 0.0
        self.peak_hold_counter = 0
        self.frame = 0
        self._xshape_ok = False

    # ---- producer side (any thread) ----

    def push_frame(self, frame: np.ndarray) -> None:
        with contextlib.suppress(queue.Full):
            self._frames.put_nowait(frame)

    def set_state(self, state: str) -> None:
        self._state = state

    def stop(self) -> None:
        self._stop.set()

    # ---- main-thread loop ----

    def run(self) -> None:
        if IS_LINUX and IS_X11:
            os.environ.setdefault("SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR", "0")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        os.environ.setdefault("SDL_VIDEO_X11_WMCLASS", "dicton")
        import pygame

        pygame.init()
        pygame.display.set_caption("dicton")

        info = pygame.display.Info()
        pos_x = max(0, info.current_w - SIZE - 24)
        pos_y = 48
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{pos_x},{pos_y}"

        # Always-mapped window: we never call show()/hide() because each
        # remap on i3 grabs input focus, sending xdotool's Ctrl+Shift+V to
        # the donut instead of the user's app. Visibility is driven via the
        # XShape mask, which doesn't trigger focus events.
        screen = pygame.display.set_mode((SIZE, SIZE), pygame.NOFRAME)
        if IS_LINUX and IS_X11:
            self._set_x11_floating_hint(pygame)
            self._init_x11_shape(pygame)
            self._apply_shape(visible=False)  # start fully clipped (invisible)
            self._set_sdl_opacity(pygame, 0.85)  # semi-transparent voile over the dark bg
        elif IS_WINDOWS:
            self._set_windows_colorkey_transparency(pygame, screen)

        shape_visible = False
        was_showing = False
        clock = pygame.time.Clock()
        while not self._stop.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop.set()
            should_show = self._state in ("recording", "processing")
            if IS_LINUX and IS_X11 and should_show != shape_visible:
                self._apply_shape(visible=should_show)
                shape_visible = should_show
            if should_show:
                self._drain_frames()
                self._draw(pygame, screen)
                self.frame += 1
            elif was_showing and not (IS_LINUX and IS_X11):
                # On Windows / macOS / non-X11 Linux there is no XShape mask
                # to clip the stale frame away when we go back to idle. Paint
                # one frame of pure colorkey/background so the donut actually
                # disappears.
                if IS_WINDOWS:
                    screen.fill(TRANSPARENT_COLORKEY)
                else:
                    screen.fill((15, 15, 18))
                pygame.display.flip()
            was_showing = should_show
            clock.tick(60 if should_show else 20)
        pygame.quit()

    @staticmethod
    def _sdl_window(pygame):
        try:
            from pygame._sdl2.video import Window

            return Window.from_display_module()
        except (ImportError, AttributeError):
            return None

    @staticmethod
    def _set_sdl_opacity(pygame, opacity: float) -> None:
        """Per-window opacity via SDL (requires a running compositor; picom on i3)."""
        try:
            from pygame._sdl2.video import Window

            Window.from_display_module().opacity = max(0.0, min(1.0, opacity))
        except (ImportError, AttributeError, Exception):
            pass

    # ---- audio → levels (ported from main `update()`) ----

    def _drain_frames(self) -> None:
        latest: np.ndarray | None = None
        while True:
            try:
                latest = self._frames.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            with self._lock:
                self.levels *= 0.9
                self.global_level *= 0.9
            return
        data = latest.astype(np.float32)
        raw_rms = float(np.sqrt(np.mean(data * data))) / RMS_NORMALIZATION
        with self._lock:
            if raw_rms > self.peak_level:
                self.peak_level = raw_rms
                self.peak_hold_counter = PEAK_HOLD_FRAMES
            elif self.peak_hold_counter > 0:
                self.peak_hold_counter -= 1
            else:
                self.peak_level *= 0.995
            if self.peak_level > 0.7:
                target = max(MIN_GAIN, min(MAX_GAIN, 0.7 / max(self.peak_level, 0.01)))
                self.adaptive_gain += (target - self.adaptive_gain) * GAIN_ATTACK
            else:
                self.adaptive_gain += (DEFAULT_GAIN - self.adaptive_gain) * GAIN_RELEASE
            self.adaptive_gain = max(MIN_GAIN, min(MAX_GAIN, self.adaptive_gain))
            rms = _soft_compress(raw_rms * self.adaptive_gain)
            self.global_level = self.global_level * 0.7 + rms * 0.3

            fft = np.abs(np.fft.rfft(data))
            fft_size = len(fft)
            for i in range(WAVE_POINTS):
                idx = min(1 + int((i / WAVE_POINTS) * (fft_size - 1) * 0.7), fft_size - 1)
                level = _soft_compress((fft[idx] / 35000) * self.adaptive_gain)
                self.levels[i] = self.levels[i] * 0.4 + level * 0.6

    # ---- drawing (ported verbatim from main `_draw()`) ----

    def _draw(self, pygame, screen) -> None:
        if IS_WINDOWS:
            bg = TRANSPARENT_COLORKEY
        elif self._xshape_ok:
            bg = (15, 15, 18)
        else:
            bg = (20, 20, 24)
        screen.fill(bg)

        center_x, center_y = SIZE // 2, SIZE // 2
        outer_radius = SIZE // 2 - 10
        inner_radius = 20
        mid_radius = (outer_radius + inner_radius) // 2
        max_amplitude = (outer_radius - inner_radius) // 2 - 2

        with self._lock:
            is_processing = self._state == "processing"
            levels_copy = self.levels.copy()
            global_level = self.global_level

        if is_processing:
            pulse_phase = self.frame * 0.03
            pulse = (math.sin(pulse_phase) + 1) / 2
            min_ring_radius = inner_radius + 15
            max_ring_radius = outer_radius - 5
            ring_radius = min_ring_radius + pulse * (max_ring_radius - min_ring_radius)
            ring_width = 4
            pygame.draw.circle(
                screen, COLOR_MAIN, (center_x, center_y), int(ring_radius), ring_width
            )
            glow_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            glow_alpha = int(40 + pulse * 30)
            pygame.draw.circle(
                glow_surf,
                (*COLOR_DIM, glow_alpha),
                (center_x, center_y),
                int(ring_radius) + 3,
                ring_width + 4,
            )
            screen.blit(glow_surf, (0, 0))
            pygame.display.flip()
            return

        for i in range(WAVE_POINTS):
            self.smooth_levels[i] = self.smooth_levels[i] * 0.82 + levels_copy[i] * 0.18

        outer_points: list[tuple[float, float]] = []
        inner_points: list[tuple[float, float]] = []
        angle_offset = math.pi / 2

        for i in range(WAVE_POINTS):
            angle = (i / WAVE_POINTS) * 2 * math.pi + angle_offset
            level = float(self.smooth_levels[i])
            wave_phase = self.frame * 0.05
            wave1 = math.sin(wave_phase + angle * 3) * 0.15
            wave2 = math.sin(wave_phase * 0.7 + angle * 5) * 0.1
            wave3 = math.sin(wave_phase * 1.2 + angle * 2) * 0.08
            base_wave = (wave1 + wave2 + wave3) * max_amplitude * 0.3
            amplitude = level * max_amplitude * 0.9 + base_wave
            amplitude *= 0.4 + global_level * 0.9

            outer_r = mid_radius + amplitude
            outer_points.append(
                (center_x + math.cos(angle) * outer_r, center_y + math.sin(angle) * outer_r)
            )
            inner_r = max(inner_radius, mid_radius - amplitude)
            inner_points.append(
                (center_x + math.cos(angle) * inner_r, center_y + math.sin(angle) * inner_r)
            )

        if global_level > 0.1:
            glow_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            glow_alpha = int(40 + global_level * 50)
            glow_outer: list[tuple[float, float]] = []
            for i in range(WAVE_POINTS):
                angle = (i / WAVE_POINTS) * 2 * math.pi + angle_offset
                level = float(self.smooth_levels[i])
                wave = math.sin(self.frame * 0.05 + angle * 3) * 0.15
                amp = (level * max_amplitude * 0.9 + wave * max_amplitude * 0.3) * 1.1
                amp *= 0.4 + global_level * 0.9
                r = mid_radius + amp
                glow_outer.append((center_x + math.cos(angle) * r, center_y + math.sin(angle) * r))
            pygame.draw.polygon(glow_surf, (*COLOR_DIM, glow_alpha), glow_outer, width=4)
            screen.blit(glow_surf, (0, 0))

        if len(outer_points) > 2 and len(inner_points) > 2:
            donut_shape = outer_points + inner_points[::-1]
            pygame.draw.polygon(screen, COLOR_MID, donut_shape)

        if len(outer_points) > 2:
            intensity = min(1.0, 0.5 + global_level * 0.6)
            line_color = (
                int(COLOR_DIM[0] + (COLOR_MAIN[0] - COLOR_DIM[0]) * intensity),
                int(COLOR_DIM[1] + (COLOR_MAIN[1] - COLOR_DIM[1]) * intensity),
                int(COLOR_DIM[2] + (COLOR_MAIN[2] - COLOR_DIM[2]) * intensity),
            )
            pygame.draw.polygon(screen, line_color, outer_points, width=2)

        if len(inner_points) > 2:
            pygame.draw.polygon(screen, COLOR_DIM, inner_points, width=2)

        pygame.draw.circle(screen, bg, (center_x, center_y), inner_radius - 8)

        if global_level > 0.25:
            highlight_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            pygame.draw.polygon(
                highlight_surf, (*COLOR_GLOW, int(global_level * 120)), outer_points, width=1
            )
            screen.blit(highlight_surf, (0, 0))

        pygame.display.flip()

    # ---- X11 / Windows window setup ----

    def _set_x11_floating_hint(self, pygame) -> None:
        """Mark as UTILITY (auto-float on i3), tell the WM we don't want
        keyboard focus, and pin the window across every workspace (sticky).
        Without sticky, i3 leaves the visualizer on workspace 1 so the user
        loses sight of it when they switch workspace."""
        try:
            from Xlib import X, Xutil, display, protocol

            wm_info = pygame.display.get_wm_info()
            win_id = wm_info.get("window")
            if not win_id:
                return
            d = display.Display()
            win = d.create_resource_object("window", win_id)

            wm_type = d.intern_atom("_NET_WM_WINDOW_TYPE")
            utility = d.intern_atom("_NET_WM_WINDOW_TYPE_UTILITY")
            win.change_property(wm_type, d.intern_atom("ATOM"), 32, [utility])

            # WM_HINTS with input=False: ICCCM signal that this window does
            # not want keyboard input. Most WMs (i3 included) skip it in the
            # focus rotation as a result.
            win.set_wm_hints(flags=Xutil.InputHint, input=False)

            # _NET_WM_STATE_STICKY: float on every workspace, not just the
            # one where the daemon was started. We set the property *and*
            # send the EWMH ClientMessage to root — the property covers the
            # case where the window is still being mapped, the message
            # covers the case where it's already mapped.
            wm_state = d.intern_atom("_NET_WM_STATE")
            sticky = d.intern_atom("_NET_WM_STATE_STICKY")
            win.change_property(wm_state, d.intern_atom("ATOM"), 32, [sticky])
            ev = protocol.event.ClientMessage(
                window=win,
                client_type=wm_state,
                data=(32, [1, sticky, 0, 1, 0]),  # _NET_WM_STATE_ADD=1, source=app
            )
            d.screen().root.send_event(
                ev,
                event_mask=X.SubstructureNotifyMask | X.SubstructureRedirectMask,
            )
            d.sync()
        except Exception:
            pass

    def _init_x11_shape(self, pygame) -> None:
        """Open a long-lived X11 connection so we can toggle the shape mask
        between 'circle' and 'empty' at state-change time without remapping
        the window (which would steal input focus)."""
        try:
            from Xlib import display
            from Xlib.ext import shape  # noqa: F401  (extension load side effect)

            wm_info = pygame.display.get_wm_info()
            win_id = wm_info.get("window")
            if not win_id:
                return
            self._xd = display.Display()
            self._xwin = self._xd.create_resource_object("window", win_id)
            self._xshape_ok = True
        except Exception:
            self._xshape_ok = False

    def _apply_shape(self, *, visible: bool) -> None:
        """Visible (state transition only): permissive circle so the donut can
        always render. Invisible: clip away every pixel. Per-frame refinement
        to the actual donut polygon happens in ``_set_donut_shape``."""
        if not self._xshape_ok or not hasattr(self, "_xwin"):
            return
        try:
            from Xlib.ext import shape

            if visible:
                pixmap = self._xwin.create_pixmap(SIZE, SIZE, 1)
                gc = pixmap.create_gc(foreground=0, background=0)
                pixmap.fill_rectangle(gc, 0, 0, SIZE, SIZE)
                gc.change(foreground=1)
                pixmap.fill_arc(gc, 0, 0, SIZE, SIZE, 0, 360 * 64)
            else:
                pixmap = self._xwin.create_pixmap(1, 1, 1)
                gc = pixmap.create_gc(foreground=0, background=0)
                pixmap.fill_rectangle(gc, 0, 0, 1, 1)
            self._xwin.shape_mask(shape.SO.Set, shape.SK.Bounding, 0, 0, pixmap)
            self._xwin.shape_mask(shape.SO.Set, shape.SK.Input, 0, 0, pixmap)
            self._xd.sync()
            pixmap.free()
        except Exception:
            pass

    def _set_donut_shape(
        self,
        outer_pts: list[tuple[float, float]],
        inner_pts: list[tuple[float, float]],
    ) -> None:
        """Per-frame XShape: clip everything except the donut polygon, so the
        dark background pixels never reach the screen. The polygons are
        dilated radially by a margin so the mask also captures pygame's
        outlines, glow halo, and highlight pass that draw slightly outside
        the bare polygon."""
        if not self._xshape_ok or not hasattr(self, "_xwin"):
            return
        if len(outer_pts) < 3 or len(inner_pts) < 3:
            return
        try:
            from Xlib import X
            from Xlib.ext import shape

            # Margin 0 on both sides: mask = exact donut polygon. Any positive
            # outer margin leaves a visible bg halo around the ring; the
            # outer stroke is half-clipped (≈1 px) but the user doesn't see
            # any dark pixels.
            outer_xy = _dilate_radially(outer_pts, SIZE / 2, SIZE / 2, 0)
            inner_xy = _dilate_radially(inner_pts, SIZE / 2, SIZE / 2, 0)

            pixmap = self._xwin.create_pixmap(SIZE, SIZE, 1)
            gc = pixmap.create_gc(foreground=0, background=0)
            pixmap.fill_rectangle(gc, 0, 0, SIZE, SIZE)
            gc.change(foreground=1)
            pixmap.fill_poly(gc, X.Complex, X.CoordModeOrigin, outer_xy)
            gc.change(foreground=0)
            pixmap.fill_poly(gc, X.Complex, X.CoordModeOrigin, inner_xy)
            self._xwin.shape_mask(shape.SO.Set, shape.SK.Bounding, 0, 0, pixmap)
            self._xd.flush()
            pixmap.free()
        except Exception:
            pass

    def _set_windows_colorkey_transparency(self, pygame, screen) -> None:
        try:
            screen.set_colorkey(TRANSPARENT_COLORKEY)
            import ctypes

            hwnd = pygame.display.get_wm_info().get("window")
            if not hwnd:
                return
            user32 = ctypes.windll.user32

            # Hide, flip the extended style, then show without activating.
            # The style change only takes effect on a window-state cycle, and
            # if we Show normally the donut steals focus from the user's app.
            GWL_EXSTYLE = -20  # noqa: N806
            WS_EX_LAYERED = 0x00080000  # noqa: N806
            WS_EX_TOOLWINDOW = 0x00000080  # noqa: N806  (no taskbar / Alt+Tab)
            WS_EX_NOACTIVATE = 0x08000000  # noqa: N806
            SW_HIDE = 0  # noqa: N806
            SW_SHOWNOACTIVATE = 4  # noqa: N806

            user32.ShowWindow(hwnd, SW_HIDE)
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            )
            user32.SetLayeredWindowAttributes(hwnd, 0xFF | (0x00 << 8) | (0xFF << 16), 0, 0x1)
            user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
        except Exception:
            pass


def _soft_compress(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value < 0.5:
        return value
    return min(1.0, 0.5 + 0.5 * (1.0 - math.exp(-(value - 0.5) * 2.0)))


def _dilate_radially(
    pts: list[tuple[float, float]],
    cx: float,
    cy: float,
    margin: float,
) -> list[tuple[int, int]]:
    """Push each polygon point ``margin`` pixels away from (cx, cy) along its
    radial direction. Positive margin grows the polygon outward; negative
    shrinks it inward (used to grow the donut hole)."""
    out: list[tuple[int, int]] = []
    for x, y in pts:
        dx = x - cx
        dy = y - cy
        r = math.hypot(dx, dy) or 1.0
        scale = (r + margin) / r
        out.append((int(cx + dx * scale), int(cy + dy * scale)))
    return out
