"""Integration tests for the durable weekly rollover scheduler."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.weekly_rollover import (
    SQLiteWeeklyRolloverPersistence,
)

ROOT = Path(__file__).resolve().parents[1]
WEEK_START = date(2026, 11, 23)
COMPLETED_AT = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)


def _database(tmp_path: Path) -> Path:
    database_path = tmp_path / "rollover.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    command.upgrade(config, "head")
    return database_path


def _persistence(database_path: Path) -> SQLiteWeeklyRolloverPersistence:
    return SQLiteWeeklyRolloverPersistence(database_path)


def test_checkpoint_starts_empty_and_advances_forward(tmp_path) -> None:
    database_path = _database(tmp_path)
    persistence = _persistence(database_path)

    assert persistence.last_completed_week_start() is None

    persistence.mark_completed(WEEK_START, COMPLETED_AT)
    assert persistence.last_completed_week_start() == WEEK_START

    persistence.mark_completed(WEEK_START + timedelta(days=7), COMPLETED_AT)
    assert persistence.last_completed_week_start() == WEEK_START + timedelta(days=7)


def test_checkpoint_does_not_regress_or_rewrite_the_completed_week(tmp_path) -> None:
    database_path = _database(tmp_path)
    persistence = _persistence(database_path)
    persistence.mark_completed(WEEK_START, COMPLETED_AT)

    persistence.mark_completed(WEEK_START - timedelta(days=7), COMPLETED_AT)
    persistence.mark_completed(WEEK_START, COMPLETED_AT + timedelta(hours=1))

    assert persistence.last_completed_week_start() == WEEK_START
    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT completed_at
            FROM weekly_rollover_state
            WHERE id = 1
            """
        ).fetchone()
    assert row["completed_at"] == "2026-11-23T10:00:00.000Z"


def test_checkpoint_rejects_invalid_week_and_timestamp(tmp_path) -> None:
    database_path = _database(tmp_path)
    persistence = _persistence(database_path)

    with pytest.raises(ValueError, match="Monday"):
        persistence.mark_completed(WEEK_START + timedelta(days=1), COMPLETED_AT)
    with pytest.raises(ValueError, match="timezone-aware"):
        persistence.mark_completed(WEEK_START, datetime(2026, 11, 23, 10, 0))
    with pytest.raises(TypeError, match="week_start must be a date"):
        persistence.mark_completed(datetime(2026, 11, 23, 10, 0), COMPLETED_AT)
    with pytest.raises(TypeError, match="completed_at"):
        persistence.mark_completed(WEEK_START, "2026-11-23T10:00:00Z")
