from __future__ import annotations

import logging

import httpx
import pytest

from dicton.async_lifecycle import AsyncLoopRunner


async def _return_value(value: int) -> int:
    return value


async def _raise_value_error() -> None:
    raise ValueError("scheduled transition failed")


def test_runner_submits_coroutine_and_closes_client() -> None:
    runner = AsyncLoopRunner(lambda: httpx.AsyncClient(http2=True, http1=True))
    runner.start()

    try:
        assert runner.is_running
        assert runner.client is not None
        future = runner.submit(_return_value(7))
        assert future.result(timeout=2) == 7
    finally:
        runner.close(timeout=2)

    assert not runner.is_running


def test_runner_logs_unobserved_coroutine_exception(caplog: pytest.LogCaptureFixture) -> None:
    runner = AsyncLoopRunner(lambda: httpx.AsyncClient(http2=True, http1=True))
    runner.start()

    try:
        with caplog.at_level(logging.ERROR, logger="dicton"):
            future = runner.submit(_raise_value_error())
            with pytest.raises(ValueError, match="scheduled transition failed"):
                future.result(timeout=2)
            assert "async task failed" in caplog.text
    finally:
        runner.close(timeout=2)
