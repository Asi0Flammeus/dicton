"""Tiny pygame waveform visualizer."""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field


@dataclass(slots=True)
class Visualizer:
    width: int = 400
    height: int = 100
    frames: queue.Queue[bytes | None] = field(default_factory=lambda: queue.Queue(maxsize=8))
    _thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def feed(self, pcm16: bytes) -> None:
        try:
            self.frames.put_nowait(pcm16)
        except queue.Full:
            pass

    def stop(self) -> None:
        self.frames.put(None)

    def _run(self) -> None:
        try:
            import audioop

            import pygame
        except ImportError:
            return
        pygame.init()
        screen = pygame.display.set_mode((self.width, self.height))
        pygame.display.set_caption("dicton REC")
        clock = pygame.time.Clock()
        last_rms = 0
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            try:
                frame = self.frames.get_nowait()
                if frame is None:
                    running = False
                else:
                    last_rms = min(self.height, audioop.rms(frame, 2) * self.height // 32768)
            except queue.Empty:
                pass
            screen.fill((20, 16, 12))
            pygame.draw.rect(
                screen, (161, 74, 40), (10, self.height - last_rms, self.width - 20, last_rms)
            )
            pygame.display.flip()
            clock.tick(30)
        pygame.quit()
