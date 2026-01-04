"""Elegant circular audio visualizer - donut waveform with transparent background"""

import math
import os
import threading

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

# Platform-specific SDL settings (only for X11/Linux)
from .platform_utils import IS_LINUX, IS_WINDOWS, IS_X11

if IS_LINUX and IS_X11:
    os.environ["SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR"] = "0"

import numpy as np

from .config import config

# Transparency colorkey (magenta - unlikely to be used in the visualizer)
TRANSPARENT_COLORKEY = (255, 0, 255)

SIZE = 160
WAVE_POINTS = 90

# Adaptive gain settings
DEFAULT_GAIN = 0.7  # Reduced from implicit 1.0 for lower default saturation
MIN_GAIN = 0.3  # Minimum gain floor
MAX_GAIN = 1.5  # Maximum gain ceiling
GAIN_ATTACK = 0.02  # How fast gain decreases (fast attack for loud sounds)
GAIN_RELEASE = 0.005  # How slow gain increases (slow release for recovery)
PEAK_HOLD_FRAMES = 30  # Frames to hold peak before decay (~0.5s at 60fps)


class Visualizer:
    """Circular donut audio visualizer with transparent background"""

    def __init__(self):
        self.running = False
        self.thread = None
        self.levels = np.zeros(WAVE_POINTS)
        self.smooth_levels = np.zeros(WAVE_POINTS)
        self.lock = threading.Lock()
        self._ready = threading.Event()
        self.frame = 0
        self.global_level = 0.0
        self.transparent = True  # Enable transparent background
        self.linux_opacity_mode = False  # Set by _setup_linux_transparency
        self.xshape_mode = False  # Set by _setup_xshape_circular

        # Processing mode (pulsing loader animation)
        self.processing = False

        # Adaptive gain control
        self.adaptive_gain = DEFAULT_GAIN
        self.peak_level = 0.0
        self.peak_hold_counter = 0

        # Load theme colors from config
        colors = config.get_theme_colors()
        self.COLOR_MAIN = colors["main"]
        self.COLOR_MID = colors["mid"]
        self.COLOR_DIM = colors["dim"]
        self.COLOR_GLOW = colors["glow"]

    def set_colors(self, color_name: str):
        """Dynamically switch ring color by Flexoki color name.

        Args:
            color_name: One of 'red', 'orange', 'yellow', 'green', 'cyan', 'blue', 'purple', 'magenta'
        """
        from .config import FLEXOKI_COLORS

        color_name = color_name.lower()
        if color_name not in FLEXOKI_COLORS:
            color_name = "orange"  # fallback

        colors = FLEXOKI_COLORS[color_name]
        with self.lock:
            self.COLOR_MAIN = colors["main"]
            self.COLOR_MID = colors["mid"]
            self.COLOR_DIM = colors["dim"]
            self.COLOR_GLOW = colors["glow"]

    def start(self):
        if self.running:
            return

        self.running = True
        self.levels = np.zeros(WAVE_POINTS)
        self.smooth_levels = np.zeros(WAVE_POINTS)
        self.frame = 0
        self.global_level = 0.0
        self.adaptive_gain = DEFAULT_GAIN
        self.peak_level = 0.0
        self.peak_hold_counter = 0
        self.linux_opacity_mode = False
        self._ready.clear()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=2.0)

    def stop(self):
        """Stop the visualizer completely."""
        self.processing = False
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def start_processing(self):
        """Switch to processing mode (pulsing loader animation).

        Called when recording stops but processing (transcription + LLM) is starting.
        The ring will pulse rhythmically until stop() is called.
        """
        with self.lock:
            self.processing = True
            # Reset levels for clean pulsing animation
            self.levels = np.zeros(WAVE_POINTS)
            self.smooth_levels = np.zeros(WAVE_POINTS)
            self.global_level = 0.0

    def update(self, audio_chunk: bytes):
        if not self.running:
            return

        try:
            data = np.frombuffer(audio_chunk, dtype=np.int16)
            if len(data) == 0:
                return

            # Calculate raw RMS (before gain)
            raw_rms = np.sqrt(np.mean(data.astype(np.float32) ** 2)) / 8000

            # Adaptive gain adjustment based on peak levels
            with self.lock:
                # Track peak level with hold and decay
                if raw_rms > self.peak_level:
                    self.peak_level = raw_rms
                    self.peak_hold_counter = PEAK_HOLD_FRAMES
                elif self.peak_hold_counter > 0:
                    self.peak_hold_counter -= 1
                else:
                    # Slow decay of peak level
                    self.peak_level *= 0.995

                # Adjust gain based on peak level to prevent clipping
                if self.peak_level > 0.7:
                    # Reduce gain quickly when loud (attack)
                    target_gain = 0.7 / max(self.peak_level, 0.01)
                    target_gain = max(MIN_GAIN, min(MAX_GAIN, target_gain))
                    self.adaptive_gain += (target_gain - self.adaptive_gain) * GAIN_ATTACK
                else:
                    # Slowly return to default gain (release)
                    self.adaptive_gain += (DEFAULT_GAIN - self.adaptive_gain) * GAIN_RELEASE

                # Clamp gain to valid range
                self.adaptive_gain = max(MIN_GAIN, min(MAX_GAIN, self.adaptive_gain))

                # Apply adaptive gain and soft compression
                rms = self._soft_compress(raw_rms * self.adaptive_gain)
                self.global_level = self.global_level * 0.7 + rms * 0.3

            fft_data = np.abs(np.fft.rfft(data))
            fft_size = len(fft_data)

            with self.lock:
                for i in range(WAVE_POINTS):
                    # Skip DC component (bin 0) which is always high
                    freq_idx = 1 + int((i / WAVE_POINTS) * (fft_size - 1) * 0.7)
                    freq_idx = min(freq_idx, fft_size - 1)
                    # Apply adaptive gain and soft compression to FFT levels
                    level = fft_data[freq_idx] / 35000
                    level = self._soft_compress(level * self.adaptive_gain)
                    self.levels[i] = self.levels[i] * 0.4 + level * 0.6

        except Exception:
            pass

    def _soft_compress(self, value: float) -> float:
        """Apply soft compression to prevent visual clipping.

        Uses a smooth saturation curve that approaches 1.0 asymptotically.
        Values below 0.5 pass through nearly unchanged.
        Values above 0.5 are progressively compressed.
        """
        if value <= 0.0:
            return 0.0
        if value < 0.5:
            # Linear region for quiet sounds
            return value
        # Soft knee compression: 1 - e^(-x) curve shifted to knee point
        # This gives smooth saturation approaching 1.0
        compressed = 0.5 + 0.5 * (1.0 - math.exp(-(value - 0.5) * 2.0))
        return min(1.0, compressed)

    def _run(self):
        try:
            import pygame

            pygame.init()

            # Get position from config
            info = pygame.display.Info()
            screen_w, screen_h = info.current_w, info.current_h
            pos_x, pos_y = config.get_animation_position(screen_w, screen_h, SIZE)

            # Set window position (cross-platform approach)
            # SDL_VIDEO_WINDOW_POS works on most platforms
            os.environ["SDL_VIDEO_WINDOW_POS"] = f"{pos_x},{pos_y}"

            screen = pygame.display.set_mode((SIZE, SIZE), pygame.NOFRAME)
            pygame.display.set_caption("Dicton")

            # Enable transparency based on platform
            if IS_WINDOWS and self.transparent:
                self._setup_windows_transparency(pygame)
            elif IS_LINUX and IS_X11 and self.transparent:
                self._setup_linux_transparency(pygame)

            clock = pygame.time.Clock()
            self._ready.set()

            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        break

                self._draw(screen, pygame)
                self.frame += 1
                clock.tick(60)

            pygame.quit()

        except Exception as e:
            print(f"Visualizer error: {e}")
            self._ready.set()

    def _setup_windows_transparency(self, pygame):
        """Set up transparent window on Windows using layered window API"""
        try:
            import win32api
            import win32con
            import win32gui

            hwnd = pygame.display.get_wm_info()["window"]
            # Add layered window style
            win32gui.SetWindowLong(
                hwnd,
                win32con.GWL_EXSTYLE,
                win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_LAYERED,
            )
            # Set colorkey for transparency (magenta becomes transparent)
            win32gui.SetLayeredWindowAttributes(
                hwnd,
                win32api.RGB(*TRANSPARENT_COLORKEY),
                0,
                win32con.LWA_COLORKEY,
            )
        except ImportError:
            # pywin32 not installed, transparency not available
            self.transparent = False
        except Exception:
            self.transparent = False

    def _setup_linux_transparency(self, pygame):
        """Set up transparent window on Linux X11.

        Tries XShape extension first (works without compositor) for true
        circular window shape, then falls back to window opacity if compositor
        is available.
        """
        # Try XShape first - works without compositor
        if self._setup_xshape_circular(pygame):
            return

        # Fall back to opacity mode (requires compositor)
        try:
            from pygame._sdl2.video import Window

            sdl_window = Window.from_display_module()
            opacity = max(0.0, min(1.0, config.VISUALIZER_OPACITY))
            sdl_window.opacity = opacity
            self.linux_opacity_mode = True
            if config.DEBUG:
                print(f"✓ Linux X11 transparency enabled (opacity: {opacity})")
        except (ImportError, AttributeError) as e:
            if config.DEBUG:
                print(f"⚠ Linux transparency not available: {e}")
            self.linux_opacity_mode = False
            self.transparent = False
        except Exception as e:
            if config.DEBUG:
                print(f"⚠ Window opacity failed (compositor running?): {e}")
            self.linux_opacity_mode = False
            self.transparent = False

    def _setup_xshape_circular(self, pygame):
        """Set up circular window shape using X11 XShape extension.

        Creates a truly circular window that works without a compositor.
        The window shape is defined at the X11 protocol level, so only
        the circular area is visible and receives input.

        Returns True if successful, False otherwise.
        """
        try:
            from Xlib import display
            from Xlib.ext import shape

            # Get X11 window ID from pygame
            wm_info = pygame.display.get_wm_info()
            window_id = wm_info.get("window")
            if not window_id:
                if config.DEBUG:
                    print("⚠ Could not get X11 window ID")
                return False

            # Connect to X display
            d = display.Display()
            window = d.create_resource_object("window", window_id)

            # Check if XShape extension is available
            if not d.has_extension("SHAPE"):
                if config.DEBUG:
                    print("⚠ XShape extension not available")
                return False

            # Create a pixmap for the circular shape mask (1-bit depth)
            pixmap = window.create_pixmap(SIZE, SIZE, 1)

            # Create a GC for drawing on the pixmap
            gc = pixmap.create_gc(foreground=0, background=0)

            # Clear pixmap to transparent (0)
            pixmap.fill_rectangle(gc, 0, 0, SIZE, SIZE)

            # Draw filled circle (1 = opaque)
            gc.change(foreground=1)
            # fill_arc: x, y, width, height, angle1, angle2
            # Angles are in 64ths of a degree, full circle = 360*64
            pixmap.fill_arc(gc, 0, 0, SIZE, SIZE, 0, 360 * 64)

            # Apply the shape to the window (method is on window object)
            window.shape_mask(
                shape.SO.Set,
                shape.SK.Bounding,
                0, 0,  # x, y offset
                pixmap
            )

            # Also set input shape so clicks pass through transparent areas
            window.shape_mask(
                shape.SO.Set,
                shape.SK.Input,
                0, 0,
                pixmap
            )

            d.sync()
            pixmap.free()

            self.xshape_mode = True
            if config.DEBUG:
                print("✓ XShape circular window enabled")
            return True

        except ImportError:
            if config.DEBUG:
                print("⚠ python-xlib not installed for XShape support")
            return False
        except Exception as e:
            if config.DEBUG:
                print(f"⚠ XShape setup failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _draw(self, screen, pygame):
        # Use transparent colorkey background on Windows, dark background elsewhere
        # Background color: colorkey for Windows transparency, dark for XShape/others
        if IS_WINDOWS and self.transparent:
            bg_color = TRANSPARENT_COLORKEY
        elif self.xshape_mode:
            bg_color = (15, 15, 18)  # Dark background, shape handles transparency
        else:
            bg_color = (20, 20, 24)
        screen.fill(bg_color)

        center_x = SIZE // 2
        center_y = SIZE // 2

        outer_radius = SIZE // 2 - 10
        inner_radius = 20  # Inner edge of ring
        mid_radius = (outer_radius + inner_radius) // 2
        max_amplitude = (outer_radius - inner_radius) // 2 - 2

        # Check if we're in processing mode (pulsing loader)
        with self.lock:
            is_processing = self.processing
            levels_copy = self.levels.copy()
            global_level = self.global_level

        if is_processing:
            # Simple pulsing: ring shrinks to center and expands back
            pulse_phase = self.frame * 0.03  # Slow, calm pulse
            pulse = (math.sin(pulse_phase) + 1) / 2  # 0 to 1

            # Ring radius pulses between inner_radius+10 and outer_radius
            min_ring_radius = inner_radius + 15
            max_ring_radius = outer_radius - 5
            ring_radius = min_ring_radius + pulse * (max_ring_radius - min_ring_radius)

            # Ring thickness stays constant
            ring_width = 4

            # Draw simple pulsing ring
            pygame.draw.circle(screen, self.COLOR_MAIN, (center_x, center_y), int(ring_radius), ring_width)

            # Subtle glow that pulses with the ring
            glow_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            glow_alpha = int(40 + pulse * 30)
            pygame.draw.circle(glow_surf, (*self.COLOR_DIM, glow_alpha), (center_x, center_y), int(ring_radius) + 3, ring_width + 4)
            screen.blit(glow_surf, (0, 0))

            pygame.display.flip()
            return

        # Normal audio-reactive animation (existing code)
        for i in range(WAVE_POINTS):
            self.smooth_levels[i] = self.smooth_levels[i] * 0.82 + levels_copy[i] * 0.18

        # Calculate wave points
        outer_points = []
        inner_points = []

        # Rotation offset: +π/2 to start from top (90° counter-clockwise)
        angle_offset = math.pi / 2

        for i in range(WAVE_POINTS):
            angle = (i / WAVE_POINTS) * 2 * math.pi + angle_offset
            level = self.smooth_levels[i]

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

        # Draw glow (using SRCALPHA surface for proper blending)
        # Reduced glow threshold and intensity for lower saturation
        if global_level > 0.1:
            glow_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            # Reduced glow alpha: was 60 + 80*level, now 40 + 50*level
            glow_alpha = int(40 + global_level * 50)

            glow_outer = []
            for i in range(WAVE_POINTS):
                angle = (i / WAVE_POINTS) * 2 * math.pi + angle_offset
                level = self.smooth_levels[i]
                wave = math.sin(self.frame * 0.05 + angle * 3) * 0.15
                # Reduced glow expansion: was 1.2, now 1.1
                amp = (level * max_amplitude * 0.9 + wave * max_amplitude * 0.3) * 1.1
                amp *= 0.4 + global_level * 0.9
                r = mid_radius + amp
                glow_outer.append((center_x + math.cos(angle) * r, center_y + math.sin(angle) * r))

            pygame.draw.polygon(glow_surf, (*self.COLOR_DIM, glow_alpha), glow_outer, width=4)
            screen.blit(glow_surf, (0, 0))

        # Draw filled donut
        if len(outer_points) > 2 and len(inner_points) > 2:
            donut_shape = outer_points + inner_points[::-1]
            pygame.draw.polygon(screen, self.COLOR_MID, donut_shape)

        # Outer edge
        if len(outer_points) > 2:
            intensity = min(1.0, 0.5 + global_level * 0.6)
            line_color = (
                int(self.COLOR_DIM[0] + (self.COLOR_MAIN[0] - self.COLOR_DIM[0]) * intensity),
                int(self.COLOR_DIM[1] + (self.COLOR_MAIN[1] - self.COLOR_DIM[1]) * intensity),
                int(self.COLOR_DIM[2] + (self.COLOR_MAIN[2] - self.COLOR_DIM[2]) * intensity),
            )
            pygame.draw.polygon(screen, line_color, outer_points, width=2)

        # Inner edge
        if len(inner_points) > 2:
            pygame.draw.polygon(screen, self.COLOR_DIM, inner_points, width=2)

        # Cut out center - smaller dark circle in the middle
        pygame.draw.circle(screen, bg_color, (center_x, center_y), inner_radius - 8)

        # Highlight (reduced intensity for lower saturation)
        if global_level > 0.25:
            highlight_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            # Reduced highlight alpha: was 180*level, now 120*level
            pygame.draw.polygon(
                highlight_surf, (*self.COLOR_GLOW, int(global_level * 120)), outer_points, width=1
            )
            screen.blit(highlight_surf, (0, 0))

        pygame.display.flip()


_visualizer = None


def get_visualizer() -> Visualizer:
    global _visualizer
    if _visualizer is None:
        _visualizer = Visualizer()
    return _visualizer
