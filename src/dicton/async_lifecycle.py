"""Asyncio loop lifecycle owned by the dictation pipeline."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import httpx

log = logging.getLogger("dicton")

T = TypeVar("T")


class AsyncLoopRunner:
    """Runs one asyncio loop in one background thread and observes submitted tasks."""

    def __init__(self, client_factory: Callable[[], httpx.AsyncClient]) -> None:
        self._client_factory = client_factory
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._closed = threading.Event()
        self.client: httpx.AsyncClient | None = None

    @property
    def is_running(self) -> bool:
        return self._loop is not None and self._loop.is_running()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="dicton-async", daemon=False)
        self._thread.start()
        self._ready.wait()

    def submit(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        if self._loop is None:
            coro.close()
            raise RuntimeError("async loop is not started")
        return asyncio.run_coroutine_threadsafe(self._observe(coro), self._loop)

    def call(self, fn: Callable[..., T], *args: object) -> None:
        if self._loop is None:
            return
        self._loop.call_soon_threadsafe(fn, *args)

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)

    def close(self, *, timeout: float = 5.0) -> None:
        self.stop()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._closed.set()

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self.client = self._client_factory()
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            if self.client is not None:
                loop.run_until_complete(self.client.aclose())
            loop.close()
            self._loop = None

    @staticmethod
    async def _observe(coro: Coroutine[Any, Any, T]) -> T:
        try:
            return await coro
        except Exception:
            log.error("async task failed", exc_info=True)
            raise