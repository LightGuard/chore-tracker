"""Tests for application configuration loading and validation."""

from datetime import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from chore_tracker.config import EmailTransport, Environment, Settings


def test_development_defaults_are_safe_and_explicit() -> None:
    settings = Settings(_env_file=None, _secrets_dir=None)

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.app_host == "127.0.0.1"
    assert settings.app_origin == "http://127.0.0.1:5173"
    assert settings.database_path == Path("./data/chore-tracker.db")
    assert settings.email_transport is EmailTransport.CONSOLE
    assert settings.report_timezone == "America/Denver"
    assert settings.report_delivery_time == time(3, 0)


def test_environment_values_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHORE_TRACKER_APP_PORT", "9000")
    monkeypatch.setenv("CHORE_TRACKER_DATABASE_PATH", "/data/chore-tracker.db")
    monkeypatch.setenv("CHORE_TRACKER_REPORT_DELIVERY_TIME", "04:15")

    settings = Settings(_env_file=None, _secrets_dir=None)

    assert settings.app_port == 9000
    assert settings.database_path == Path("/data/chore-tracker.db")
    assert settings.report_delivery_time == time(4, 15)


def test_invalid_port_is_rejected_without_echoing_input() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, _secrets_dir=None, app_port=70000)

    assert "app_port" in str(error.value)
    assert "70000" not in str(error.value)


def test_invalid_bind_host_is_rejected() -> None:
    with pytest.raises(ValidationError, match="IP address or valid DNS"):
        Settings(_env_file=None, _secrets_dir=None, app_host="not a host")


def test_invalid_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError, match="valid IANA timezone"):
        Settings(_env_file=None, _secrets_dir=None, report_timezone="Not/A_Timezone")


def test_invalid_application_origin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="absolute HTTP or HTTPS"):
        Settings(_env_file=None, _secrets_dir=None, app_origin="localhost:5173/path")


def test_smtp_requires_host_and_sender() -> None:
    with pytest.raises(ValidationError, match="SMTP transport requires"):
        Settings(
            _env_file=None,
            _secrets_dir=None,
            email_transport=EmailTransport.SMTP,
        )


def test_mounted_secret_file_is_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "smtp_password").write_text("test-secret-value", encoding="utf-8")
    monkeypatch.setenv(
        "CHORE_TRACKER_SMTP_PASSWORD_FILE", str(tmp_path / "smtp_password")
    )
    settings = Settings(
        _env_file=None,
        email_transport=EmailTransport.SMTP,
        smtp_host="mail.example.test",
        email_from_address="chores@example.test",
        smtp_username="mailer",
    )

    assert settings.smtp_password is not None
    assert settings.smtp_password.get_secret_value() == "test-secret-value"
    assert "test-secret-value" not in repr(settings)
    assert "test-secret-value" not in str(settings)


def test_secret_values_are_not_echoed_in_validation_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "do-not-log-this-value"
    monkeypatch.setenv("CHORE_TRACKER_EMAIL_TRANSPORT", "smtp")
    monkeypatch.setenv("CHORE_TRACKER_SMTP_PASSWORD", secret)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, _secrets_dir=None)

    assert secret not in str(error.value)


def test_smtp_username_requires_password() -> None:
    with pytest.raises(ValidationError, match="configured together"):
        Settings(
            _env_file=None,
            _secrets_dir=None,
            email_transport=EmailTransport.SMTP,
            smtp_host="mail.example.test",
            email_from_address="chores@example.test",
            smtp_username="mailer",
        )


def test_production_rejects_development_defaults() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(_env_file=None, _secrets_dir=None, environment=Environment.PRODUCTION)


def test_production_accepts_explicit_secure_configuration() -> None:
    settings = Settings(
        _env_file=None,
        _secrets_dir=None,
        environment=Environment.PRODUCTION,
        app_host="0.0.0.0",
        app_origin="https://chores.example.test",
        passkey_rp_id="chores.example.test",
        passkey_origin="https://chores.example.test",
        email_transport=EmailTransport.SMTP,
        smtp_host="mail.example.test",
        email_from_address="chores@example.test",
    )

    assert settings.environment is Environment.PRODUCTION


def test_production_requires_https_and_non_local_passkey_domain() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            _env_file=None,
            _secrets_dir=None,
            environment=Environment.PRODUCTION,
            passkey_rp_id="example.test",
            email_transport=EmailTransport.SMTP,
            smtp_host="mail.example.test",
            email_from_address="chores@example.test",
        )
