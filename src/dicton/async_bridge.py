"""Async bridge for running coroutines from synchronous code.

This module provides a persistent asyncio event loop in a dedicated thread,
enabling synchronous code to submit coroutines without blocking.

Problem solved:
    The previous implementation created a new event loop for each streaming
    session, which caused issues with cleanup and resource management.

Architecture:
    +------------------+         +----------------------+
    | MAIN THREAD      |         | ASYNC THREAD         |
    |                  |         |                      |
    | submit(coro)     |-------->| asyncio event loop   |
    |     |            |         |   - run_forever()    |
    |     v            |         |   - handle coroutines|
    | Future.result()  |<--------|   - return results   |
    |                  |         |                      |
    +------------------+         +----------------------+

Usage:
    bridge = get_async_bridge()  # Singleton

    # Submit a coroutine from sync code
    future = bridge.submit(my_coroutine())

    # Wait for result (blocks calling thread, not event loop)
    result = future.result(timeout=30)
"""

import asyncio
import atexit
import threading
from concurrent.futures import Future
from typing import Any, Coroutine


class AsyncBridge:
    """Bridge for running async code from synchronous contexts.

    Maintains a persistent asyncio event loop in a dedicated thread,
    allowing coroutines to be submitted from any thread.

    Features:
        - Single persistent event loop (no per-call overhead)
        - Thread-safe coroutine submission
        - Proper cleanup on shutdown
        - Reusable across multiple streaming sessions

    Example:
        bridge = AsyncBridge()
        bridge.start()

        # Submit coroutine from sync code
        future = bridge.submit(some_async_function())
        result = future.result(timeout=30)

        bridge.stop()
    """

    def __init__(self):
        """Initialize async bridge (not yet started)."""
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._started = threading.Event()
        self._lock = threading.Lock()

    def _run_loop(self):
        """Run the event loop in the dedicated thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        # Signal that loop is ready
        self._started.set()

        try:
            self._loop.run_forever()
        finally:
            # Cleanup pending tasks
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()

            # Wait for tasks to be cancelled
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )

            self._loop.close()
            self._loop = None

    def start(self) -> None:
        """Start the async bridge.

        Creates a dedicated thread with a persistent event loop.
        Safe to call multiple times (no-op if already started).
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._started.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="AsyncBridge-EventLoop",
                daemon=True,
            )
            self._thread.start()

            # Wait for loop to be ready
            self._started.wait(timeout=5.0)
            if not self._started.is_set():
                raise RuntimeError("Failed to start async bridge event loop")

    def stop(self) -> None:
        """Stop the async bridge.

        Stops the event loop and joins the thread.
        Safe to call multiple times.
        """
        with self._lock:
            if self._loop is not None:
                # Schedule loop stop from the loop's thread
                self._loop.call_soon_threadsafe(self._loop.stop)

            if self._thread is not None:
                self._thread.join(timeout=5.0)
                self._thread = None

            self._started.clear()

    def submit(self, coro: Coroutine[Any, Any, Any]) -> Future:
        """Submit a coroutine for execution in the async bridge.

        Thread-safe method to run a coroutine in the persistent event loop.

        Args:
            coro: Coroutine to execute

        Returns:
            Future that will contain the result or exception

        Raises:
            RuntimeError: If bridge is not started
        """
        if self._loop is None:
            raise RuntimeError("AsyncBridge not started. Call start() first.")

        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    @property
    def is_running(self) -> bool:
        """Check if the async bridge is running."""
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._loop is not None
            and self._loop.is_running()
        )

    def run_sync(self, coro: Coroutine[Any, Any, Any], timeout: float | None = None) -> Any:
        """Submit a coroutine and wait for the result synchronously.

        Convenience method that combines submit() and Future.result().

        Args:
            coro: Coroutine to execute
            timeout: Maximum time to wait for result (None = no timeout)

        Returns:
            Result of the coroutine

        Raises:
            RuntimeError: If bridge is not started
            TimeoutError: If timeout expires
            Exception: Any exception raised by the coroutine
        """
        future = self.submit(coro)
        return future.result(timeout=timeout)


# Module-level singleton
_bridge_instance: AsyncBridge | None = None
_bridge_lock = threading.Lock()


def get_async_bridge() -> AsyncBridge:
    """Get the singleton AsyncBridge instance.

    Creates and starts the bridge on first call.
    Subsequent calls return the same instance.

    Returns:
        The singleton AsyncBridge instance
    """
    global _bridge_instance

    with _bridge_lock:
        if _bridge_instance is None:
            _bridge_instance = AsyncBridge()
            _bridge_instance.start()

            # Register cleanup on exit
            atexit.register(_cleanup_bridge)

        elif not _bridge_instance.is_running:
            # Restart if stopped
            _bridge_instance.start()

        return _bridge_instance


def _cleanup_bridge():
    """Cleanup function called at exit."""
    global _bridge_instance
    if _bridge_instance is not None:
        try:
            _bridge_instance.stop()
        except Exception:
            pass
        _bridge_instance = None


def reset_async_bridge():
    """Reset the singleton bridge (for testing).

    Stops the current bridge and clears the singleton.
    Next call to get_async_bridge() will create a new instance.
    """
    global _bridge_instance

    with _bridge_lock:
        if _bridge_instance is not None:
            try:
                _bridge_instance.stop()
            except Exception:
                pass
            _bridge_instance = None
