"""Integration tests for the versioned SQLite schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from chore_tracker.adapters.sqlite import connect

ROOT = Path(__file__).resolve().parents[1]


def migration_config(database_path: Path) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    return config


def read_connection(database_path: Path) -> sqlite3.Connection:
    return connect(database_path)


def test_fresh_database_is_created_entirely_by_migrations(tmp_path) -> None:
    database_path = tmp_path / "fresh.db"
    command.upgrade(migration_config(database_path), "head")

    with read_connection(database_path) as connection:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "administrators",
            "administrator_passkey_credentials",
            "authentication_challenges",
            "administrator_enrollment_tokens",
            "administrator_sessions",
            "family_members",
            "chores",
            "chore_checklist_items",
            "weekly_assignments",
            "assignment_checklist_items",
            "daily_checklist_completions",
            "weekly_reports",
            "report_deliveries",
            "alembic_version",
        } <= tables
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()["version_num"]
        assert revision == "0004_administrator_passkeys"


def test_upgrade_from_prior_revision_preserves_existing_rows(tmp_path) -> None:
    database_path = tmp_path / "upgrade.db"
    config = migration_config(database_path)
    command.upgrade(config, "0001_core_entities")

    with read_connection(database_path) as connection:
        connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        )
        connection.execute(
            "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean kitchen')"
        )

    command.upgrade(config, "head")

    with read_connection(database_path) as connection:
        member = connection.execute(
            "SELECT display_name FROM family_members WHERE id = 1"
        ).fetchone()
        chore = connection.execute("SELECT name FROM chores WHERE id = 1").fetchone()
        assert member["display_name"] == "Taylor"
        assert chore["name"] == "Kitchen"
        assert connection.execute(
            "SELECT COUNT(*) FROM weekly_assignments"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM administrator_passkey_credentials"
        ).fetchone()[0] == 0
