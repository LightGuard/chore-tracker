"""Tests for application configuration loading and validation."""

from datetime import time
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from chore_tracker.config import EmailTransport, Environment, Settings

PRODUCTION_ORIGIN = "https://chores.example.test"


def production_settings(**overrides: object) -> Settings:
    """Build valid production settings, allowing individual fields to vary."""
    return Settings(
        _env_file=None,
        _secrets_dir=None,
        environment=Environment.PRODUCTION,
        app_host="0.0.0.0",
        app_origin=PRODUCTION_ORIGIN,
        passkey_rp_id="chores.example.test",
        passkey_origin=PRODUCTION_ORIGIN,
        **overrides,
    )


def test_development_defaults_are_safe_and_explicit() -> None:
    settings = Settings(_env_file=None, _secrets_dir=None)

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.app_host == "127.0.0.1"
    assert settings.app_origin == "http://localhost:5173"
    assert settings.database_path == Path("./data/chore-tracker.db")
    assert settings.email_transport is None
    assert settings.email_delivery_configured is False
    assert settings.report_timezone == "America/Denver"
    assert settings.report_delivery_time == time(3, 0)
    assert settings.weekly_rollover_enabled is True


def test_environment_values_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHORE_TRACKER_APP_PORT", "9000")
    monkeypatch.setenv("CHORE_TRACKER_DATABASE_PATH", "/data/chore-tracker.db")
    monkeypatch.setenv("CHORE_TRACKER_REPORT_DELIVERY_TIME", "04:15")
    monkeypatch.setenv("CHORE_TRACKER_WEEKLY_ROLLOVER_ENABLED", "false")
    monkeypatch.setenv("CHORE_TRACKER_EMAIL_TRANSPORT", "console")

    settings = Settings(_env_file=None, _secrets_dir=None)

    assert settings.app_port == 9000
    assert settings.database_path == Path("/data/chore-tracker.db")
    assert settings.report_delivery_time == time(4, 15)
    assert settings.weekly_rollover_enabled is False
    assert settings.email_transport is EmailTransport.CONSOLE


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


def test_smtp_settings_enable_email_without_an_explicit_transport() -> None:
    settings = Settings(
        _env_file=None,
        _secrets_dir=None,
        smtp_host="mail.example.test",
        email_from_address="chores@example.test",
    )

    assert settings.email_transport is EmailTransport.SMTP
    assert settings.email_delivery_configured is True


def test_explicit_smtp_transport_requires_host_and_sender() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            _secrets_dir=None,
            email_transport=EmailTransport.SMTP,
        )

    message = str(error.value)
    assert "SMTP email delivery is incomplete" in message
    assert "CHORE_TRACKER_SMTP_HOST" in message
    assert "CHORE_TRACKER_EMAIL_FROM_ADDRESS" in message
    assert "run without email" in message


def test_incomplete_smtp_settings_fail_with_an_actionable_diagnostic() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            _secrets_dir=None,
            smtp_host="mail.example.test",
        )

    message = str(error.value)
    assert "CHORE_TRACKER_EMAIL_FROM_ADDRESS" in message
    assert "Remove the SMTP settings" in message


def test_console_transport_cannot_be_combined_with_smtp_settings() -> None:
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            _secrets_dir=None,
            email_transport=EmailTransport.CONSOLE,
            smtp_host="mail.example.test",
        )

    message = str(error.value)
    assert "CHORE_TRACKER_EMAIL_TRANSPORT=console" in message
    assert "CHORE_TRACKER_SMTP_HOST" in message
    assert "CHORE_TRACKER_EMAIL_TRANSPORT=smtp" in message


def test_smtp_port_and_starttls_alone_do_not_enable_email() -> None:
    settings = Settings(
        _env_file=None,
        _secrets_dir=None,
        smtp_port=2525,
        smtp_starttls=False,
    )

    assert settings.email_transport is None
    assert settings.email_delivery_configured is False


def test_blank_email_environment_values_are_treated_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "CHORE_TRACKER_EMAIL_TRANSPORT",
        "CHORE_TRACKER_EMAIL_FROM_ADDRESS",
        "CHORE_TRACKER_SMTP_HOST",
        "CHORE_TRACKER_SMTP_USERNAME",
        "CHORE_TRACKER_SMTP_PASSWORD",
        "CHORE_TRACKER_SMTP_PASSWORD_FILE",
    ):
        monkeypatch.setenv(name, "")

    settings = Settings(_env_file=None, _secrets_dir=None)

    assert settings.email_transport is None
    assert settings.email_delivery_configured is False
    assert settings.email_from_address is None
    assert settings.smtp_host is None
    assert settings.smtp_username is None
    assert settings.smtp_password is None
    assert settings.smtp_password_file is None


def test_mounted_secret_file_is_loaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "smtp_password").write_text("test-secret-value", encoding="utf-8")
    monkeypatch.setenv(
        "CHORE_TRACKER_SMTP_PASSWORD_FILE", str(tmp_path / "smtp_password")
    )
    settings = Settings(
        _env_file=None,
        smtp_host="mail.example.test",
        email_from_address="chores@example.test",
        smtp_username="mailer",
    )

    assert settings.email_transport is EmailTransport.SMTP
    assert settings.smtp_password is not None
    assert settings.smtp_password.get_secret_value() == "test-secret-value"
    assert "test-secret-value" not in repr(settings)
    assert "test-secret-value" not in str(settings)


def test_unreadable_password_file_is_reported_actionably(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "CHORE_TRACKER_SMTP_PASSWORD_FILE", str(tmp_path / "missing-password")
    )

    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None,
            smtp_host="mail.example.test",
            email_from_address="chores@example.test",
        )

    message = str(error.value)
    assert "CHORE_TRACKER_SMTP_PASSWORD_FILE" in message
    assert "could not be read" in message


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
    with pytest.raises(ValidationError, match="SMTP authentication is incomplete"):
        Settings(
            _env_file=None,
            _secrets_dir=None,
            email_transport=EmailTransport.SMTP,
            smtp_host="mail.example.test",
            email_from_address="chores@example.test",
            smtp_username="mailer",
        )


def test_smtp_password_requires_username() -> None:
    with pytest.raises(ValidationError, match="SMTP authentication is incomplete"):
        Settings(
            _env_file=None,
            _secrets_dir=None,
            email_transport=EmailTransport.SMTP,
            smtp_host="mail.example.test",
            email_from_address="chores@example.test",
            smtp_password=SecretStr("test-secret-value"),
        )


def test_production_rejects_development_defaults() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(_env_file=None, _secrets_dir=None, environment=Environment.PRODUCTION)


def test_production_accepts_secure_configuration_without_email() -> None:
    settings = production_settings()

    assert settings.environment is Environment.PRODUCTION
    assert settings.email_transport is None
    assert settings.email_delivery_configured is False


def test_production_accepts_auto_enabled_smtp() -> None:
    settings = production_settings(
        smtp_host="mail.example.test",
        email_from_address="chores@example.test",
    )

    assert settings.email_transport is EmailTransport.SMTP


def test_production_accepts_explicit_console_transport_without_smtp_settings() -> None:
    settings = production_settings(email_transport=EmailTransport.CONSOLE)

    assert settings.email_transport is EmailTransport.CONSOLE


def test_production_requires_https_and_non_local_passkey_domain() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        Settings(
            _env_file=None,
            _secrets_dir=None,
            environment=Environment.PRODUCTION,
            passkey_rp_id="example.test",
            smtp_host="mail.example.test",
            email_from_address="chores@example.test",
        )
