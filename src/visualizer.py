"""Minimal audio visualizer - transparent with orange accent, symmetrical"""
import os
import sys
import threading

# Suppress pygame messages before import
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR'] = '0'

import numpy as np

# Colors
BLACK = (0, 0, 0)
ORANGE = (188, 82, 21)  # #BC5215
ORANGE_DIM = (94, 41, 10)
ORANGE_GLOW = (255, 120, 40)
TRANSPARENT = (0, 0, 0, 0)

# Window settings
WIDTH = 500
HEIGHT = 160
BAR_COUNT = 40
BAR_GAP = 3
CORNER_RADIUS = 20


class Visualizer:
    """Audio visualizer window using pygame"""

    def __init__(self):
        self.running = False
        self.thread = None
        self.levels = np.zeros(BAR_COUNT)
        self.peak_levels = np.zeros(BAR_COUNT)
        self.lock = threading.Lock()
        self._ready = threading.Event()

    def start(self):
        """Start visualizer in separate thread"""
        if self.running:
            return

        self.running = True
        self.levels = np.zeros(BAR_COUNT)
        self.peak_levels = np.zeros(BAR_COUNT)
        self._ready.clear()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=2.0)

    def stop(self):
        """Stop visualizer"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def update(self, audio_chunk: bytes):
        """Update with new audio data"""
        if not self.running:
            return

        try:
            data = np.frombuffer(audio_chunk, dtype=np.int16)
            if len(data) == 0:
                return

            chunk_size = max(1, len(data) // BAR_COUNT)

            with self.lock:
                for i in range(BAR_COUNT):
                    start = i * chunk_size
                    end = min(start + chunk_size, len(data))
                    if start < len(data):
                        chunk = data[start:end]
                        level = np.sqrt(np.mean(chunk.astype(np.float32) ** 2)) / 5000
                        self.levels[i] = self.levels[i] * 0.4 + min(1.0, level) * 0.6
        except Exception:
            pass

    def _run(self):
        """Main visualizer loop"""
        try:
            import pygame

            pygame.init()

            # Get screen info for centering
            info = pygame.display.Info()
            screen_w, screen_h = info.current_w, info.current_h
            pos_x = (screen_w - WIDTH) // 2
            pos_y = (screen_h - HEIGHT) // 2

            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{pos_x},{pos_y}'

            # Create window with transparency support
            screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.NOFRAME | pygame.SRCALPHA)
            pygame.display.set_caption("P2W")

            # Try to set window transparency (Linux/X11)
            try:
                from pygame._sdl2 import Window
                window = Window.from_display_module()
                window.opacity = 0.9
            except Exception:
                pass

            clock = pygame.time.Clock()
            self._ready.set()

            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                        break

                self._draw(screen, pygame)
                clock.tick(60)

            pygame.quit()

        except Exception as e:
            print(f"Visualizer error: {e}")
            self._ready.set()

    def _draw(self, screen, pygame):
        """Draw the visualizer with rounded corners and symmetry"""
        # Clear with semi-transparent black
        screen.fill((10, 10, 10))

        bar_width = (WIDTH - (BAR_COUNT + 1) * BAR_GAP) // BAR_COUNT
        center_y = HEIGHT // 2
        max_bar_height = (HEIGHT // 2) - 15

        with self.lock:
            levels_copy = self.levels.copy()
            peaks_copy = self.peak_levels.copy()

        for i in range(BAR_COUNT):
            level = levels_copy[i] * 0.90  # Decay
            self.levels[i] = level

            # Update peak
            if level > peaks_copy[i]:
                self.peak_levels[i] = level
            else:
                self.peak_levels[i] = peaks_copy[i] * 0.96

            peak = self.peak_levels[i]

            # Bar position (centered)
            x = BAR_GAP + i * (bar_width + BAR_GAP)
            bar_height = int(level * max_bar_height)

            if bar_height > 1:
                # Color intensity based on level
                intensity = min(1.0, level * 2)
                color = (
                    int(ORANGE_DIM[0] + (ORANGE[0] - ORANGE_DIM[0]) * intensity),
                    int(ORANGE_DIM[1] + (ORANGE[1] - ORANGE_DIM[1]) * intensity),
                    int(ORANGE_DIM[2] + (ORANGE[2] - ORANGE_DIM[2]) * intensity)
                )

                # Draw upper bar (going up from center)
                upper_rect = pygame.Rect(x, center_y - bar_height, bar_width, bar_height)
                pygame.draw.rect(screen, color, upper_rect, border_radius=2)

                # Draw lower bar (going down from center, mirrored)
                lower_rect = pygame.Rect(x, center_y, bar_width, bar_height)
                pygame.draw.rect(screen, color, lower_rect, border_radius=2)

                # Glow effect at peaks
                if bar_height > 3:
                    # Upper glow
                    pygame.draw.rect(screen, ORANGE_GLOW,
                                   (x, center_y - bar_height, bar_width, 2), border_radius=1)
                    # Lower glow
                    pygame.draw.rect(screen, ORANGE_GLOW,
                                   (x, center_y + bar_height - 2, bar_width, 2), border_radius=1)

            # Peak indicators
            if peak > 0.03:
                peak_h = int(peak * max_bar_height)
                # Upper peak
                pygame.draw.rect(screen, ORANGE, (x, center_y - peak_h - 3, bar_width, 2))
                # Lower peak
                pygame.draw.rect(screen, ORANGE, (x, center_y + peak_h + 1, bar_width, 2))

        # Center line accent
        pygame.draw.rect(screen, ORANGE_DIM, (10, center_y - 1, WIDTH - 20, 2), border_radius=1)

        # Rounded border
        pygame.draw.rect(screen, ORANGE_DIM, (0, 0, WIDTH, HEIGHT),
                        width=2, border_radius=CORNER_RADIUS)

        pygame.display.flip()


# Singleton
_visualizer = None


def get_visualizer() -> Visualizer:
    """Get or create visualizer instance"""
    global _visualizer
    if _visualizer is None:
        _visualizer = Visualizer()
    return _visualizer
