"""Tests for SQLite connection and transaction behavior."""

from __future__ import annotations

import sqlite3

import pytest

from chore_tracker.adapters.sqlite import connect, transaction


def test_foreign_keys_are_enabled_for_every_connection(tmp_path) -> None:
    database_path = tmp_path / "tracker.db"
    with transaction(database_path) as connection:
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            """
            CREATE TABLE child (
                parent_id INTEGER NOT NULL REFERENCES parent(id)
            )
            """
        )

    for _ in range(2):
        with transaction(database_path) as connection:
            assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("INSERT INTO child (parent_id) VALUES (999)")


def test_transaction_rolls_back_all_writes_on_failure(tmp_path) -> None:
    database_path = tmp_path / "tracker.db"
    with transaction(database_path) as connection:
        connection.execute("CREATE TABLE entries (value TEXT NOT NULL)")

    with pytest.raises(RuntimeError, match="abort transaction"):
        with transaction(database_path) as connection:
            connection.execute("INSERT INTO entries (value) VALUES ('not committed')")
            raise RuntimeError("abort transaction")

    with transaction(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0] == 0


def test_connect_creates_parent_directory(tmp_path) -> None:
    database_path = tmp_path / "data" / "nested" / "tracker.db"

    connection = connect(database_path)
    try:
        assert database_path.exists()
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        connection.close()
