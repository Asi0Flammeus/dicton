"""VisPy-based audio visualizer with multiple professional styles"""

import threading
from abc import ABC, abstractmethod

import numpy as np

# Use pyglet backend for VisPy (lighter than PyQt6, works well with X11)
import vispy

from .config import config

vispy.use("pyglet")

# VisPy imports
from vispy import app, gloo
from vispy.gloo import Program

# Background color (transparent for toric style, dark for others)
BG_COLOR = (0.078, 0.078, 0.094, 1.0)  # RGB normalized (20, 20, 24)
BG_COLOR_TRANSPARENT = (0.0, 0.0, 0.0, 0.0)  # Fully transparent

# FFT and smoothing settings
FFT_BINS = 64
SMOOTHING = 0.15


class BaseVisualizerStyle(ABC):
    """Abstract base class for visualization styles"""

    def __init__(self, canvas, colors):
        self.canvas = canvas
        self.colors = colors
        self.program = None
        self.setup()

    @abstractmethod
    def setup(self):
        """Initialize shaders and buffers"""
        pass

    @abstractmethod
    def update(self, levels: np.ndarray, global_level: float, frame: int):
        """Update visualization with new audio data"""
        pass

    @abstractmethod
    def draw(self):
        """Draw the visualization"""
        pass


class MinimalisticStyle(BaseVisualizerStyle):
    """Small pulsing circle - minimalistic style"""

    VERTEX_SHADER = """
    attribute vec2 a_position;
    uniform float u_radius;
    uniform float u_pulse;
    uniform vec2 u_center;

    void main() {
        vec2 pos = a_position * u_radius * (1.0 + u_pulse * 0.3) + u_center;
        gl_Position = vec4(pos, 0.0, 1.0);
    }
    """

    FRAGMENT_SHADER = """
    uniform vec4 u_color;
    uniform float u_glow;

    void main() {
        float alpha = 0.7 + u_glow * 0.3;
        gl_FragColor = vec4(u_color.rgb, alpha);
    }
    """

    def setup(self):
        self.program = Program(self.VERTEX_SHADER, self.FRAGMENT_SHADER)

        # Create circle vertices
        n_points = 64
        theta = np.linspace(0, 2 * np.pi, n_points, dtype=np.float32)
        circle = np.zeros((n_points, 2), dtype=np.float32)
        circle[:, 0] = np.cos(theta)
        circle[:, 1] = np.sin(theta)

        self.program["a_position"] = circle
        self.program["u_center"] = (0.0, 0.0)
        self.program["u_radius"] = 0.3
        self.program["u_pulse"] = 0.0
        self.program["u_glow"] = 0.0

        # Set color (normalize to 0-1)
        main_color = self.colors["main"]
        self.program["u_color"] = (
            main_color[0] / 255.0,
            main_color[1] / 255.0,
            main_color[2] / 255.0,
            1.0,
        )

    def update(self, levels: np.ndarray, global_level: float, frame: int):
        # Smooth pulse based on bass frequencies
        bass_level = np.mean(levels[:8]) if len(levels) > 8 else global_level
        self.program["u_pulse"] = float(bass_level)
        self.program["u_glow"] = float(global_level)

    def draw(self):
        self.program.draw("triangle_fan")


class ClassicStyle(BaseVisualizerStyle):
    """Horizontal bars, vertically symmetric (mirror effect)"""

    VERTEX_SHADER = """
    attribute vec2 a_position;
    attribute float a_level;
    uniform float u_bar_width;
    uniform float u_max_height;

    varying float v_level;

    void main() {
        v_level = a_level;
        gl_Position = vec4(a_position, 0.0, 1.0);
    }
    """

    FRAGMENT_SHADER = """
    uniform vec4 u_color_main;
    uniform vec4 u_color_mid;
    uniform vec4 u_color_dim;
    varying float v_level;

    void main() {
        vec4 color = mix(u_color_dim, u_color_main, v_level);
        gl_FragColor = color;
    }
    """

    def setup(self):
        self.n_bars = FFT_BINS
        self.program = Program(self.VERTEX_SHADER, self.FRAGMENT_SHADER)

        # Pre-allocate vertex buffer for bars (each bar = 2 triangles = 6 vertices)
        # For symmetric, we draw top and bottom
        self.vertices = np.zeros((self.n_bars * 12, 2), dtype=np.float32)
        self.levels_attr = np.zeros(self.n_bars * 12, dtype=np.float32)

        bar_width = 1.8 / self.n_bars
        self.bar_width = bar_width
        self.gap = bar_width * 0.1

        self.program["a_position"] = self.vertices
        self.program["a_level"] = self.levels_attr
        self.program["u_bar_width"] = bar_width
        self.program["u_max_height"] = 0.8

        # Set colors
        for color_name in ["main", "mid", "dim"]:
            c = self.colors[color_name]
            self.program[f"u_color_{color_name}"] = (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1.0)

    def update(self, levels: np.ndarray, global_level: float, frame: int):
        bar_width = self.bar_width - self.gap

        for i in range(self.n_bars):
            level = levels[i] if i < len(levels) else 0.0
            height = level * 0.7

            x_left = -0.9 + i * self.bar_width
            x_right = x_left + bar_width

            # Top bar (6 vertices for 2 triangles)
            idx = i * 12
            # Triangle 1
            self.vertices[idx] = (x_left, 0.02)
            self.vertices[idx + 1] = (x_right, 0.02)
            self.vertices[idx + 2] = (x_right, 0.02 + height)
            # Triangle 2
            self.vertices[idx + 3] = (x_left, 0.02)
            self.vertices[idx + 4] = (x_right, 0.02 + height)
            self.vertices[idx + 5] = (x_left, 0.02 + height)

            # Bottom bar (mirrored)
            self.vertices[idx + 6] = (x_left, -0.02)
            self.vertices[idx + 7] = (x_right, -0.02)
            self.vertices[idx + 8] = (x_right, -0.02 - height)
            self.vertices[idx + 9] = (x_left, -0.02)
            self.vertices[idx + 10] = (x_right, -0.02 - height)
            self.vertices[idx + 11] = (x_left, -0.02 - height)

            # Set level for color
            self.levels_attr[idx : idx + 12] = level

        self.program["a_position"].set_data(self.vertices)
        self.program["a_level"].set_data(self.levels_attr)

    def draw(self):
        self.program.draw("triangles")


class LegacyStyle(BaseVisualizerStyle):
    """Horizontal bars, non-symmetric (classic spectrum analyzer)"""

    VERTEX_SHADER = """
    attribute vec2 a_position;
    attribute float a_level;

    varying float v_level;
    varying float v_y;

    void main() {
        v_level = a_level;
        v_y = a_position.y;
        gl_Position = vec4(a_position, 0.0, 1.0);
    }
    """

    FRAGMENT_SHADER = """
    uniform vec4 u_color_main;
    uniform vec4 u_color_mid;
    uniform vec4 u_color_dim;
    uniform vec4 u_color_glow;
    varying float v_level;
    varying float v_y;

    void main() {
        // Gradient from dim at bottom to main at top
        float gradient = (v_y + 0.8) / 1.6;
        vec4 color = mix(u_color_dim, u_color_main, gradient * v_level);

        // Add glow at peaks
        if (v_level > 0.7) {
            color = mix(color, u_color_glow, (v_level - 0.7) * 2.0);
        }

        gl_FragColor = color;
    }
    """

    def setup(self):
        self.n_bars = FFT_BINS
        self.program = Program(self.VERTEX_SHADER, self.FRAGMENT_SHADER)

        # 6 vertices per bar (2 triangles)
        self.vertices = np.zeros((self.n_bars * 6, 2), dtype=np.float32)
        self.levels_attr = np.zeros(self.n_bars * 6, dtype=np.float32)

        bar_width = 1.8 / self.n_bars
        self.bar_width = bar_width
        self.gap = bar_width * 0.15

        self.program["a_position"] = self.vertices
        self.program["a_level"] = self.levels_attr

        # Set colors
        for color_name in ["main", "mid", "dim", "glow"]:
            c = self.colors[color_name]
            self.program[f"u_color_{color_name}"] = (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1.0)

    def update(self, levels: np.ndarray, global_level: float, frame: int):
        bar_width = self.bar_width - self.gap

        for i in range(self.n_bars):
            level = levels[i] if i < len(levels) else 0.0
            height = level * 1.5  # Scale to use more vertical space

            x_left = -0.9 + i * self.bar_width
            x_right = x_left + bar_width
            y_bottom = -0.8
            y_top = y_bottom + height

            idx = i * 6
            # Triangle 1
            self.vertices[idx] = (x_left, y_bottom)
            self.vertices[idx + 1] = (x_right, y_bottom)
            self.vertices[idx + 2] = (x_right, y_top)
            # Triangle 2
            self.vertices[idx + 3] = (x_left, y_bottom)
            self.vertices[idx + 4] = (x_right, y_top)
            self.vertices[idx + 5] = (x_left, y_top)

            self.levels_attr[idx : idx + 6] = level

        self.program["a_position"].set_data(self.vertices)
        self.program["a_level"].set_data(self.levels_attr)

    def draw(self):
        self.program.draw("triangles")


class ToricStyle(BaseVisualizerStyle):
    """Thin ring outline with audio-reactive displacement - like the original pygame version"""

    VERTEX_SHADER = """
    attribute vec2 a_position;
    attribute float a_angle;
    attribute float a_level;
    attribute float a_base_radius;

    uniform float u_global_level;
    uniform float u_time;
    uniform float u_max_amplitude;

    varying float v_level;
    varying float v_intensity;

    void main() {
        v_level = a_level;

        // Wave animations like the original
        float wave1 = sin(u_time * 3.0 + a_angle * 3.0) * 0.15;
        float wave2 = sin(u_time * 2.1 + a_angle * 5.0) * 0.1;
        float wave3 = sin(u_time * 3.6 + a_angle * 2.0) * 0.08;

        float base_wave = (wave1 + wave2 + wave3) * u_max_amplitude * 0.3;
        float amplitude = a_level * u_max_amplitude * 0.9 + base_wave;
        amplitude *= (0.4 + u_global_level * 0.9);

        // Calculate displaced radius
        float displaced_radius = a_base_radius + amplitude;

        // Calculate position from angle and radius
        vec2 pos = vec2(cos(a_angle), sin(a_angle)) * displaced_radius;

        v_intensity = 0.5 + u_global_level * 0.6;

        gl_Position = vec4(pos, 0.0, 1.0);
    }
    """

    FRAGMENT_SHADER = """
    uniform vec4 u_color_main;
    uniform vec4 u_color_dim;
    uniform vec4 u_color_glow;
    uniform float u_global_level;

    varying float v_level;
    varying float v_intensity;

    void main() {
        // Color interpolation based on intensity
        vec4 color = mix(u_color_dim, u_color_main, v_intensity);

        // Add glow at high levels
        if (u_global_level > 0.2) {
            float glow = (u_global_level - 0.2) * 0.8;
            color = mix(color, u_color_glow, glow * v_level);
        }

        gl_FragColor = color;
    }
    """

    def setup(self):
        self.n_segments = 90  # Match original WAVE_POINTS
        self.program = Program(self.VERTEX_SHADER, self.FRAGMENT_SHADER)

        # Ring parameters - single thin ring
        self.base_radius = 0.45
        self.max_amplitude = 0.25

        # Create ring vertices (line loop)
        self.vertices = np.zeros((self.n_segments, 2), dtype=np.float32)
        self.angles = np.zeros(self.n_segments, dtype=np.float32)
        self.levels_attr = np.zeros(self.n_segments, dtype=np.float32)
        self.base_radii = np.zeros(self.n_segments, dtype=np.float32)

        # Smoothed levels for animation
        self.smooth_levels = np.zeros(self.n_segments, dtype=np.float32)

        # Initialize geometry - start from top (add π/2 offset)
        angle_offset = np.pi / 2
        for i in range(self.n_segments):
            angle = (i / self.n_segments) * 2 * np.pi + angle_offset
            self.angles[i] = angle
            self.base_radii[i] = self.base_radius
            # Initial position
            self.vertices[i] = (np.cos(angle) * self.base_radius, np.sin(angle) * self.base_radius)

        self.program["a_position"] = self.vertices
        self.program["a_angle"] = self.angles
        self.program["a_level"] = self.levels_attr
        self.program["a_base_radius"] = self.base_radii
        self.program["u_global_level"] = 0.0
        self.program["u_time"] = 0.0
        self.program["u_max_amplitude"] = self.max_amplitude

        # Set colors
        for color_name in ["main", "dim", "glow"]:
            c = self.colors[color_name]
            self.program[f"u_color_{color_name}"] = (c[0] / 255.0, c[1] / 255.0, c[2] / 255.0, 1.0)

        # Enable line smoothing
        gloo.set_line_width(2.0)

    def update(self, levels: np.ndarray, global_level: float, frame: int):
        self.program["u_global_level"] = float(global_level)
        self.program["u_time"] = float(frame) * 0.05  # Match original timing

        # Smooth the levels like the original
        for i in range(self.n_segments):
            level = levels[i % len(levels)] if len(levels) > 0 else 0.0
            self.smooth_levels[i] = self.smooth_levels[i] * 0.82 + level * 0.18
            self.levels_attr[i] = self.smooth_levels[i]

        self.program["a_level"].set_data(self.levels_attr)

    def draw(self):
        self.program.draw("line_loop")


class TerminalStyle(BaseVisualizerStyle):
    """Retro terminal/ASCII-inspired visualization using point sprites"""

    VERTEX_SHADER = """
    attribute vec2 a_position;
    attribute float a_level;
    attribute float a_char_idx;

    uniform float u_point_size;

    varying float v_level;
    varying float v_char_idx;

    void main() {
        v_level = a_level;
        v_char_idx = a_char_idx;
        gl_Position = vec4(a_position, 0.0, 1.0);
        gl_PointSize = u_point_size * (0.5 + v_level * 0.5);
    }
    """

    FRAGMENT_SHADER = """
    uniform vec4 u_color_main;
    uniform vec4 u_color_dim;

    varying float v_level;
    varying float v_char_idx;

    void main() {
        // Create blocky terminal-like appearance
        vec2 coord = gl_PointCoord * 2.0 - 1.0;

        // Square shape with slight rounding
        float d = max(abs(coord.x), abs(coord.y));
        if (d > 0.8) discard;

        // Scanline effect
        float scanline = 0.9 + 0.1 * sin(gl_FragCoord.y * 0.5);

        // Color based on level
        vec4 color = mix(u_color_dim, u_color_main, v_level);
        color.rgb *= scanline;

        // Add slight green tint for terminal feel
        color.g += 0.05 * v_level;

        gl_FragColor = color;
    }
    """

    def setup(self):
        self.n_cols = 32
        self.n_rows = 16
        self.program = Program(self.VERTEX_SHADER, self.FRAGMENT_SHADER)

        n_points = self.n_cols * self.n_rows
        self.positions = np.zeros((n_points, 2), dtype=np.float32)
        self.levels_attr = np.zeros(n_points, dtype=np.float32)
        self.char_indices = np.zeros(n_points, dtype=np.float32)

        # Create grid
        for row in range(self.n_rows):
            for col in range(self.n_cols):
                idx = row * self.n_cols + col
                x = -0.9 + (col / self.n_cols) * 1.8
                y = 0.8 - (row / self.n_rows) * 1.6
                self.positions[idx] = (x, y)
                self.char_indices[idx] = float(col)

        self.program["a_position"] = self.positions
        self.program["a_level"] = self.levels_attr
        self.program["a_char_idx"] = self.char_indices
        self.program["u_point_size"] = 12.0

        # Set colors (green tint for terminal)
        main = self.colors["main"]
        dim = self.colors["dim"]
        self.program["u_color_main"] = (main[0] / 255.0, main[1] / 255.0, main[2] / 255.0, 1.0)
        self.program["u_color_dim"] = (dim[0] / 255.0, dim[1] / 255.0, dim[2] / 255.0, 0.3)

    def update(self, levels: np.ndarray, global_level: float, frame: int):
        # Map frequency bins to columns
        bins_per_col = max(1, len(levels) // self.n_cols)

        for row in range(self.n_rows):
            threshold = (self.n_rows - row) / self.n_rows
            for col in range(self.n_cols):
                idx = row * self.n_cols + col

                # Get level for this column
                bin_start = col * bins_per_col
                bin_end = min(bin_start + bins_per_col, len(levels))
                if bin_start < len(levels):
                    col_level = np.mean(levels[bin_start:bin_end])
                else:
                    col_level = 0.0

                # Set level if above threshold for this row
                if col_level >= threshold * 0.8:
                    self.levels_attr[idx] = col_level
                else:
                    self.levels_attr[idx] = 0.1  # Dim background

        self.program["a_level"].set_data(self.levels_attr)

    def draw(self):
        self.program.draw("points")


# Style registry
VISUALIZER_STYLES = {
    "minimalistic": MinimalisticStyle,
    "classic": ClassicStyle,
    "legacy": LegacyStyle,
    "toric": ToricStyle,
    "terminal": TerminalStyle,
}


class VisPyVisualizerCanvas(app.Canvas):
    """VisPy canvas for audio visualization"""

    def __init__(
        self, style_name: str = "toric", size: tuple = (200, 200), transparent: bool = False
    ):
        # Configure context for transparency if needed
        context_config = {}
        if transparent:
            # Request RGBA context with alpha channel
            context_config = {
                "red_size": 8,
                "green_size": 8,
                "blue_size": 8,
                "alpha_size": 8,
            }

        # Get window position from config
        # Note: VisPy position is set differently
        app.Canvas.__init__(
            self,
            size=size,
            title="Dicton",
            keys="interactive",
            resizable=False,
            decorate=False,  # Frameless window
            config=context_config if context_config else None,
        )

        self.style_name = style_name
        self.colors = config.get_theme_colors()
        self.transparent = transparent

        # Audio data
        self.levels = np.zeros(FFT_BINS, dtype=np.float32)
        self.smooth_levels = np.zeros(FFT_BINS, dtype=np.float32)
        self.global_level = 0.0
        self.frame = 0
        self.lock = threading.Lock()

        # Initialize style
        style_class = VISUALIZER_STYLES.get(style_name, ToricStyle)
        self.style = style_class(self, self.colors)

        # Set up OpenGL
        if transparent:
            gloo.set_clear_color(BG_COLOR_TRANSPARENT)
            # Enable blending for transparency
            gloo.set_state(blend=True, blend_func=("src_alpha", "one_minus_src_alpha"))
        else:
            gloo.set_clear_color(BG_COLOR)

        gloo.set_viewport(0, 0, *self.physical_size)

        # Timer for animation (60 FPS)
        self._timer = app.Timer(1.0 / 60, connect=self.on_timer, start=True)

    def on_resize(self, event):
        gloo.set_viewport(0, 0, *event.physical_size)

    def on_timer(self, event):
        self.frame += 1

        with self.lock:
            # Smooth the levels
            self.smooth_levels = self.smooth_levels * (1 - SMOOTHING) + self.levels * SMOOTHING

        # Update style
        self.style.update(self.smooth_levels, self.global_level, self.frame)
        self.update()

    def on_draw(self, event):
        if self.transparent:
            # Clear with transparent color and enable blending
            gloo.clear(color=True, depth=True)
            gloo.set_state(blend=True, blend_func=("src_alpha", "one_minus_src_alpha"))
        else:
            gloo.clear()
        self.style.draw()

    def update_audio(self, audio_chunk: bytes):
        """Update with new audio data"""
        try:
            data = np.frombuffer(audio_chunk, dtype=np.int16)
            if len(data) == 0:
                return

            # Calculate RMS for global level
            rms = np.sqrt(np.mean(data.astype(np.float32) ** 2)) / 8000
            rms = min(1.0, rms * 1.8)

            # FFT analysis
            fft_data = np.abs(np.fft.rfft(data))
            fft_size = len(fft_data)

            with self.lock:
                self.global_level = self.global_level * 0.7 + rms * 0.3

                # Map FFT bins to our visualization bins
                # Skip DC component (bin 0) which is always high
                for i in range(FFT_BINS):
                    # Start from bin 1 to skip DC component
                    freq_idx = 1 + int((i / FFT_BINS) * (fft_size - 1) * 0.7)
                    freq_idx = min(freq_idx, fft_size - 1)
                    level = fft_data[freq_idx] / 35000
                    level = min(1.0, level * 1.8)
                    self.levels[i] = self.levels[i] * 0.4 + level * 0.6

        except Exception:
            pass


class Visualizer:
    """Main visualizer class - manages the VisPy canvas in a separate thread"""

    def __init__(self):
        self.running = False
        self.thread = None
        self._ready = threading.Event()
        self.canvas = None
        self._stop_event = threading.Event()

    def start(self):
        if self.running:
            return

        self.running = True
        self._ready.clear()
        self._stop_event.clear()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=3.0)

    def stop(self):
        self.running = False
        self._stop_event.set()

        if self.canvas:
            try:
                # Stop timer and close canvas safely
                if hasattr(self.canvas, "_timer") and self.canvas._timer:
                    self.canvas._timer.stop()
                self.canvas.close()
            except Exception:
                pass

        # Quit the app event loop
        try:
            app.quit()
        except Exception:
            pass

        if self.thread:
            self.thread.join(timeout=1.0)

    def update(self, audio_chunk: bytes):
        """Update visualizer with audio data"""
        if self.canvas and self.running:
            self.canvas.update_audio(audio_chunk)

    def _run(self):
        try:
            # Get style from config
            style_name = config.VISUALIZER_STYLE

            # Get size based on style
            size_map = {
                "minimalistic": (100, 100),
                "classic": (300, 150),
                "legacy": (300, 150),
                "toric": (200, 200),
                "terminal": (320, 200),
            }
            size = size_map.get(style_name, (200, 200))

            # Enable transparency for toric style
            use_transparent = style_name == "toric"

            # Get screen dimensions for positioning
            screen_w, screen_h = 1920, 1080  # Defaults

            # Try to detect screen size using pyglet
            try:
                import pyglet

                display = pyglet.canvas.get_display()
                screen = display.get_default_screen()
                screen_w = screen.width
                screen_h = screen.height
            except Exception:
                pass

            # Calculate position
            pos_x, pos_y = config.get_animation_position(screen_w, screen_h, size[0])

            # Create canvas with position and transparency
            self.canvas = VisPyVisualizerCanvas(
                style_name=style_name, size=size, transparent=use_transparent
            )

            # Set window position
            try:
                self.canvas.position = (pos_x, pos_y)
            except Exception:
                pass

            # Try to enable window transparency via pyglet
            if use_transparent:
                try:
                    import pyglet

                    # Get the native window from the canvas
                    native_window = self.canvas.native
                    if hasattr(native_window, "_window"):
                        # pyglet window
                        pyglet_window = native_window._window
                        # Set window to be transparent (works on compositing WMs)
                        if hasattr(pyglet_window, "set_transparent"):
                            pyglet_window.set_transparent(True)
                except Exception:
                    pass

            self.canvas.show()
            self._ready.set()

            # Run the VisPy event loop
            # Use process_events in a loop instead of app.run() for better control
            while self.running and not self._stop_event.is_set():
                try:
                    app.process_events()
                except Exception:
                    break
                self._stop_event.wait(timeout=0.016)  # ~60fps

        except Exception as e:
            print(f"VisPy Visualizer error: {e}")
            import traceback

            if config.DEBUG:
                traceback.print_exc()
        finally:
            self._ready.set()


# Singleton instance
_visualizer = None


def get_visualizer() -> Visualizer:
    """Get the global visualizer instance"""
    global _visualizer
    if _visualizer is None:
        _visualizer = Visualizer()
    return _visualizer
