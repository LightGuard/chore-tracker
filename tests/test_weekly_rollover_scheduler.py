"""Tests for the background weekly rollover scheduler loop."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from chore_tracker.application.services.weekly_rollover import WeeklyRolloverResult
from chore_tracker.application.services.weekly_rollover_scheduler import (
    DEFAULT_RETRY_DELAY_SECONDS,
    MAX_SLEEP_SECONDS,
    WeeklyRolloverScheduler,
)

NOW = datetime(2026, 11, 23, 3, 0, tzinfo=UTC)


class _FakeRollover:
    def __init__(
        self,
        *,
        fail: bool = False,
        next_delay: timedelta = timedelta(days=7),
    ) -> None:
        self._fail = fail
        self._next_delay = next_delay
        self.calls: list[datetime | None] = []

    def run_due(self, now: datetime | None = None) -> tuple[WeeklyRolloverResult, ...]:
        self.calls.append(now)
        if self._fail:
            raise RuntimeError("injected rollover failure")
        return ()

    def next_run_at(self, now: datetime | None = None) -> datetime:
        assert now is not None
        return now + self._next_delay


def test_scheduler_runs_on_startup_then_sleeps_until_the_next_run() -> None:
    rollover = _FakeRollover(next_delay=timedelta(minutes=30))
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
    assert delays == [30 * 60]


def test_scheduler_rechecks_the_clock_at_least_hourly() -> None:
    rollover = _FakeRollover(next_delay=timedelta(days=7))
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

    assert delays == [MAX_SLEEP_SECONDS]


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
