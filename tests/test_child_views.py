"""Integration tests for unauthenticated child-facing API views."""

from __future__ import annotations

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
    database_path = tmp_path / "child-views.db"
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


def create_assignment(connection, family_member_id):
    chore_id = connection.execute(
        """INSERT INTO chores (name, description, is_active)
           VALUES ('Kitchen', 'Clean the kitchen', 1)"""
    ).lastrowid
    assignment_id = connection.execute(
        """INSERT INTO weekly_assignments
           (family_member_id, chore_id, week_start, week_end,
            chore_name_snapshot, chore_description_snapshot)
           VALUES (?, ?, '2026-11-09', '2026-11-15', 'Kitchen snapshot',
                   'Snapshot description')""",
        (family_member_id, chore_id),
    ).lastrowid
    first_item = connection.execute(
        """INSERT INTO assignment_checklist_items
           (weekly_assignment_id, label_snapshot, position)
           VALUES (?, 'Sweep floor', 0)""",
        (assignment_id,),
    ).lastrowid
    second_item = connection.execute(
        """INSERT INTO assignment_checklist_items
           (weekly_assignment_id, label_snapshot, position)
           VALUES (?, 'Wipe counters', 1)""",
        (assignment_id,),
    ).lastrowid
    return assignment_id, first_item, second_item


def test_active_family_member_selector_is_public_and_excludes_inactive(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        create_member(connection, "Zoe")
        create_member(connection, "Alex")
        create_member(connection, "Inactive", active=False)

    response = client.get("/family-members/active")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 2, "display_name": "Alex"},
        {"id": 1, "display_name": "Zoe"},
    ]


def test_current_assignment_returns_snapshots_in_order_and_today_completion(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        assignment_id, first_item, second_item = create_assignment(
            connection, member_id
        )
        connection.execute(
            """INSERT INTO daily_checklist_completions
               (assignment_checklist_item_id, completion_date, is_completed,
                completed_at)
               VALUES (?, '2026-11-12', 1, '2026-11-12T18:00:00Z')""",
            (second_item,),
        )

    response = client.get(f"/family-members/{member_id}/current-assignment")

    assert response.status_code == 200
    assert response.json() == {
        "id": assignment_id,
        "family_member_id": member_id,
        "week_start": "2026-11-09",
        "week_end": "2026-11-15",
        "chore_name": "Kitchen snapshot",
        "chore_description": "Snapshot description",
        "today": "2026-11-12",
        "checklist_items": [
            {
                "id": first_item,
                "label": "Sweep floor",
                "position": 0,
                "is_completed": False,
            },
            {
                "id": second_item,
                "label": "Wipe counters",
                "position": 1,
                "is_completed": True,
            },
        ],
        "is_complete": False,
    }


def test_current_assignment_is_complete_only_when_every_item_is_checked(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        _, first_item, second_item = create_assignment(connection, member_id)
        connection.executemany(
            """INSERT INTO daily_checklist_completions
               (assignment_checklist_item_id, completion_date, is_completed,
                completed_at)
               VALUES (?, '2026-11-12', 1, '2026-11-12T18:00:00Z')""",
            [(first_item,), (second_item,)],
        )

    response = client.get(f"/family-members/{member_id}/current-assignment")

    assert response.status_code == 200
    assert response.json()["is_complete"] is True


def test_current_assignment_uses_monday_sunday_week_boundaries(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        create_assignment(connection, member_id)
        next_chore_id = connection.execute(
            """INSERT INTO chores (name, description, is_active)
               VALUES ('Yard', '', 1)"""
        ).lastrowid
        connection.execute(
            """INSERT INTO weekly_assignments
               (family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot)
               VALUES (?, ?, '2026-11-16', '2026-11-22', 'Next week', '')""",
            (member_id, next_chore_id),
        )

    response = client.get(f"/family-members/{member_id}/current-assignment")

    assert response.status_code == 200
    assert response.json()["week_start"] == "2026-11-09"
    assert response.json()["week_end"] == "2026-11-15"


def test_current_assignment_documents_missing_inactive_and_unassigned_profiles(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        inactive_id = create_member(connection, "Inactive", active=False)
        unassigned_id = create_member(connection, "Unassigned")

    assert client.get("/family-members/999/current-assignment").status_code == 404
    assert (
        client.get(f"/family-members/{inactive_id}/current-assignment").status_code
        == 409
    )
    assert (
        client.get(f"/family-members/{unassigned_id}/current-assignment").status_code
        == 404
    )


def test_child_facing_endpoints_do_not_require_authentication(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        create_assignment(connection, member_id)

    assert client.get("/family-members/active").status_code == 200
    assert (
        client.get(f"/family-members/{member_id}/current-assignment").status_code
        == 200
    )


def test_current_assignment_remains_same_on_sunday_boundary(tmp_path, monkeypatch):
    class SundayDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 15, 23, 59, tzinfo=tz)

    client, database_path = prepare_client(tmp_path, monkeypatch)
    monkeypatch.setattr(child_views, "datetime", SundayDateTime)
    with connect(database_path) as connection:
        member_id = create_member(connection, "Alex")
        create_assignment(connection, member_id)

    response = client.get(f"/family-members/{member_id}/current-assignment")

    assert response.status_code == 200
    assert response.json()["today"] == "2026-11-15"
    assert response.json()["week_start"] == "2026-11-09"
    assert response.json()["week_end"] == "2026-11-15"


def test_current_assignment_moves_to_new_week_on_monday_boundary(
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
        create_assignment(connection, member_id)
        next_chore_id = connection.execute(
            """INSERT INTO chores (name, description, is_active)
               VALUES ('Yard', '', 1)"""
        ).lastrowid
        connection.execute(
            """INSERT INTO weekly_assignments
               (family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot)
               VALUES (?, ?, '2026-11-16', '2026-11-22', 'Next week', '')""",
            (member_id, next_chore_id),
        )

    response = client.get(f"/family-members/{member_id}/current-assignment")

    assert response.status_code == 200
    assert response.json()["today"] == "2026-11-16"
    assert response.json()["week_start"] == "2026-11-16"
    assert response.json()["week_end"] == "2026-11-22"
    assert response.json()["chore_name"] == "Next week"
