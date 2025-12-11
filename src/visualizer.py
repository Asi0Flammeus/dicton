"""Elegant circular audio visualizer - donut waveform with dark background"""
import os
import math
import threading

os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
os.environ['SDL_VIDEO_X11_NET_WM_BYPASS_COMPOSITOR'] = '0'

import numpy as np

# Color palette
ORANGE = (255, 120, 40)
ORANGE_MID = (220, 80, 20)
ORANGE_DIM = (120, 50, 15)
ORANGE_GLOW = (255, 160, 60)
BG_COLOR = (20, 20, 24)

SIZE = 160
WAVE_POINTS = 90


class Visualizer:
    """Circular donut audio visualizer"""

    def __init__(self):
        self.running = False
        self.thread = None
        self.levels = np.zeros(WAVE_POINTS)
        self.smooth_levels = np.zeros(WAVE_POINTS)
        self.lock = threading.Lock()
        self._ready = threading.Event()
        self.frame = 0
        self.global_level = 0.0

    def start(self):
        if self.running:
            return

        self.running = True
        self.levels = np.zeros(WAVE_POINTS)
        self.smooth_levels = np.zeros(WAVE_POINTS)
        self.frame = 0
        self.global_level = 0.0
        self._ready.clear()

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self._ready.wait(timeout=2.0)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)

    def update(self, audio_chunk: bytes):
        if not self.running:
            return

        try:
            data = np.frombuffer(audio_chunk, dtype=np.int16)
            if len(data) == 0:
                return

            rms = np.sqrt(np.mean(data.astype(np.float32) ** 2)) / 8000
            rms = min(1.0, rms * 1.8)

            fft_data = np.abs(np.fft.rfft(data))
            fft_size = len(fft_data)

            with self.lock:
                self.global_level = self.global_level * 0.7 + rms * 0.3

                for i in range(WAVE_POINTS):
                    freq_idx = int((i / WAVE_POINTS) * fft_size * 0.7)
                    freq_idx = min(freq_idx, fft_size - 1)
                    level = fft_data[freq_idx] / 35000
                    level = min(1.0, level * 1.8)
                    self.levels[i] = self.levels[i] * 0.4 + level * 0.6

        except Exception:
            pass

    def _run(self):
        try:
            import pygame
            pygame.init()

            # Position at bottom center
            info = pygame.display.Info()
            screen_w, screen_h = info.current_w, info.current_h
            pos_x = (screen_w - SIZE) // 2
            pos_y = screen_h - SIZE - 50
            os.environ['SDL_VIDEO_WINDOW_POS'] = f'{pos_x},{pos_y}'

            screen = pygame.display.set_mode((SIZE, SIZE), pygame.NOFRAME)
            pygame.display.set_caption("P2W")

            # Try to set opacity
            try:
                from pygame._sdl2.video import Window
                window = Window.from_display_module()
                window.opacity = 0.92
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
                self.frame += 1
                clock.tick(60)

            pygame.quit()

        except Exception as e:
            print(f"Visualizer error: {e}")
            self._ready.set()

    def _draw(self, screen, pygame):
        screen.fill(BG_COLOR)

        center_x = SIZE // 2
        center_y = SIZE // 2

        outer_radius = SIZE // 2 - 10
        inner_radius = 25
        mid_radius = (outer_radius + inner_radius) // 2
        max_amplitude = (outer_radius - inner_radius) // 2 - 2

        with self.lock:
            levels_copy = self.levels.copy()
            global_level = self.global_level

        for i in range(WAVE_POINTS):
            self.smooth_levels[i] = self.smooth_levels[i] * 0.82 + levels_copy[i] * 0.18

        # Calculate wave points
        outer_points = []
        inner_points = []

        for i in range(WAVE_POINTS):
            angle = (i / WAVE_POINTS) * 2 * math.pi
            level = self.smooth_levels[i]

            wave_phase = self.frame * 0.05
            wave1 = math.sin(wave_phase + angle * 3) * 0.15
            wave2 = math.sin(wave_phase * 0.7 + angle * 5) * 0.1
            wave3 = math.sin(wave_phase * 1.2 + angle * 2) * 0.08

            base_wave = (wave1 + wave2 + wave3) * max_amplitude * 0.3
            amplitude = level * max_amplitude * 0.9 + base_wave
            amplitude *= (0.4 + global_level * 0.9)

            outer_r = mid_radius + amplitude
            outer_points.append((
                center_x + math.cos(angle) * outer_r,
                center_y + math.sin(angle) * outer_r
            ))

            inner_r = max(inner_radius, mid_radius - amplitude)
            inner_points.append((
                center_x + math.cos(angle) * inner_r,
                center_y + math.sin(angle) * inner_r
            ))

        # Draw glow
        if global_level > 0.05:
            glow_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            glow_alpha = int(60 + global_level * 80)

            glow_outer = []
            for i in range(WAVE_POINTS):
                angle = (i / WAVE_POINTS) * 2 * math.pi
                level = self.smooth_levels[i]
                wave = math.sin(self.frame * 0.05 + angle * 3) * 0.15
                amp = (level * max_amplitude * 0.9 + wave * max_amplitude * 0.3) * 1.2
                amp *= (0.4 + global_level * 0.9)
                r = mid_radius + amp
                glow_outer.append((center_x + math.cos(angle) * r, center_y + math.sin(angle) * r))

            pygame.draw.polygon(glow_surf, (*ORANGE_DIM, glow_alpha), glow_outer, width=5)
            screen.blit(glow_surf, (0, 0))

        # Draw filled donut
        if len(outer_points) > 2 and len(inner_points) > 2:
            donut_shape = outer_points + inner_points[::-1]
            pygame.draw.polygon(screen, ORANGE_MID, donut_shape)

        # Outer edge
        if len(outer_points) > 2:
            intensity = min(1.0, 0.5 + global_level * 0.6)
            line_color = (
                int(ORANGE_DIM[0] + (ORANGE[0] - ORANGE_DIM[0]) * intensity),
                int(ORANGE_DIM[1] + (ORANGE[1] - ORANGE_DIM[1]) * intensity),
                int(ORANGE_DIM[2] + (ORANGE[2] - ORANGE_DIM[2]) * intensity)
            )
            pygame.draw.polygon(screen, line_color, outer_points, width=2)

        # Inner edge
        if len(inner_points) > 2:
            pygame.draw.polygon(screen, ORANGE_DIM, inner_points, width=2)

        # Cut out center (draw circle with background color)
        pygame.draw.circle(screen, BG_COLOR, (center_x, center_y), inner_radius - 3)

        # Highlight
        if global_level > 0.2:
            highlight_surf = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
            pygame.draw.polygon(highlight_surf, (*ORANGE_GLOW, int(global_level * 180)), outer_points, width=1)
            screen.blit(highlight_surf, (0, 0))

        # Draw circular mask to make window appear round
        # Create mask surface
        mask = pygame.Surface((SIZE, SIZE), pygame.SRCALPHA)
        mask.fill((0, 0, 0, 255))
        pygame.draw.circle(mask, (0, 0, 0, 0), (center_x, center_y), SIZE // 2 - 2)

        # Apply mask - fill corners with very dark color
        corner_color = (10, 10, 12)
        # Top-left
        pygame.draw.polygon(screen, corner_color, [(0, 0), (SIZE//2, 0), (0, SIZE//2)])
        # Top-right
        pygame.draw.polygon(screen, corner_color, [(SIZE, 0), (SIZE//2, 0), (SIZE, SIZE//2)])
        # Bottom-left
        pygame.draw.polygon(screen, corner_color, [(0, SIZE), (SIZE//2, SIZE), (0, SIZE//2)])
        # Bottom-right
        pygame.draw.polygon(screen, corner_color, [(SIZE, SIZE), (SIZE//2, SIZE), (SIZE, SIZE//2)])

        # Draw outer circle to clean up
        pygame.draw.circle(screen, corner_color, (center_x, center_y), SIZE // 2, SIZE // 2 - outer_radius - 12)

        pygame.display.flip()


_visualizer = None


def get_visualizer() -> Visualizer:
    global _visualizer
    if _visualizer is None:
        _visualizer = Visualizer()
    return _visualizer
