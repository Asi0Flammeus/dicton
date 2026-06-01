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
import logging
import math
import os
import queue
import shutil
import subprocess
import sys
import threading

import numpy as np

log = logging.getLogger("dicton")

# After this many consecutive frame errors, stop animating rather than
# busy-spin on a wedged display (e.g. an X server that dropped the window).
# The daemon keeps recording/pasting — it just loses the visual feedback.
MAX_CONSECUTIVE_ERRORS = 30

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
        # True only when the loop exited because shutdown was requested (SDL
        # QUIT / SIGTERM), as opposed to a crash. The daemon uses this to know
        # whether to exit or keep serving dictations without animation.
        self.quit_requested = False
        self._lock = threading.Lock()
        self.levels = np.zeros(WAVE_POINTS, dtype=np.float32)
        self.smooth_levels = np.zeros(WAVE_POINTS, dtype=np.float32)
        self.global_level = 0.0
        self.adaptive_gain = DEFAULT_GAIN
        self.peak_level = 0.0
        self.peak_hold_counter = 0
        self.frame = 0
        self._xshape_ok = False
        self._pygame = None
        self._screen = None

    # ---- producer side (any thread) ----

    def push_frame(self, frame: np.ndarray) -> None:
        with contextlib.suppress(queue.Full):
            self._frames.put_nowait(frame)

    def set_state(self, state: str) -> None:
        if state != self._state:
            log.info("visualizer state: %s -> %s", self._state, state)
        self._state = state

    def stop(self) -> None:
        self._stop.set()

    # ---- main-thread loop ----

    def initialize(self) -> None:
        """Create and hide the SDL window before any other X client starts."""
        if self._pygame is not None and self._screen is not None:
            return
        if IS_LINUX and IS_X11:
            os.environ.setdefault("SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR", "0")
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        os.environ.setdefault("SDL_VIDEO_X11_WMCLASS", "dicton")
        log.info(
            "visualizer starting: platform linux=%s x11=%s windows=%s",
            IS_LINUX,
            IS_X11,
            IS_WINDOWS,
        )
        import pygame

        pygame.init()
        log.info("visualizer pygame initialized")
        pygame.display.set_caption("dicton")

        info = pygame.display.Info()
        pos_x = max(0, info.current_w - SIZE - 24)
        pos_y = 48
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{pos_x},{pos_y}"
        log.info(
            "visualizer display: screen=%sx%s pos=%s,%s",
            info.current_w,
            info.current_h,
            pos_x,
            pos_y,
        )
        # X11 shape setup remains one-shot. Runtime visibility uses SDL
        # hide/show, not python-xlib, so crash breadcrumbs can distinguish SDL
        # remap crashes from XShape setup crashes.
        screen = pygame.display.set_mode((SIZE, SIZE), pygame.NOFRAME)
        log.info("visualizer set_mode complete: wm_info=%s", pygame.display.get_wm_info())
        if IS_LINUX and IS_X11:
            self._init_x11_window(pygame)
            log.info("visualizer X11 setup complete: xshape_ok=%s", self._xshape_ok)
            self._set_visible(pygame, screen, False)  # start hidden; raised on first frame
        elif IS_WINDOWS:
            self._set_windows_colorkey_transparency(pygame, screen)
            log.info("visualizer Windows colorkey setup complete")
        self._pygame = pygame
        self._screen = screen

    def run(self) -> None:
        if self._pygame is None or self._screen is None:
            self.initialize()
        pygame = self._pygame
        screen = self._screen

        # Crash isolation: a single bad frame (transient X error, lost
        # surface, …) must not kill the loop — that previously froze the
        # window and, because run() is on the main thread, could take the
        # whole daemon down. We log the first failure with a traceback so the
        # real cause is recoverable from dicton.log, count consecutive
        # failures, and give up animating only if the display is truly wedged.
        try:
            self._loop(pygame, screen)
            log.info("visualizer loop exited")
        except Exception:
            log.exception("visualizer loop crashed — daemon continues without animation")
        finally:
            log.info("visualizer pygame quit begin")
            with contextlib.suppress(Exception):
                pygame.quit()
            log.info("visualizer pygame quit end")

    def _loop(self, pygame, screen) -> None:
        visible = False
        consecutive_errors = 0
        clock = pygame.time.Clock()
        while not self._stop.is_set():
            try:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.quit_requested = True
                        self._stop.set()
                should_show = self._state in ("recording", "processing")
                if should_show != visible:
                    log.info(
                        "visualizer visibility transition: visible=%s state=%s frame=%s",
                        should_show,
                        self._state,
                        self.frame,
                    )
                    self._set_visible(pygame, screen, should_show)
                    visible = should_show
                if should_show:
                    self._drain_frames()
                    self._draw(pygame, screen)
                    self.frame += 1
                consecutive_errors = 0
            except Exception:
                consecutive_errors += 1
                if consecutive_errors == 1:
                    log.warning("visualizer frame failed", exc_info=True)
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    log.error(
                        "visualizer giving up after %d consecutive frame errors "
                        "— daemon continues without animation",
                        consecutive_errors,
                    )
                    return
            clock.tick(60 if self._state in ("recording", "processing") else 20)

    def _set_visible(self, pygame, screen, visible: bool) -> None:
        """Show/hide without runtime XShape mutations.

        Hidden means unmapped, not just opacity=0: opacity depends on picom,
        so a compositor restart exposes an idle black circle. SDL hide/show
        uses SDL's own X11 connection, preserving the single-owner invariant
        that avoids python-xlib/SDL crashes. Showing a window can steal focus
        on i3, so restore the previous active X11 window immediately after
        remapping.
        """
        log.info("visualizer set_visible begin: visible=%s", visible)
        window = None
        if not IS_WINDOWS:
            window = self._sdl_window(pygame)
            log.info("visualizer sdl window resolved: present=%s", window is not None)
            if visible:
                previous_focus = self._active_x11_window(pygame)
                log.info("visualizer previous focus: %s", previous_focus)
                self._set_sdl_opacity(pygame, 0.85)
                if window is not None:
                    with contextlib.suppress(Exception):
                        window.show()
                        log.info("visualizer SDL show complete")
                self._restore_x11_focus(previous_focus)
                log.info("visualizer focus restore attempted")
            else:
                self._set_sdl_opacity(pygame, 0.0)
                log.info("visualizer SDL opacity set to hidden")
        if not visible:
            screen.fill(TRANSPARENT_COLORKEY if IS_WINDOWS else (15, 15, 18))
            with contextlib.suppress(Exception):
                pygame.display.flip()
                log.info("visualizer display flip before hide complete")
            if not IS_WINDOWS and window is not None:
                with contextlib.suppress(Exception):
                    window.hide()
                    log.info("visualizer SDL hide complete")
        log.info("visualizer set_visible end: visible=%s", visible)

    @staticmethod
    def _sdl_window(pygame):
        try:
            try:
                Window = pygame._sdl2.video.Window
            except AttributeError:
                from pygame._sdl2.video import Window

            window = Window.from_display_module()
            log.info("visualizer Window.from_display_module ok")
            return window
        except (ImportError, AttributeError, Exception):
            log.info("visualizer Window.from_display_module unavailable", exc_info=True)
            return None

    @staticmethod
    def _active_x11_window(pygame) -> str | None:
        if not (IS_LINUX and IS_X11 and shutil.which("xdotool")):
            log.info("visualizer active x11 window probe skipped")
            return None
        try:
            current_id = str(pygame.display.get_wm_info().get("window", ""))
            active = subprocess.run(
                ["xdotool", "getactivewindow"],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.5,
            ).stdout.strip()
            log.info("visualizer active x11 window probe: current=%s active=%s", current_id, active)
            return active if active and active != current_id else None
        except Exception:
            log.info("visualizer active x11 window probe failed", exc_info=True)
            return None

    @staticmethod
    def _restore_x11_focus(window_id: str | None) -> None:
        if not (window_id and shutil.which("xdotool")):
            log.info("visualizer focus restore skipped")
            return
        with contextlib.suppress(Exception):
            subprocess.run(
                ["xdotool", "windowactivate", "--sync", window_id],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1.0,
            )
            log.info("visualizer focus restored: %s", window_id)

    @staticmethod
    def _set_sdl_opacity(pygame, opacity: float) -> None:
        """Per-window opacity via SDL (cosmetic; requires a compositor)."""
        try:
            window = Visualizer._sdl_window(pygame)
            if window is not None:
                clamped = max(0.0, min(1.0, opacity))
                window.opacity = clamped
                log.info("visualizer SDL opacity set: %.2f", clamped)
        except Exception:
            log.info("visualizer SDL opacity set failed", exc_info=True)

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

    def _init_x11_window(self, pygame) -> None:
        """One-shot X11 setup on a SHORT-LIVED python-xlib connection.

        Does, in order, on a single Display() that we close immediately:
        - mark as UTILITY (auto-float on i3, also signals 'no taskbar');
        - WM_HINTS input=False so the WM skips us in focus rotation;
        - _NET_WM_STATE_STICKY (every workspace) + _NET_WM_STATE_ABOVE (keep
          over the focused app on stacking WMs);
        - XShape Bounding to a circle, so the square corners never render;
        - XShape Input to empty, so all clicks pass through (true overlay,
          never grabs the pointer).

        We then close this connection. From this point on, SDL is the ONLY
        process talking X about this window — that single-connection
        invariant is what removes the segfault we used to hit when a long-
        lived python-xlib connection raced SDL during the render loop.
        """
        try:
            from Xlib import X, Xutil, display, protocol
            from Xlib.ext import shape

            wm_info = pygame.display.get_wm_info()
            win_id = wm_info.get("window")
            if not win_id:
                return
            d = display.Display()
            try:
                win = d.create_resource_object("window", win_id)

                wm_type = d.intern_atom("_NET_WM_WINDOW_TYPE")
                utility = d.intern_atom("_NET_WM_WINDOW_TYPE_UTILITY")
                win.change_property(wm_type, d.intern_atom("ATOM"), 32, [utility])
                win.set_wm_hints(flags=Xutil.InputHint, input=False)

                # Property covers the still-mapping case; ClientMessage covers
                # the already-mapped case. EWMH allows two states per message.
                wm_state = d.intern_atom("_NET_WM_STATE")
                sticky = d.intern_atom("_NET_WM_STATE_STICKY")
                above = d.intern_atom("_NET_WM_STATE_ABOVE")
                win.change_property(wm_state, d.intern_atom("ATOM"), 32, [sticky, above])
                ev = protocol.event.ClientMessage(
                    window=win,
                    client_type=wm_state,
                    data=(32, [1, sticky, above, 1, 0]),  # ADD=1, src=app(1)
                )
                d.screen().root.send_event(
                    ev, event_mask=X.SubstructureNotifyMask | X.SubstructureRedirectMask
                )

                # Bounding mask = filled circle. Input mask = empty, so the
                # whole window is click-through; the donut never eats clicks
                # even on its visible pixels.
                circle = win.create_pixmap(SIZE, SIZE, 1)
                gc = circle.create_gc(foreground=0, background=0)
                circle.fill_rectangle(gc, 0, 0, SIZE, SIZE)
                gc.change(foreground=1)
                circle.fill_arc(gc, 0, 0, SIZE, SIZE, 0, 360 * 64)
                win.shape_mask(shape.SO.Set, shape.SK.Bounding, 0, 0, circle)
                circle.free()

                empty = win.create_pixmap(1, 1, 1)
                gc = empty.create_gc(foreground=0, background=0)
                empty.fill_rectangle(gc, 0, 0, 1, 1)
                win.shape_mask(shape.SO.Set, shape.SK.Input, 0, 0, empty)
                empty.free()

                d.sync()
                self._xshape_ok = True
            finally:
                d.close()
        except Exception:
            log.info("X11 window setup failed", exc_info=True)
            self._xshape_ok = False

    def _set_windows_colorkey_transparency(self, pygame, screen) -> None:
        try:
            screen.set_colorkey(TRANSPARENT_COLORKEY)
            import ctypes

            hwnd = pygame.display.get_wm_info().get("window")
            if not hwnd:
                return
            user32 = ctypes.windll.user32

            # Three Win32 bits we need, applied without a ShowWindow hide/show
            # cycle — that cycle invalidates SDL's swap chain and the donut
            # never renders again. SWP_FRAMECHANGED forces Windows to re-read
            # the EXSTYLE bits (taskbar / topmost) without touching visibility.
            GWL_EXSTYLE = -20  # noqa: N806
            WS_EX_LAYERED = 0x00080000  # noqa: N806
            WS_EX_TOOLWINDOW = 0x00000080  # noqa: N806  (no taskbar / Alt+Tab)
            WS_EX_TOPMOST = 0x00000008  # noqa: N806  (z-order above user apps)
            HWND_TOPMOST = -1  # noqa: N806
            SWP_NOMOVE = 0x0002  # noqa: N806
            SWP_NOSIZE = 0x0001  # noqa: N806
            SWP_NOACTIVATE = 0x0010  # noqa: N806
            SWP_FRAMECHANGED = 0x0020  # noqa: N806

            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd,
                GWL_EXSTYLE,
                style | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST,
            )
            user32.SetLayeredWindowAttributes(hwnd, 0xFF | (0x00 << 8) | (0xFF << 16), 0, 0x1)
            user32.SetWindowPos(
                hwnd,
                HWND_TOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        except Exception:
            pass


def _soft_compress(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value < 0.5:
        return value
    return min(1.0, 0.5 + 0.5 * (1.0 - math.exp(-(value - 0.5) * 2.0)))
