"""Integration tests for administrator family member management."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
import chore_tracker.api.routes.family_members as family_members
from chore_tracker.adapters.sqlite import connect
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "family-members.db"
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
        family_members,
        "get_settings",
        lambda: SimpleNamespace(database_path=database_path),
    )
    client = TestClient(app)
    started = client.post(
        "/auth/setup/start",
        json={"email": "admin@example.test"},
        headers={"Origin": ORIGIN},
    )
    monkeypatch.setattr(
        auth,
        "_verify_registration",
        lambda _challenge, _credential: SimpleNamespace(
            credential_id=b"admin-credential",
            credential_public_key=b"public-key",
            sign_count=0,
        ),
    )
    finished = client.post(
        "/auth/setup/finish",
        json={
            "challenge_id": started.json()["challenge_id"],
            "credential": {
                "id": "YWRtaW4tY3JlZGVudGlhbA",
                "response": {"transports": ["internal"]},
            },
        },
        headers={"Origin": ORIGIN},
    )
    assert finished.status_code == 200
    return client, database_path


def admin_headers():
    return {"Origin": ORIGIN}


def test_family_member_endpoints_require_admin_session(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    client.post("/auth/logout", headers=admin_headers())

    assert client.get("/family-members").status_code == 401
    assert client.post(
        "/family-members",
        json={"display_name": "Alex"},
        headers=admin_headers(),
    ).status_code == 401
    assert client.patch(
        "/family-members/1",
        json={"display_name": "Alex"},
        headers=admin_headers(),
    ).status_code == 401


def test_create_list_and_update_family_members_allow_duplicate_names(
    tmp_path, monkeypatch
):
    client, _ = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()

    first = client.post(
        "/family-members", json={"display_name": " Alex "}, headers=headers
    )
    second = client.post(
        "/family-members", json={"display_name": "Alex"}, headers=headers
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["display_name"] == "Alex"
    assert first.json()["id"] != second.json()["id"]

    listed = client.get("/family-members")
    assert listed.status_code == 200
    assert len(listed.json()) == 2
    assert {member["id"] for member in listed.json()} == {
        first.json()["id"],
        second.json()["id"],
    }

    updated = client.patch(
        f"/family-members/{first.json()['id']}",
        json={"display_name": "Alexandra", "is_active": False},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["display_name"] == "Alexandra"
    assert updated.json()["is_active"] is False


def test_family_member_validation_and_missing_profile(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()

    for invalid_name in ("", "   "):
        response = client.post(
            "/family-members",
            json={"display_name": invalid_name},
            headers=headers,
        )
        assert response.status_code == 422

    assert client.patch(
        "/family-members/999",
        json={"display_name": "Unknown"},
        headers=headers,
    ).status_code == 404
    assert client.patch(
        "/family-members/999",
        json={},
        headers=headers,
    ).status_code == 422


def test_deactivation_preserves_historical_assignment_and_completion(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()

    member = client.post(
        "/family-members", json={"display_name": "Alex"}, headers=headers
    ).json()

    with connect(database_path) as connection:
        chore_id = connection.execute(
            """INSERT INTO chores (name, description, is_active)
               VALUES ('Kitchen', '', 1)"""
        ).lastrowid
        assignment_id = connection.execute(
            """INSERT INTO weekly_assignments
               (family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot)
               VALUES (?, ?, '2026-11-09', '2026-11-15', 'Kitchen', '')""",
            (member["id"], chore_id),
        ).lastrowid
        item_id = connection.execute(
            """INSERT INTO assignment_checklist_items
               (weekly_assignment_id, label_snapshot, position)
               VALUES (?, 'Wipe counters', 0)""",
            (assignment_id,),
        ).lastrowid
        connection.execute(
            """INSERT INTO daily_checklist_completions
               (assignment_checklist_item_id, completion_date, is_completed,
                completed_at)
               VALUES (?, '2026-11-09', 1, '2026-11-09T12:00:00Z')""",
            (item_id,),
        )

    deactivated = client.patch(
        f"/family-members/{member['id']}",
        json={"is_active": False},
        headers=headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["is_active"] is False

    with connect(database_path) as connection:
        assignment = connection.execute(
            "SELECT family_member_id FROM weekly_assignments WHERE id = ?",
            (assignment_id,),
        ).fetchone()
        completion = connection.execute(
            """SELECT is_completed FROM daily_checklist_completions
               WHERE assignment_checklist_item_id = ?""",
            (item_id,),
        ).fetchone()

    assert assignment["family_member_id"] == member["id"]
    assert completion["is_completed"] == 1
