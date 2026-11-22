"""SQLite persistence for durable weekly rollover progress."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from chore_tracker.adapters.sqlite import transaction


def _format_timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


class SQLiteWeeklyRolloverPersistence:
    """Read and advance the scheduler checkpoint in one SQLite row."""

    def __init__(self, database_path: str | Path) -> None:
        self._database_path = database_path

    def last_completed_week_start(self) -> date | None:
        with transaction(self._database_path) as connection:
            row = connection.execute(
                """
                SELECT last_completed_week_start
                FROM weekly_rollover_state
                WHERE id = 1
                """
            ).fetchone()
        return None if row is None else date.fromisoformat(row[0])

    def mark_completed(self, week_start: date, completed_at: datetime) -> None:
        if not isinstance(week_start, date) or isinstance(week_start, datetime):
            raise TypeError("week_start must be a date")
        if week_start.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        if not isinstance(completed_at, datetime):
            raise TypeError("completed_at must be a timezone-aware datetime")
        if completed_at.tzinfo is None or completed_at.utcoffset() is None:
            raise ValueError("completed_at must be a timezone-aware datetime")

        with transaction(self._database_path) as connection:
            # Serialize checkpoints so concurrent scheduler runs cannot regress
            # or duplicate the durable completion record.
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO weekly_rollover_state (
                    id, last_completed_week_start, completed_at
                )
                VALUES (1, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    last_completed_week_start = excluded.last_completed_week_start,
                    completed_at = excluded.completed_at
                WHERE excluded.last_completed_week_start
                    > weekly_rollover_state.last_completed_week_start
                """,
                (week_start.isoformat(), _format_timestamp(completed_at)),
            )
