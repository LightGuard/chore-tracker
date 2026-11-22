"""Async loop that executes the durable weekly rollover schedule."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from chore_tracker.application.services.weekly_rollover import (
    WeeklyRolloverResult,
)

logger = logging.getLogger(__name__)
DEFAULT_RETRY_DELAY_SECONDS = 300.0


class WeeklyRolloverRunner(Protocol):
    """Scheduling operations required by the background loop."""

    def run_due(
        self, now: datetime | None = None
    ) -> tuple[WeeklyRolloverResult, ...]: ...

    def next_run_at(self, now: datetime | None = None) -> datetime: ...


class WeeklyRolloverScheduler:
    """Run due rollovers on startup and at each configured Monday time.

    Durable progress belongs to the rollover service; this loop only decides
    when to call it. A failed attempt is retried after a short delay instead of
    waiting a full week, and the next application startup always checks for
    missed weeks again.
    """

    def __init__(
        self,
        rollover: WeeklyRolloverRunner,
        *,
        clock: Callable[[], datetime] | None = None,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
    ) -> None:
        self._rollover = rollover
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep or asyncio.sleep
        self._retry_delay_seconds = retry_delay_seconds

    async def run_forever(self) -> None:
        logger.info("Weekly rollover scheduler started")
        try:
            while True:
                now = self._clock()
                try:
                    self._rollover.run_due(now)
                except Exception:
                    logger.exception(
                        "Weekly rollover attempt failed; retrying in %.0f seconds",
                        self._retry_delay_seconds,
                    )
                    await self._sleep(self._retry_delay_seconds)
                    continue

                delay = max(
                    0.0, (self._rollover.next_run_at(now) - now).total_seconds()
                )
                await self._sleep(delay)
        except asyncio.CancelledError:
            logger.info("Weekly rollover scheduler stopped")
            raise
