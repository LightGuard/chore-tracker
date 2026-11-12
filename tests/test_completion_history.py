"""Integration tests for historical daily completion queries."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
import chore_tracker.api.routes.child_views as child_views
from chore_tracker.adapters.sqlite import connect
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "completion-history.db"
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
    return TestClient(app), database_path


def create_assignment(connection, week_start="2026-11-09", member_name="Alex"):
    start = date.fromisoformat(week_start)
    week_end = start + timedelta(days=6)
    member_id = connection.execute(
        "INSERT INTO family_members (display_name) VALUES (?)",
        (member_name,),
    ).lastrowid
    chore_id = connection.execute(
        "INSERT INTO chores (name, description) VALUES ('Kitchen', 'Clean kitchen')"
    ).lastrowid
    assignment_id = connection.execute(
        """INSERT INTO weekly_assignments
           (family_member_id, chore_id, week_start, week_end,
            chore_name_snapshot, chore_description_snapshot)
           VALUES (?, ?, ?, ?, 'Kitchen snapshot', 'Original description')""",
        (member_id, chore_id, start.isoformat(), week_end.isoformat()),
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
    return member_id, assignment_id, chore_id, item_ids


def set_item(client, member_id, assignment_id, item_id, completion_date, completed):
    return client.put(
        f"/family-members/{member_id}/assignments/{assignment_id}/"
        f"checklist-items/{item_id}/completion",
        json={"completion_date": completion_date, "is_completed": completed},
    )


def test_history_distinguishes_complete_incomplete_and_unrecorded_days(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, assignment_id, _, item_ids = create_assignment(connection)

    assert (
        set_item(
            client, member_id, assignment_id, item_ids[0], "2026-11-12", True
        ).status_code
        == 200
    )
    assert (
        set_item(
            client, member_id, assignment_id, item_ids[1], "2026-11-12", True
        ).status_code
        == 200
    )
    assert (
        set_item(
            client, member_id, assignment_id, item_ids[0], "2026-11-11", False
        ).status_code
        == 200
    )

    response = client.get(f"/family-members/{member_id}/completion-history")

    assert response.status_code == 200
    payload = response.json()
    by_date = {item["completion_date"]: item for item in payload["items"]}
    assert payload["total"] == 7
    assert by_date["2026-11-12"]["completion_status"] == "complete"
    assert by_date["2026-11-11"]["completion_status"] == "incomplete"
    assert by_date["2026-11-10"]["completion_status"] == "not_yet_recorded"
    assert by_date["2026-11-12"]["assignment_id"] == assignment_id
    assert by_date["2026-11-12"]["week_start"] == "2026-11-09"
    assert by_date["2026-11-12"]["week_end"] == "2026-11-15"
    assert by_date["2026-11-12"]["chore_name"] == "Kitchen snapshot"
    assert by_date["2026-11-12"]["chore_description"] == "Original description"


def test_history_is_available_for_inactive_profiles_and_preserves_snapshots(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, _, chore_id, _ = create_assignment(connection)
        connection.execute(
            "UPDATE family_members SET is_active = 0 WHERE id = ?", (member_id,)
        )
        connection.execute(
            "UPDATE chores SET name = 'Renamed chore', description = 'Changed', "
            "is_active = 0 WHERE id = ?",
            (chore_id,),
        )

    response = client.get(f"/family-members/{member_id}/completion-history")

    assert response.status_code == 200
    assert response.json()["total"] == 7
    assert response.json()["items"][0]["chore_name"] == "Kitchen snapshot"
    assert response.json()["items"][0]["chore_description"] == "Original description"


def test_history_for_existing_profile_without_assignments_is_empty(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Taylor')"
        ).lastrowid

    response = client.get(f"/family-members/{member_id}/completion-history")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "limit": 50, "offset": 0}


def test_history_returns_404_for_unknown_profile(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)

    response = client.get("/family-members/999/completion-history")

    assert response.status_code == 404
    assert response.json()["detail"] == "Family member was not found"


def test_history_pagination_is_bounded_and_has_stable_order(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, _, _, _ = create_assignment(connection)
        # A second week is assigned to the same profile.
        chore_id = connection.execute(
            "INSERT INTO chores (name, description) VALUES ('Yard', '')"
        ).lastrowid
        connection.execute(
            """INSERT INTO weekly_assignments
               (family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot)
               VALUES (?, ?, '2026-11-16', '2026-11-22', 'Yard snapshot', '')""",
            (member_id, chore_id),
        )

    first = client.get(
        f"/family-members/{member_id}/completion-history",
        params={"limit": 5, "offset": 0},
    )
    second = client.get(
        f"/family-members/{member_id}/completion-history",
        params={"limit": 5, "offset": 5},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 14
    first_dates = [item["completion_date"] for item in first.json()["items"]]
    second_dates = [item["completion_date"] for item in second.json()["items"]]
    assert first_dates == [
        "2026-11-22",
        "2026-11-21",
        "2026-11-20",
        "2026-11-19",
        "2026-11-18",
    ]
    assert second_dates == [
        "2026-11-17",
        "2026-11-16",
        "2026-11-15",
        "2026-11-14",
        "2026-11-13",
    ]
    assert not set(first_dates).intersection(second_dates)


def test_history_rejects_invalid_pagination_values(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id, _, _, _ = create_assignment(connection)

    assert (
        client.get(
            f"/family-members/{member_id}/completion-history",
            params={"limit": 0},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/family-members/{member_id}/completion-history",
            params={"limit": 101},
        ).status_code
        == 422
    )
    assert (
        client.get(
            f"/family-members/{member_id}/completion-history",
            params={"offset": -1},
        ).status_code
        == 422
    )
