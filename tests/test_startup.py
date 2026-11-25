"""Tests for startup diagnostics and weekly rollover scheduling ownership."""

from __future__ import annotations

import asyncio
import logging
import threading
from types import SimpleNamespace

from fastapi.testclient import TestClient
from pydantic import SecretStr

from chore_tracker.config import EmailTransport, Environment, Settings
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


def _scheduler_settings(*, weekly_rollover_enabled: bool) -> SimpleNamespace:
    """Return the settings fields the lifespan scheduler path reads."""
    return SimpleNamespace(
        weekly_rollover_enabled=weekly_rollover_enabled,
        email_transport=None,
        smtp_host=None,
        smtp_port=587,
        smtp_starttls=True,
    )


def test_lifespan_starts_and_stops_the_weekly_rollover_scheduler(monkeypatch) -> None:
    scheduler = _FakeScheduler()
    monkeypatch.setattr(
        app.state,
        "settings",
        _scheduler_settings(weekly_rollover_enabled=True),
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
        _scheduler_settings(weekly_rollover_enabled=False),
    )
    monkeypatch.setattr(
        app.state,
        "weekly_rollover_scheduler_factory",
        unexpected_factory,
    )

    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200


def test_production_startup_does_not_require_email_configuration(
    monkeypatch, caplog
) -> None:
    settings = Settings(
        _env_file=None,
        _secrets_dir=None,
        environment=Environment.PRODUCTION,
        app_host="0.0.0.0",
        app_origin="https://chores.example.test",
        passkey_origin="https://chores.example.test",
        passkey_rp_id="chores.example.test",
        weekly_rollover_enabled=False,
    )
    monkeypatch.setattr(app.state, "settings", settings)

    with caplog.at_level(logging.INFO), TestClient(app) as client:
        assert client.get("/health/live").status_code == 200

    assert settings.email_transport is None
    assert settings.email_delivery_configured is False
    assert "Email delivery is disabled" in caplog.text


def test_startup_logs_enabled_smtp_configuration_without_secrets(
    monkeypatch, caplog
) -> None:
    settings = Settings(
        _env_file=None,
        _secrets_dir=None,
        smtp_host="mail.example.test",
        smtp_port=2525,
        email_from_address="chores@example.test",
        smtp_username="mailer",
        smtp_password=SecretStr("test-secret-value"),
        weekly_rollover_enabled=False,
    )
    monkeypatch.setattr(app.state, "settings", settings)

    with caplog.at_level(logging.INFO), TestClient(app) as client:
        assert client.get("/health/live").status_code == 200

    assert settings.email_transport is EmailTransport.SMTP
    assert "Email delivery is enabled with SMTP host mail.example.test port 2525" in (
        caplog.text
    )
    assert "test-secret-value" not in caplog.text


def test_startup_logs_console_email_configuration(monkeypatch, caplog) -> None:
    settings = Settings(
        _env_file=None,
        _secrets_dir=None,
        email_transport=EmailTransport.CONSOLE,
        weekly_rollover_enabled=False,
    )
    monkeypatch.setattr(app.state, "settings", settings)

    with caplog.at_level(logging.INFO), TestClient(app) as client:
        assert client.get("/health/live").status_code == 200

    assert "console transport" in caplog.text
