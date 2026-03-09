"""GTK3/Cairo-based audio visualizer with true per-pixel transparency on Linux.

This visualizer uses GTK3 and Cairo for rendering, which provides native
ARGB visual support on X11 composited desktops. The ring is drawn with
full alpha transparency - the background is completely see-through.

Requirements:
- PyGObject (gi): pip install PyGObject
- GTK3 libraries: sudo apt install libgtk-3-dev libcairo2-dev libgirepository1.0-dev
- Compositor running (GNOME, KDE, picom, etc.)
"""

# ruff: noqa: I001
# Import order is intentional: gi.require_version must be called before gi.repository imports

import math
import threading

import numpy as np

from .config import config

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

import cairo
from gi.repository import Gdk, GLib, Gtk

# Visualizer settings
SIZE = 160
WAVE_POINTS = 90

# Adaptive gain settings (same as pygame visualizer)
DEFAULT_GAIN = 0.7
MIN_GAIN = 0.3
MAX_GAIN = 1.5
GAIN_ATTACK = 0.02
GAIN_RELEASE = 0.005
PEAK_HOLD_FRAMES = 30


class TransparentVisualizerWindow(Gtk.Window):
    """GTK window with true per-pixel transparency for the ring visualizer."""

    def __init__(self):
        super().__init__(title="Dicton")

        # Window setup
        self.set_size_request(SIZE, SIZE)
        self.set_resizable(False)  # Fixed size — also triggers i3 auto-float (min==max)
        self.set_decorated(False)  # No window decorations
        self.set_keep_above(True)  # Always on top
        self.set_skip_taskbar_hint(True)  # Don't show in taskbar
        self.set_skip_pager_hint(True)  # Don't show in pager
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)  # Float in tiling WMs
        # Enable ARGB visual for true transparency
        screen = self.get_screen()
        visual = screen.get_rgba_visual()

        if visual and screen.is_composited():
            self.set_visual(visual)
            self.supports_alpha = True
        else:
            self.supports_alpha = False
            print("⚠ Compositor not running - transparency unavailable")

        self.set_app_paintable(True)

        # Connect signals
        self.connect("draw", self.on_draw)
        self.connect("destroy", self.on_destroy)

        # Drawing area for the ring
        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.connect("draw", self.on_draw)
        self.add(self.drawing_area)

        # Audio data
        self.levels = np.zeros(WAVE_POINTS)
        self.smooth_levels = np.zeros(WAVE_POINTS)
        self.global_level = 0.0
        self.frame = 0
        self.lock = threading.Lock()

        # Processing mode (pulsing loader animation)
        self.processing = False

        # Adaptive gain
        self.adaptive_gain = DEFAULT_GAIN
        self.peak_level = 0.0
        self.peak_hold_counter = 0

        # Theme colors (normalized to 0-1)
        colors = config.get_theme_colors()
        self.color_main = tuple(c / 255.0 for c in colors["main"])
        self.color_mid = tuple(c / 255.0 for c in colors["mid"])
        self.color_dim = tuple(c / 255.0 for c in colors["dim"])
        self.color_glow = tuple(c / 255.0 for c in colors["glow"])

        # Animation timer (60 FPS)
        self.timer_id = None
        self.running = False

    def start_animation(self):
        """Start the animation timer."""
        if self.timer_id is None:
            self.running = True
            # 60 FPS = ~16.67ms interval
            self.timer_id = GLib.timeout_add(16, self.on_tick)

    def stop_animation(self):
        """Stop the animation timer."""
        self.running = False
        if self.timer_id is not None:
            GLib.source_remove(self.timer_id)
            self.timer_id = None

    def on_tick(self):
        """Animation tick - update and redraw."""
        if not self.running:
            return False

        self.frame += 1

        with self.lock:
            # Smooth the levels
            self.smooth_levels = self.smooth_levels * 0.82 + self.levels * 0.18

        # Request redraw
        self.drawing_area.queue_draw()
        return True  # Continue timer

    def on_draw(self, widget, cr):
        """Draw the ring visualizer with Cairo."""
        # Clear to fully transparent
        if self.supports_alpha:
            cr.set_source_rgba(0, 0, 0, 0)
        else:
            cr.set_source_rgb(0.078, 0.078, 0.094)  # Fallback dark bg

        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # Get dimensions
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        center_x = width / 2
        center_y = height / 2

        # Ring parameters
        outer_radius = min(width, height) / 2 - 10
        inner_radius = 25
        mid_radius = (outer_radius + inner_radius) / 2
        max_amplitude = (outer_radius - inner_radius) / 2 - 2

        with self.lock:
            global_level = self.global_level
            levels = self.smooth_levels.copy()
            is_processing = self.processing

        # Rotation offset: start from top
        angle_offset = math.pi / 2

        if is_processing:
            # Simple pulsing: ring shrinks to center and expands back
            pulse_phase = self.frame * 0.03  # Slow, calm pulse
            pulse = (math.sin(pulse_phase) + 1) / 2  # 0 to 1

            # Ring radius pulses between inner and outer
            min_ring_radius = inner_radius + 15
            max_ring_radius = outer_radius - 5
            ring_radius = min_ring_radius + pulse * (max_ring_radius - min_ring_radius)
            ring_width = 4

            # Draw simple pulsing ring with glow
            glow_alpha = 0.15 + pulse * 0.1
            cr.set_source_rgba(*self.color_dim, glow_alpha)
            cr.set_line_width(ring_width + 4)
            cr.arc(center_x, center_y, ring_radius + 2, 0, 2 * math.pi)
            cr.stroke()

            # Main ring
            cr.set_source_rgba(*self.color_main, 1.0)
            cr.set_line_width(ring_width)
            cr.arc(center_x, center_y, ring_radius, 0, 2 * math.pi)
            cr.stroke()

            return False

        # Normal audio-reactive animation (existing code)
        outer_points = []
        inner_points = []

        for i in range(WAVE_POINTS):
            angle = (i / WAVE_POINTS) * 2 * math.pi + angle_offset
            level = levels[i]

            # Wave animation
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

        # Draw glow (if active)
        if global_level > 0.1:
            glow_alpha = 0.15 + global_level * 0.2
            cr.set_source_rgba(*self.color_dim, glow_alpha)
            cr.set_line_width(5)

            glow_points = []
            for i in range(WAVE_POINTS):
                angle = (i / WAVE_POINTS) * 2 * math.pi + angle_offset
                level = levels[i]
                wave = math.sin(self.frame * 0.05 + angle * 3) * 0.15
                amp = (level * max_amplitude * 0.9 + wave * max_amplitude * 0.3) * 1.1
                amp *= 0.4 + global_level * 0.9
                r = mid_radius + amp
                glow_points.append((center_x + math.cos(angle) * r, center_y + math.sin(angle) * r))

            if glow_points:
                cr.move_to(*glow_points[0])
                for point in glow_points[1:]:
                    cr.line_to(*point)
                cr.close_path()
                cr.stroke()

        # Draw filled donut
        if len(outer_points) > 2 and len(inner_points) > 2:
            cr.set_source_rgba(*self.color_mid, 0.9)

            # Outer path
            cr.move_to(*outer_points[0])
            for point in outer_points[1:]:
                cr.line_to(*point)
            cr.close_path()

            # Inner path (reverse for hole)
            cr.move_to(*inner_points[0])
            for point in reversed(inner_points[1:]):
                cr.line_to(*point)
            cr.close_path()

            cr.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
            cr.fill()

        # Draw outer edge
        if len(outer_points) > 2:
            intensity = min(1.0, 0.5 + global_level * 0.6)
            edge_color = tuple(
                self.color_dim[i] + (self.color_main[i] - self.color_dim[i]) * intensity
                for i in range(3)
            )
            cr.set_source_rgba(*edge_color, 1.0)
            cr.set_line_width(2)

            cr.move_to(*outer_points[0])
            for point in outer_points[1:]:
                cr.line_to(*point)
            cr.close_path()
            cr.stroke()

        # Draw inner edge
        if len(inner_points) > 2:
            cr.set_source_rgba(*self.color_dim, 1.0)
            cr.set_line_width(2)

            cr.move_to(*inner_points[0])
            for point in inner_points[1:]:
                cr.line_to(*point)
            cr.close_path()
            cr.stroke()

        # Draw highlight (if loud)
        if global_level > 0.25:
            highlight_alpha = global_level * 0.5
            cr.set_source_rgba(*self.color_glow, highlight_alpha)
            cr.set_line_width(1)

            cr.move_to(*outer_points[0])
            for point in outer_points[1:]:
                cr.line_to(*point)
            cr.close_path()
            cr.stroke()

        return False

    def on_destroy(self, widget):
        """Handle window destruction."""
        self.stop_animation()

    def update_audio(self, audio_chunk: bytes):
        """Update with new audio data."""
        try:
            data = np.frombuffer(audio_chunk, dtype=np.int16)
            if len(data) == 0:
                return

            # Calculate raw RMS
            raw_rms = np.sqrt(np.mean(data.astype(np.float32) ** 2)) / 8000

            with self.lock:
                # Adaptive gain control
                if raw_rms > self.peak_level:
                    self.peak_level = raw_rms
                    self.peak_hold_counter = PEAK_HOLD_FRAMES
                elif self.peak_hold_counter > 0:
                    self.peak_hold_counter -= 1
                else:
                    self.peak_level *= 0.995

                if self.peak_level > 0.7:
                    target_gain = 0.7 / max(self.peak_level, 0.01)
                    target_gain = max(MIN_GAIN, min(MAX_GAIN, target_gain))
                    self.adaptive_gain += (target_gain - self.adaptive_gain) * GAIN_ATTACK
                else:
                    self.adaptive_gain += (DEFAULT_GAIN - self.adaptive_gain) * GAIN_RELEASE

                self.adaptive_gain = max(MIN_GAIN, min(MAX_GAIN, self.adaptive_gain))

                # Apply gain and soft compression
                rms = self._soft_compress(raw_rms * self.adaptive_gain)
                self.global_level = self.global_level * 0.7 + rms * 0.3

            # FFT analysis
            fft_data = np.abs(np.fft.rfft(data))
            fft_size = len(fft_data)

            with self.lock:
                for i in range(WAVE_POINTS):
                    freq_idx = 1 + int((i / WAVE_POINTS) * (fft_size - 1) * 0.7)
                    freq_idx = min(freq_idx, fft_size - 1)
                    level = fft_data[freq_idx] / 35000
                    level = self._soft_compress(level * self.adaptive_gain)
                    self.levels[i] = self.levels[i] * 0.4 + level * 0.6

        except Exception:
            pass

    def _soft_compress(self, value: float) -> float:
        """Apply soft compression to prevent visual clipping."""
        if value <= 0.0:
            return 0.0
        if value < 0.5:
            return value
        compressed = 0.5 + 0.5 * (1.0 - math.exp(-(value - 0.5) * 2.0))
        return min(1.0, compressed)


class Visualizer:
    """GTK-based visualizer with true transparency on Linux."""

    def __init__(self):
        self.running = False
        self.thread = None
        self._ready = threading.Event()
        self.window = None
        self.processing = False  # Processing mode (pulsing loader animation)
        self._owns_gtk_loop = False
        self._pending_color: str | None = None  # Color to apply when window is created

    def set_colors(self, color_name: str):
        """Dynamically switch ring color by Flexoki color name."""
        from .config import FLEXOKI_COLORS

        color_name = color_name.lower()
        if color_name not in FLEXOKI_COLORS:
            color_name = "orange"

        # Store for later if window doesn't exist yet
        self._pending_color = color_name

        colors = FLEXOKI_COLORS[color_name]
        if self.window:
            with self.window.lock:
                self.window.color_main = tuple(c / 255.0 for c in colors["main"])
                self.window.color_mid = tuple(c / 255.0 for c in colors["mid"])
                self.window.color_dim = tuple(c / 255.0 for c in colors["dim"])
                self.window.color_glow = tuple(c / 255.0 for c in colors["glow"])

    def start(self):
        """Start the visualizer in a separate thread."""
        if self.running:
            return

        self.running = True
        self._ready.clear()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self):
        """Stop the visualizer completely."""
        self.processing = False
        self.running = False

        if self.window:
            # Schedule window destruction on GTK main thread
            GLib.idle_add(self._destroy_window)

        if self.thread:
            self.thread.join(timeout=1.0)

    def start_processing(self):
        """Switch to processing mode (pulsing loader animation).

        Called when recording stops but processing (transcription + LLM) is starting.
        The ring will pulse rhythmically until stop() is called.
        """
        self.processing = True
        if self.window:
            with self.window.lock:
                self.window.processing = True
                # Reset audio levels for clean pulsing animation (must stay numpy arrays)
                self.window.levels = np.zeros(WAVE_POINTS)
                self.window.smooth_levels = np.zeros(WAVE_POINTS)
                self.window.global_level = 0.0

    def _destroy_window(self):
        """Destroy window from GTK thread."""
        if self.window:
            self.window.stop_animation()
            self.window.destroy()
            self.window = None
        if self._owns_gtk_loop:
            Gtk.main_quit()
        return False

    def update(self, audio_chunk: bytes):
        """Update visualizer with audio data."""
        if self.window and self.running:
            # Schedule update on GTK main thread
            GLib.idle_add(self.window.update_audio, audio_chunk)

    def _run(self):
        """Run the GTK visualizer.

        If a GTK main loop is already running (e.g. from the system tray),
        we schedule window creation on that loop via GLib.idle_add().
        Otherwise we start our own loop.
        """
        try:
            # Schedule window creation on the GTK main context
            GLib.idle_add(self._create_window)

            # Check if a GTK main loop is already running (e.g. from the tray).
            # Gtk.main_level() is per-thread, so we probe the default context:
            # if we can acquire it, nobody else is running a loop.
            ctx = GLib.MainContext.default()
            owns = ctx.acquire()
            if owns:
                ctx.release()
                # No existing loop — start our own
                self._owns_gtk_loop = True
                Gtk.main()
            else:
                # Another thread (tray) is running Gtk.main(); piggyback on it.
                self._owns_gtk_loop = False
                self._ready.wait(timeout=3.0)  # wait for idle_add to fire
                # Keep thread alive until stop() is called
                while self.running:
                    import time

                    time.sleep(0.1)

        except Exception as e:
            print(f"GTK Visualizer error: {e}")
            if config.DEBUG:
                import traceback

                traceback.print_exc()
        finally:
            self._ready.set()

    def _create_window(self):
        """Create the visualizer window (called on GTK thread via idle_add)."""
        try:
            display = Gdk.Display.get_default()
            monitor = display.get_primary_monitor()
            geometry = monitor.get_geometry()
            screen_w, screen_h = geometry.width, geometry.height

            pos_x, pos_y = config.get_animation_position(screen_w, screen_h, SIZE)

            self.window = TransparentVisualizerWindow()

            # Apply pending color if set_colors() was called before window creation
            if self._pending_color:
                self.set_colors(self._pending_color)

            self.window.move(pos_x, pos_y)

            # realize() creates the underlying X11 window without mapping it,
            # so we can set _NET_WM_WINDOW_TYPE BEFORE i3 sees the MapRequest.
            self.window.realize()
            self._set_x11_window_type()

            self.window.show_all()

            self.window.start_animation()
        except Exception as e:
            print(f"GTK Visualizer window creation error: {e}")
            if config.DEBUG:
                import traceback

                traceback.print_exc()
        finally:
            self._ready.set()
        return False  # run once

    def _set_x11_window_type(self):
        """Set _NET_WM_WINDOW_TYPE via Xlib so tiling WMs float this window.

        Must be called after realize() but before show_all() so i3 sees the
        property on the initial MapRequest. Uses UTILITY which i3 auto-floats
        (NOTIFICATION is not in i3's float list).
        """
        try:
            from Xlib import display as xdisplay

            gdk_window = self.window.get_window()
            if gdk_window is None:
                return
            xid = gdk_window.get_xid()

            d = xdisplay.Display()
            window = d.create_resource_object("window", xid)
            wm_type = d.intern_atom("_NET_WM_WINDOW_TYPE")
            wm_utility = d.intern_atom("_NET_WM_WINDOW_TYPE_UTILITY")
            window.change_property(wm_type, d.intern_atom("ATOM"), 32, [wm_utility])
            d.sync()
        except ImportError:
            pass
        except Exception as e:
            if config.DEBUG:
                print(f"⚠ Could not set X11 window type: {e}")


# Singleton instance
_visualizer = None


def get_visualizer() -> Visualizer:
    """Get the global visualizer instance."""
    global _visualizer
    if _visualizer is None:
        _visualizer = Visualizer()
    return _visualizer
