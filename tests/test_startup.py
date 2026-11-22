"""Tests for weekly rollover scheduler ownership in the application lifespan."""

from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient

from chore_tracker.main import app


class _FakeScheduler:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.stopped = threading.Event()

    async def run_forever(self) -> None:
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.set()


def test_lifespan_starts_and_stops_the_weekly_rollover_scheduler(monkeypatch) -> None:
    scheduler = _FakeScheduler()
    monkeypatch.setattr(
        app.state,
        "settings",
        SimpleNamespace(weekly_rollover_enabled=True),
    )
    monkeypatch.setattr(
        app.state,
        "weekly_rollover_scheduler_factory",
        lambda _settings: scheduler,
    )

    with TestClient(app) as client:
        assert scheduler.started.wait(timeout=5)
        assert client.get("/health/live").status_code == 200

    assert scheduler.stopped.wait(timeout=5)


def test_lifespan_skips_the_scheduler_when_disabled(monkeypatch) -> None:
    def unexpected_factory(_settings):
        raise AssertionError("The scheduler should not start when disabled")

    monkeypatch.setattr(
        app.state,
        "settings",
        SimpleNamespace(weekly_rollover_enabled=False),
    )
    monkeypatch.setattr(
        app.state,
        "weekly_rollover_scheduler_factory",
        unexpected_factory,
    )

    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
