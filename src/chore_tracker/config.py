"""Validated application configuration loaded from environment and secret files."""

from __future__ import annotations

import ipaddress
import re
from datetime import time
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported application environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class EmailTransport(StrEnum):
    """Supported initial email transports."""

    CONSOLE = "console"
    SMTP = "smtp"


class Settings(BaseSettings):
    """Runtime settings; secrets are never rendered in model representations."""

    model_config = SettingsConfigDict(
        env_prefix="CHORE_TRACKER_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: Environment = Environment.DEVELOPMENT
    app_host: str = Field(default="127.0.0.1", min_length=1)
    app_port: int = Field(default=8000, ge=1, le=65535)
    app_origin: str = "http://127.0.0.1:5173"

    database_path: Path = Path("./data/chore-tracker.db")

    admin_email: str | None = None
    passkey_rp_id: str = "localhost"
    passkey_origin: str = "http://127.0.0.1:5173"

    email_transport: EmailTransport = EmailTransport.CONSOLE
    email_from_address: str | None = None
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_password_file: Path | None = Field(default=None, exclude=True, repr=False)
    smtp_starttls: bool = True

    report_timezone: str = "America/Denver"
    report_delivery_time: time = time(hour=3, minute=0)

    @model_validator(mode="before")
    @classmethod
    def load_mounted_secrets(cls, values: object) -> object:
        """Load supported mounted secret files without logging their contents."""
        if not isinstance(values, dict):
            return values
        secret_file = values.get("smtp_password_file")
        if secret_file and not values.get("smtp_password"):
            try:
                values["smtp_password"] = (
                    Path(secret_file).read_text(encoding="utf-8").rstrip("\r\n")
                )
            except OSError:
                raise ValueError(
                    "The configured SMTP password file could not be read."
                ) from None
        return values

    @model_validator(mode="after")
    def validate_environment_configuration(self) -> Settings:
        """Validate settings that depend on the selected environment or transport."""
        if self.email_transport is EmailTransport.SMTP:
            missing = [
                name
                for name, value in (
                    ("CHORE_TRACKER_SMTP_HOST", self.smtp_host),
                    ("CHORE_TRACKER_EMAIL_FROM_ADDRESS", self.email_from_address),
                )
                if not value
            ]
            if missing:
                raise ValueError("SMTP transport requires: " + ", ".join(missing))
            if bool(self.smtp_username) != bool(self.smtp_password):
                raise ValueError(
                    "SMTP username and password must be configured together."
                )

        if self.environment is Environment.PRODUCTION:
            missing = [
                name
                for name, value in (
                    ("CHORE_TRACKER_PASSKEY_RP_ID", self.passkey_rp_id),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    "Production configuration requires: " + ", ".join(missing)
                )
            if self.app_origin.startswith("http://") or self.passkey_origin.startswith(
                "http://"
            ):
                raise ValueError(
                    "Production application and passkey origins must use HTTPS."
                )
            if self.passkey_rp_id == "localhost":
                raise ValueError(
                    "Production passkey relying-party ID must not be localhost."
                )
            if self.email_transport is EmailTransport.CONSOLE:
                raise ValueError(
                    "Production requires an explicitly configured email transport."
                )

        return self

    @field_validator("app_host")
    @classmethod
    def validate_app_host(cls, value: str) -> str:
        """Accept an IP address or a DNS host name for the HTTP bind address."""
        try:
            ipaddress.ip_address(value)
            return value
        except ValueError:
            pass
        if value == "localhost":
            return value
        labels = value.rstrip(".").split(".")
        if len(value) > 253 or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in labels
        ):
            raise ValueError("app_host must be an IP address or valid DNS host name.")
        return value

    @field_validator("passkey_rp_id")
    @classmethod
    def validate_passkey_rp_id(cls, value: str) -> str:
        """Require a host name for the WebAuthn relying-party ID."""
        if value == "localhost":
            return value
        labels = value.rstrip(".").split(".")
        if (
            len(value) > 253
            or len(labels) < 2
            or any(
                not re.fullmatch(
                    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label
                )
                for label in labels
            )
        ):
            raise ValueError("passkey_rp_id must be a valid domain name.")
        return value

    @field_validator("app_origin", "passkey_origin")
    @classmethod
    def validate_origins(cls, value: str) -> str:
        """Require a well-formed HTTP origin without a path or query."""
        parsed = urlsplit(value)
        try:
            _ = parsed.port
        except ValueError as error:
            raise ValueError("Origins must contain a valid port.") from error
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError(
                "Origins must be absolute HTTP or HTTPS URLs without a path."
            )
        return value.rstrip("/")

    @field_validator("report_timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError(
                "report_timezone must be a valid IANA timezone, "
                "for example America/Denver."
            ) from error
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""
    return Settings()
