"""Integration tests for daily checklist completion operations."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
import chore_tracker.api.routes.child_views as child_views
from chore_tracker.adapters.sqlite import connect
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
TODAY = datetime(2026, 11, 12, 12, tzinfo=ZoneInfo("America/Denver"))


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(TODAY.timestamp(), tz=tz)


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "completion.db"
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


def create_assignment(connection, member_name="Alex"):
    member_id = connection.execute(
        "INSERT INTO family_members (display_name) VALUES (?)", (member_name,)
    ).lastrowid
    chore_id = connection.execute(
        "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean kitchen')"
    ).lastrowid
    assignment_id = connection.execute(
        """INSERT INTO weekly_assignments
           (family_member_id, chore_id, week_start, week_end,
            chore_name_snapshot, chore_description_snapshot)
           VALUES (?, ?, '2026-11-09', '2026-11-15', 'Kitchen snapshot',
                   'Original description')""",
        (member_id, chore_id),
    ).lastrowid
    item_ids = []
    for position, label in enumerate(("Sweep floor", "Wipe counters")):
        item_ids.append(
            connection.execute(
                """INSERT INTO assignment_checklist_items
                   (weekly_assignment_id, label_snapshot, position)
                   VALUES (?, ?, ?)""",
                (assignment_id, label, position),
            ).lastrowid
        )
    return member_id, assignment_id, item_ids


def test_daily_completion_defaults_to_unchecked_without_creating_rows(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, _ = create_assignment(connection)

    response = client.get(
        f"/family-members/{member_id}/assignments/{assignment_id}/completion",
        params={"completion_date": "2026-11-12"},
    )

    assert response.status_code == 200
    assert response.json()["is_complete"] is False
    assert [item["is_completed"] for item in response.json()["checklist_items"]] == [
        False,
        False,
    ]
    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_checklist_completions"
            ).fetchone()[0]
            == 0
        )


def test_partial_and_all_complete_status_and_idempotent_retry(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, item_ids = create_assignment(connection)

    payload = {"completion_date": "2026-11-12", "is_completed": True}
    first = client.put(url, json=payload)
    retry = client.put(url, json=payload)

    assert first.status_code == retry.status_code == 200
    assert first.json()["checklist_item"]["is_completed"] is True
    assert first.json()["is_complete"] is False
    with connect(database_path) as connection:
        assert (
            connection.execute(
                """SELECT COUNT(*) FROM daily_checklist_completions
                   WHERE assignment_checklist_item_id = ? AND completion_date = ?""",
                (item_ids[0], "2026-11-12"),
            ).fetchone()[0]
            == 1
        )

    second_url = (
        f"/family-members/{member_id}/assignments/{assignment_id}/"
        f"checklist-items/{item_ids[1]}/completion"
    )
    completed = client.put(second_url, json=payload)
    assert completed.status_code == 200
    assert completed.json()["is_complete"] is True


def test_unchecking_item_updates_only_that_date_and_preserves_other_days(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, item_ids = create_assignment(connection)

    url = (
        f"/family-members/{member_id}/assignments/{assignment_id}/"
        f"checklist-items/{item_ids[0]}/completion"
    )
    assert (
        client.put(
            url, json={"completion_date": "2026-11-11", "is_completed": True}
        ).status_code
        == 200
    )
    assert (
        client.put(
            url, json={"completion_date": "2026-11-12", "is_completed": True}
        ).status_code
        == 200
    )
    unchecked = client.put(
        url, json={"completion_date": "2026-11-12", "is_completed": False}
    )

    assert unchecked.status_code == 200
    assert unchecked.json()["checklist_item"]["is_completed"] is False
    with connect(database_path) as connection:
        rows = connection.execute(
            """SELECT completion_date, is_completed, completed_at
               FROM daily_checklist_completions
               WHERE assignment_checklist_item_id = ?
               ORDER BY completion_date""",
            (item_ids[0],),
        ).fetchall()
        assert [(row["completion_date"], row["is_completed"]) for row in rows] == [
            ("2026-11-11", 1),
            ("2026-11-12", 0),
        ]
        assert rows[0]["completed_at"] is not None
        assert rows[1]["completed_at"] is None


def test_date_is_scoped_to_assignment_week_and_invalid_dates_are_rejected(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, item_ids = create_assignment(connection)

    url = (
        f"/family-members/{member_id}/assignments/{assignment_id}/"
        f"checklist-items/{item_ids[0]}/completion"
    )
    response = client.put(
        url, json={"completion_date": "2026-11-16", "is_completed": True}
    )

    assert response.status_code == 422
    assert "within the weekly assignment" in response.json()["detail"]
    assert (
        client.get(
            f"/family-members/{member_id}/assignments/{assignment_id}/completion",
            params={"completion_date": "not-a-date"},
        ).status_code
        == 422
    )
    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_checklist_completions"
            ).fetchone()[0]
            == 0
        )


def test_member_assignment_and_checklist_item_relationships_are_enforced(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, item_ids = create_assignment(connection)
        other_member_id = connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        ).lastrowid

    url = (
        f"/family-members/{member_id}/assignments/{assignment_id}/"
        f"checklist-items/{item_ids[0]}/completion"
    )
    payload = {"completion_date": "2026-11-12", "is_completed": True}
    assert (
        client.put(
            f"/family-members/{other_member_id}/assignments/{assignment_id}/"
            f"checklist-items/{item_ids[0]}/completion",
            json=payload,
        ).status_code
        == 404
    )
    assert (
        client.put(
            f"/family-members/{member_id}/assignments/{assignment_id}/"
            "checklist-items/999/completion",
            json=payload,
        ).status_code
        == 404
    )


def test_inactive_profile_cannot_update_completion(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, item_ids = create_assignment(connection)
        connection.execute(
            "UPDATE family_members SET is_active = 0 WHERE id = ?", (member_id,)
        )

    response = client.put(
        f"/family-members/{member_id}/assignments/{assignment_id}/"
        f"checklist-items/{item_ids[0]}/completion",
        json={"completion_date": "2026-11-12", "is_completed": True},
    )

    assert response.status_code == 409


def test_catalog_edits_do_not_change_completed_historical_snapshot(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, item_ids = create_assignment(connection)
        connection.execute(
            "UPDATE chores SET name = 'Kitchen v2', description = 'Changed' "
            "WHERE id = 1"
        )

    response = client.put(
        f"/family-members/{member_id}/assignments/{assignment_id}/"
        f"checklist-items/{item_ids[0]}/completion",
        json={"completion_date": "2026-11-12", "is_completed": True},
    )
    history = client.get(
        f"/family-members/{member_id}/assignments/{assignment_id}/completion",
        params={"completion_date": "2026-11-12"},
    )

    assert response.status_code == 200
    assert history.status_code == 200
    assert history.json()["checklist_items"][0]["label"] == "Sweep floor"
    assert history.json()["is_complete"] is False


def test_concurrent_item_updates_preserve_a_consistent_daily_state(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, item_ids = create_assignment(connection)

    def complete(item_id):
        return client.put(
            f"/family-members/{member_id}/assignments/{assignment_id}/"
            f"checklist-items/{item_id}/completion",
            json={"completion_date": "2026-11-12", "is_completed": True},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(complete, item_ids))

    assert [response.status_code for response in responses] == [200, 200]
    daily = client.get(
        f"/family-members/{member_id}/assignments/{assignment_id}/completion",
        params={"completion_date": "2026-11-12"},
    )
    assert daily.status_code == 200
    assert daily.json()["is_complete"] is True
    assert all(item["is_completed"] for item in daily.json()["checklist_items"])
