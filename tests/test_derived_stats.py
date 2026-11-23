"""Integration tests for the generic child-facing derived-stat endpoint."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.adapters.sqlite.child_views as child_views_persistence
import chore_tracker.api.routes.auth as auth
import chore_tracker.api.routes.child_views as child_views
from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite import transaction as real_transaction
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
TODAY = datetime(2026, 11, 12, 12, tzinfo=ZoneInfo("America/Denver"))


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(TODAY.timestamp(), tz=tz)


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "derived-stats.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    command.upgrade(config, "head")
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(
            database_path=database_path,
            passkey_rp_id="localhost",
            passkey_origin=ORIGIN,
        ),
    )
    monkeypatch.setattr(
        child_views,
        "get_settings",
        lambda: SimpleNamespace(
            database_path=database_path,
            report_timezone="America/Denver",
        ),
    )
    monkeypatch.setattr(child_views, "datetime", FrozenDateTime)
    return TestClient(app), database_path


def create_member(connection, name, active=True):
    return connection.execute(
        "INSERT INTO family_members (display_name, is_active) VALUES (?, ?)",
        (name, int(active)),
    ).lastrowid


def create_assignment(
    connection, member_id, week_start, labels=("Sweep floor", "Wipe counters")
):
    start = date.fromisoformat(week_start)
    week_end = start + timedelta(days=6)
    chore_id = connection.execute(
        "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean kitchen')"
    ).lastrowid
    assignment_id = connection.execute(
        """INSERT INTO weekly_assignments
           (family_member_id, chore_id, week_start, week_end,
            chore_name_snapshot, chore_description_snapshot)
           VALUES (?, ?, ?, ?, 'Kitchen snapshot', 'Snapshot description')""",
        (member_id, chore_id, start.isoformat(), week_end.isoformat()),
    ).lastrowid
    item_ids = []
    for position, label in enumerate(labels):
        item_ids.append(
            connection.execute(
                """INSERT INTO assignment_checklist_items
                   (weekly_assignment_id, label_snapshot, position)
                   VALUES (?, ?, ?)""",
                (assignment_id, label, position),
            ).lastrowid
        )
    return assignment_id, item_ids


def record_day(connection, item_ids, day, completed_positions):
    for position, item_id in enumerate(item_ids):
        is_completed = position in completed_positions
        connection.execute(
            """INSERT INTO daily_checklist_completions
               (assignment_checklist_item_id, completion_date,
                is_completed, completed_at)
               VALUES (?, ?, ?, ?)""",
            (
                item_id,
                day,
                int(is_completed),
                f"{day}T18:00:00Z" if is_completed else None,
            ),
        )


def complete_day(connection, item_ids, day):
    record_day(connection, item_ids, day, set(range(len(item_ids))))


def test_returns_generic_completion_facts_and_current_week_day_states(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        _, current_items = create_assignment(connection, member_id, "2026-11-09")
        _, prior_items = create_assignment(connection, member_id, "2026-11-02")
        complete_day(connection, current_items, "2026-11-09")
        record_day(connection, current_items, "2026-11-10", {0})
        complete_day(connection, current_items, "2026-11-12")
        complete_day(connection, prior_items, "2026-11-08")
        record_day(connection, prior_items, "2026-11-07", {0})

    response = client.get(f"/family-members/{member_id}/derived-stats")

    assert response.status_code == 200
    assert response.json() == {
        "family_member_id": member_id,
        "display_name": "Alex",
        "as_of": "2026-11-12",
        "timezone": "America/Denver",
        "lifetime": {
            "completed_checklist_items": 8,
            "complete_days": 3,
            "current_streak": 1,
        },
        "current_week": {
            "week_start": "2026-11-09",
            "week_end": "2026-11-15",
            "completed_checklist_items": 5,
            "complete_days": 2,
            "days": [
                {
                    "date": "2026-11-09",
                    "completed_checklist_items": 2,
                    "total_checklist_items": 2,
                    "state": "complete",
                },
                {
                    "date": "2026-11-10",
                    "completed_checklist_items": 1,
                    "total_checklist_items": 2,
                    "state": "incomplete",
                },
                {
                    "date": "2026-11-11",
                    "completed_checklist_items": 0,
                    "total_checklist_items": 2,
                    "state": "not_recorded",
                },
                {
                    "date": "2026-11-12",
                    "completed_checklist_items": 2,
                    "total_checklist_items": 2,
                    "state": "complete",
                },
                {
                    "date": "2026-11-13",
                    "completed_checklist_items": 0,
                    "total_checklist_items": 2,
                    "state": "not_recorded",
                },
                {
                    "date": "2026-11-14",
                    "completed_checklist_items": 0,
                    "total_checklist_items": 2,
                    "state": "not_recorded",
                },
                {
                    "date": "2026-11-15",
                    "completed_checklist_items": 0,
                    "total_checklist_items": 2,
                    "state": "not_recorded",
                },
            ],
        },
        "household": {
            "active_players": 1,
            "weekly_standings": [
                {
                    "family_member_id": member_id,
                    "display_name": "Alex",
                    "completed_checklist_items": 5,
                    "complete_days": 2,
                    "current_streak": 1,
                }
            ],
        },
    }


def test_streak_ends_yesterday_when_today_is_incomplete(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        _, items = create_assignment(
            connection, member_id, "2026-11-09", ("One", "Two", "Three")
        )
        complete_day(connection, items, "2026-11-09")
        complete_day(connection, items, "2026-11-10")
        complete_day(connection, items, "2026-11-11")
        record_day(connection, items, "2026-11-12", {0})

    payload = client.get(f"/family-members/{member_id}/derived-stats").json()

    assert payload["lifetime"]["current_streak"] == 3
    assert payload["current_week"]["complete_days"] == 3


def test_streak_is_zero_when_today_and_yesterday_are_not_complete(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        _, items = create_assignment(connection, member_id, "2026-11-09")
        complete_day(connection, items, "2026-11-09")
        record_day(connection, items, "2026-11-10", set())
        complete_day(connection, items, "2026-11-12")

    payload = client.get(f"/family-members/{member_id}/derived-stats").json()

    assert payload["lifetime"]["current_streak"] == 1
    assert payload["lifetime"]["complete_days"] == 2


def test_current_week_rolls_over_at_monday_without_losing_lifetime_facts(
    tmp_path, monkeypatch
):
    class MondayDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 16, 0, 1, tzinfo=tz)

    client, database_path = prepare_client(tmp_path, monkeypatch)
    monkeypatch.setattr(child_views, "datetime", MondayDateTime)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        _, prior_items = create_assignment(connection, member_id, "2026-11-09")
        for day in range(9, 14):
            complete_day(connection, prior_items, f"2026-11-{day:02d}")

    payload = client.get(f"/family-members/{member_id}/derived-stats").json()

    assert payload["as_of"] == "2026-11-16"
    assert payload["current_week"]["week_start"] == "2026-11-16"
    assert payload["current_week"]["week_end"] == "2026-11-22"
    assert payload["current_week"]["completed_checklist_items"] == 0
    assert payload["current_week"]["complete_days"] == 0
    assert [day["state"] for day in payload["current_week"]["days"]] == [
        "not_recorded"
    ] * 7
    assert payload["lifetime"]["completed_checklist_items"] == 10
    assert payload["lifetime"]["complete_days"] == 5
    assert payload["lifetime"]["current_streak"] == 0


def test_standings_include_all_active_children_with_stable_tie_breakers(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        alex_id = create_member(connection, "Alex")
        sam_id = create_member(connection, "Sam")
        riley_id = create_member(connection, "Riley")
        amy_id = create_member(connection, "amy")
        bea_id = create_member(connection, "Bea")
        inactive_id = create_member(connection, "Zoe", active=False)

        _, alex_items = create_assignment(connection, alex_id, "2026-11-09")
        for day in ("2026-11-09", "2026-11-10", "2026-11-11"):
            complete_day(connection, alex_items, day)

        _, sam_items = create_assignment(
            connection, sam_id, "2026-11-09", ("One", "Two", "Three")
        )
        for day in ("2026-11-09", "2026-11-10"):
            complete_day(connection, sam_items, day)

        _, riley_items = create_assignment(
            connection,
            riley_id,
            "2026-11-09",
            ("One", "Two", "Three", "Four"),
        )
        complete_day(connection, riley_items, "2026-11-12")

        _, inactive_items = create_assignment(
            connection,
            inactive_id,
            "2026-11-09",
            ("One", "Two", "Three", "Four", "Five"),
        )
        for day in ("2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12"):
            complete_day(connection, inactive_items, day)

    payload = client.get(f"/family-members/{alex_id}/derived-stats").json()

    assert payload["household"]["active_players"] == 5
    assert payload["household"]["weekly_standings"] == [
        {
            "family_member_id": alex_id,
            "display_name": "Alex",
            "completed_checklist_items": 6,
            "complete_days": 3,
            "current_streak": 3,
        },
        {
            "family_member_id": sam_id,
            "display_name": "Sam",
            "completed_checklist_items": 6,
            "complete_days": 2,
            "current_streak": 0,
        },
        {
            "family_member_id": riley_id,
            "display_name": "Riley",
            "completed_checklist_items": 4,
            "complete_days": 1,
            "current_streak": 1,
        },
        {
            "family_member_id": amy_id,
            "display_name": "amy",
            "completed_checklist_items": 0,
            "complete_days": 0,
            "current_streak": 0,
        },
        {
            "family_member_id": bea_id,
            "display_name": "Bea",
            "completed_checklist_items": 0,
            "complete_days": 0,
            "current_streak": 0,
        },
    ]
    assert all(
        "rank" not in standing for standing in payload["household"]["weekly_standings"]
    )


def test_empty_history_returns_zeroes_for_an_active_child_without_an_assignment(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Taylor")

    response = client.get(f"/family-members/{member_id}/derived-stats")

    assert response.status_code == 200
    payload = response.json()
    assert payload["lifetime"] == {
        "completed_checklist_items": 0,
        "complete_days": 0,
        "current_streak": 0,
    }
    assert payload["current_week"]["completed_checklist_items"] == 0
    assert payload["current_week"]["complete_days"] == 0
    assert all(
        day["total_checklist_items"] == 0 and day["state"] == "not_recorded"
        for day in payload["current_week"]["days"]
    )
    assert payload["household"]["weekly_standings"][0]["family_member_id"] == member_id


def test_unknown_and_inactive_members_return_the_existing_child_view_errors(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        inactive_id = create_member(connection, "Inactive", active=False)

    unknown = client.get("/family-members/999/derived-stats")
    inactive = client.get(f"/family-members/{inactive_id}/derived-stats")

    assert unknown.status_code == 404
    assert unknown.json()["detail"] == "Family member was not found"
    assert inactive.status_code == 409
    assert inactive.json()["detail"] == "Family member is inactive"


def test_derived_stats_are_read_only_and_add_no_schema(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        _, items = create_assignment(connection, member_id, "2026-11-09")
        complete_day(connection, items, "2026-11-09")
        before_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        before_completions = connection.execute(
            "SELECT COUNT(*) FROM daily_checklist_completions"
        ).fetchone()[0]
        before_assignments = connection.execute(
            "SELECT COUNT(*) FROM weekly_assignments"
        ).fetchone()[0]

    assert client.get(f"/family-members/{member_id}/derived-stats").status_code == 200

    with connect(database_path) as connection:
        after_tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert after_tables == before_tables
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_checklist_completions"
            ).fetchone()[0]
            == before_completions
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_assignments").fetchone()[0]
            == before_assignments
        )


def test_aggregate_reads_stay_constant_for_seven_active_children(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_ids = [
            create_member(connection, f"Player {index}") for index in range(7)
        ]
        for index, member_id in enumerate(member_ids):
            _, items = create_assignment(
                connection,
                member_id,
                "2026-11-09",
                ("One", "Two", "Three"),
            )
            for day in range(9, 9 + index):
                complete_day(connection, items, f"2026-11-{day:02d}")

    statements: list[str] = []

    @contextmanager
    def traced_transaction(path):
        with real_transaction(path) as connection:
            connection.set_trace_callback(statements.append)
            yield connection

    monkeypatch.setattr(child_views_persistence, "transaction", traced_transaction)
    response = client.get(f"/family-members/{member_ids[0]}/derived-stats")

    assert response.status_code == 200
    aggregate_statements = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith(("SELECT", "WITH"))
    ]
    assert len(aggregate_statements) == 2
