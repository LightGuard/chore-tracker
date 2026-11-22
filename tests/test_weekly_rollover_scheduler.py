"""Tests for the background weekly rollover scheduler loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from chore_tracker.application.services.weekly_rollover import WeeklyRolloverResult
from chore_tracker.application.services.weekly_rollover_scheduler import (
    DEFAULT_RETRY_DELAY_SECONDS,
    WeeklyRolloverScheduler,
)

NOW = datetime(2026, 11, 23, 3, 0, tzinfo=UTC)


class _FakeRollover:
    def __init__(self, *, fail: bool = False) -> None:
        self._fail = fail
        self.calls: list[datetime | None] = []

    def run_due(self, now: datetime | None = None) -> tuple[WeeklyRolloverResult, ...]:
        self.calls.append(now)
        if self._fail:
            raise RuntimeError("injected rollover failure")
        return ()

    def next_run_at(self, now: datetime | None = None) -> datetime:
        assert now is not None
        return now + timedelta(days=7)


def test_scheduler_runs_on_startup_then_sleeps_until_next_monday() -> None:
    rollover = _FakeRollover()
    delays = []

    async def stop_after_sleep(seconds: float) -> None:
        delays.append(seconds)
        raise asyncio.CancelledError

    scheduler = WeeklyRolloverScheduler(
        rollover,
        clock=lambda: NOW,
        sleep=stop_after_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scheduler.run_forever())

    assert rollover.calls == [NOW]
    assert delays == [7 * 24 * 60 * 60]


def test_scheduler_retries_failed_attempts_without_waiting_a_week() -> None:
    rollover = _FakeRollover(fail=True)
    delays = []

    async def stop_after_sleep(seconds: float) -> None:
        delays.append(seconds)
        raise asyncio.CancelledError

    scheduler = WeeklyRolloverScheduler(
        rollover,
        clock=lambda: NOW,
        sleep=stop_after_sleep,
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(scheduler.run_forever())

    assert rollover.calls == [NOW]
    assert delays == [DEFAULT_RETRY_DELAY_SECONDS]
