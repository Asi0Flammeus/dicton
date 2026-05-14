"""Live audio visualizer — pygame waveform on the main thread.

The recorder thread pushes int16 frames via `push_frame`; the main thread
pulls them in a tight loop and redraws. SDL on macOS requires the event/
window loop to run on the main thread, hence pygame in the foreground.
"""

from __future__ import annotations

import contextlib
import math
import queue
import threading

import numpy as np

WIN_W, WIN_H = 480, 120
BG = (43, 34, 23)
FG = (235, 227, 210)
ACCENT = (161, 74, 40)
ACCENT_GREEN = (61, 90, 61)


class Visualizer:
    def __init__(self) -> None:
        self._frames: queue.Queue[np.ndarray] = queue.Queue(maxsize=128)
        self._state = "idle"  # idle | recording | processing
        self._stop = threading.Event()
        self._level = 0.0
        self._waveform = np.zeros(WIN_W, dtype=np.float32)

    def push_frame(self, frame: np.ndarray) -> None:
        with contextlib.suppress(queue.Full):
            self._frames.put_nowait(frame)

    def set_state(self, state: str) -> None:
        self._state = state

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        """Main-thread loop; returns when stop() is set."""
        import os

        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        import pygame

        pygame.init()
        pygame.display.set_caption("dicton")
        screen = pygame.display.set_mode((WIN_W, WIN_H), pygame.NOFRAME)
        font = pygame.font.SysFont("monospace", 14, bold=True)
        clock = pygame.time.Clock()

        while not self._stop.is_set():
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self._stop.set()

            self._drain_frames()
            screen.fill(BG)
            self._draw_waveform(pygame, screen)
            self._draw_status(pygame, screen, font)
            pygame.display.flip()
            clock.tick(60)

        pygame.quit()

    def _drain_frames(self) -> None:
        latest = None
        while True:
            try:
                latest = self._frames.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            self._waveform *= 0.92
            self._level *= 0.92
            return
        normalised = latest.astype(np.float32) / 32768.0
        if normalised.size >= WIN_W:
            step = normalised.size // WIN_W
            self._waveform = normalised[: step * WIN_W : step][:WIN_W]
        else:
            self._waveform = np.roll(self._waveform, -normalised.size)
            self._waveform[-normalised.size :] = normalised
        self._level = float(np.sqrt(np.mean(normalised * normalised)))

    def _draw_waveform(self, pygame, screen) -> None:
        mid = WIN_H // 2
        color = ACCENT if self._state == "recording" else ACCENT_GREEN
        points = [(x, mid + int(self._waveform[x] * (WIN_H * 0.4))) for x in range(WIN_W)]
        if len(points) > 1:
            pygame.draw.lines(screen, color, False, points, 1)
        bar_w = int(min(self._level * 4, 1.0) * (WIN_W - 24))
        pygame.draw.rect(screen, color, (12, WIN_H - 14, bar_w, 4))

    def _draw_status(self, pygame, screen, font) -> None:
        label = {
            "recording": "REC",
            "processing": "…",
            "idle": "•",
        }.get(self._state, self._state)
        color = ACCENT if self._state == "recording" else FG
        text = font.render(label, True, color)
        screen.blit(text, (12, 8))


def run_in_background(viz: Visualizer) -> threading.Thread:
    """Convenience: only safe on Linux/Windows. macOS must call viz.run() on main."""
    t = threading.Thread(target=viz.run, daemon=True)
    t.start()
    return t


_ = math  # keep import for future bar smoothing
