"""Integration tests for administrator chore catalog management."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.family_chore_management import (
    SQLiteFamilyChoreManagementPersistence,
)
from chore_tracker.application.services.family_chore_management import (
    FamilyChoreManagementService,
    ManagementError,
)
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "chores.db"
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
        app.state,
        "management_service_factory",
        lambda: FamilyChoreManagementService(
            SQLiteFamilyChoreManagementPersistence(database_path)
        ),
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


def test_catalog_requires_admin_session(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    client.post("/auth/logout", headers=admin_headers())
    assert client.get("/chores").status_code == 401
    assert (
        client.post(
            "/chores", json={"name": "Kitchen"}, headers=admin_headers()
        ).status_code
        == 401
    )


def test_chore_checklist_crud_activation_and_ordering(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()

    created = client.post(
        "/chores",
        json={"name": "Kitchen", "description": "Clean the kitchen"},
        headers=headers,
    )
    assert created.status_code == 201
    chore_id = created.json()["id"]
    assert created.json()["is_active"] is False

    invalid_activation = client.patch(
        f"/chores/{chore_id}", json={"is_active": True}, headers=headers
    )
    assert invalid_activation.status_code == 409

    first = client.post(
        f"/chores/{chore_id}/checklist-items",
        json={"label": "Wipe counters"},
        headers=headers,
    )
    second = client.post(
        f"/chores/{chore_id}/checklist-items",
        json={"label": "Sweep floor"},
        headers=headers,
    )
    assert first.status_code == second.status_code == 201
    first_id, second_id = first.json()["id"], second.json()["id"]

    activated = client.patch(
        f"/chores/{chore_id}",
        json={"name": "Kitchen cleanup", "is_active": True},
        headers=headers,
    )
    assert activated.status_code == 200
    assert activated.json()["name"] == "Kitchen cleanup"

    reordered = client.put(
        f"/chores/{chore_id}/checklist-order",
        json={"ordered_item_ids": [second_id, first_id]},
        headers=headers,
    )
    assert reordered.status_code == 200
    assert [item["id"] for item in reordered.json()["checklist_items"]] == [
        second_id,
        first_id,
    ]
    assert [item["position"] for item in reordered.json()["checklist_items"]] == [0, 1]

    edited = client.patch(
        f"/chores/{chore_id}/checklist-items/{first_id}",
        json={"label": "Wipe all counters"},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["label"] == "Wipe all counters"

    assert (
        client.delete(
            f"/chores/{chore_id}/checklist-items/{first_id}", headers=headers
        ).status_code
        == 204
    )
    last_item_deactivation = client.patch(
        f"/chores/{chore_id}/checklist-items/{second_id}",
        json={"is_active": False},
        headers=headers,
    )
    assert last_item_deactivation.status_code == 409
    last_item_rejection = client.delete(
        f"/chores/{chore_id}/checklist-items/{second_id}", headers=headers
    )
    assert last_item_rejection.status_code == 409

    assert (
        client.patch(
            f"/chores/{chore_id}", json={"is_active": False}, headers=headers
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/chores/{chore_id}/checklist-items/{second_id}", headers=headers
        ).status_code
        == 204
    )

    updated = client.patch(
        f"/chores/{chore_id}",
        json={"description": "Updated description"},
        headers=headers,
    )
    assert updated.json()["description"] == "Updated description"


def test_invalid_names_labels_and_partial_reorder_are_rejected(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()

    assert (
        client.post("/chores", json={"name": "   "}, headers=headers).status_code == 422
    )
    created = client.post("/chores", json={"name": "Bathroom"}, headers=headers)
    chore_id = created.json()["id"]
    assert (
        client.post(
            f"/chores/{chore_id}/checklist-items",
            json={"label": "  "},
            headers=headers,
        ).status_code
        == 422
    )
    item = client.post(
        f"/chores/{chore_id}/checklist-items",
        json={"label": "Clean sink"},
        headers=headers,
    ).json()
    assert (
        client.put(
            f"/chores/{chore_id}/checklist-order",
            json={"ordered_item_ids": []},
            headers=headers,
        ).status_code
        == 422
    )
    assert (
        client.put(
            f"/chores/{chore_id}/checklist-order",
            json={"ordered_item_ids": [item["id"], item["id"]]},
            headers=headers,
        ).status_code
        == 422
    )


def test_catalog_changes_preserve_assignment_snapshots_and_completions(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()
    chore = client.post("/chores", json={"name": "Laundry"}, headers=headers).json()
    chore_id = chore["id"]
    item = client.post(
        f"/chores/{chore_id}/checklist-items",
        json={"label": "Fold clothes"},
        headers=headers,
    ).json()

    with connect(database_path) as connection:
        member_id = connection.execute(
            "INSERT INTO family_members (display_name) VALUES ('Alex')"
        ).lastrowid
        assignment_id = connection.execute(
            """INSERT INTO weekly_assignments
               (family_member_id, chore_id, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot)
               VALUES (?, ?, '2026-11-09', '2026-11-15', 'Laundry', 'Original')""",
            (member_id, chore_id),
        ).lastrowid
        snapshot_id = connection.execute(
            """INSERT INTO assignment_checklist_items
               (weekly_assignment_id, source_checklist_item_id,
                label_snapshot, position)
               VALUES (?, ?, 'Fold clothes', 0)""",
            (assignment_id, item["id"]),
        ).lastrowid
        connection.execute(
            """INSERT INTO daily_checklist_completions
               (assignment_checklist_item_id, completion_date,
                is_completed, completed_at)
               VALUES (?, '2026-11-09', 1, '2026-11-09T12:00:00Z')""",
            (snapshot_id,),
        )

    assert (
        client.patch(
            f"/chores/{chore_id}",
            json={"name": "Laundry (revised)", "description": "New instructions"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"/chores/{chore_id}/checklist-items/{item['id']}",
            json={"label": "Fold and put away clothes"},
            headers=headers,
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/chores/{chore_id}/checklist-items/{item['id']}", headers=headers
        ).status_code
        == 204
    )

    with connect(database_path) as connection:
        assignment = connection.execute(
            "SELECT chore_name_snapshot, chore_description_snapshot "
            "FROM weekly_assignments WHERE id = ?",
            (assignment_id,),
        ).fetchone()
        snapshot = connection.execute(
            "SELECT source_checklist_item_id, label_snapshot "
            "FROM assignment_checklist_items WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        completion = connection.execute(
            "SELECT is_completed, completed_at FROM daily_checklist_completions "
            "WHERE assignment_checklist_item_id = ?",
            (snapshot_id,),
        ).fetchone()

    assert tuple(assignment) == ("Laundry", "Original")
    assert snapshot["source_checklist_item_id"] is None
    assert snapshot["label_snapshot"] == "Fold clothes"
    assert tuple(completion) == (1, "2026-11-09T12:00:00Z")


def test_checklist_items_can_be_created_and_updated_as_optional_or_required(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()
    chore_id = client.post("/chores", json={"name": "Kitchen"}, headers=headers).json()[
        "id"
    ]

    optional = client.post(
        f"/chores/{chore_id}/checklist-items",
        json={"label": "Wipe counters", "is_required": False},
        headers=headers,
    )
    default_required = client.post(
        f"/chores/{chore_id}/checklist-items",
        json={"label": "Sweep floor"},
        headers=headers,
    )

    assert optional.status_code == default_required.status_code == 201
    assert optional.json()["is_required"] is False
    assert default_required.json()["is_required"] is True
    optional_id = optional.json()["id"]
    required_id = default_required.json()["id"]

    updated_optional = client.patch(
        f"/chores/{chore_id}/checklist-items/{optional_id}",
        json={"is_required": True},
        headers=headers,
    )
    updated_required = client.patch(
        f"/chores/{chore_id}/checklist-items/{required_id}",
        json={"is_required": False},
        headers=headers,
    )

    assert updated_optional.status_code == updated_required.status_code == 200
    assert updated_optional.json()["is_required"] is True
    assert updated_required.json()["is_required"] is False

    chore = client.get(f"/chores/{chore_id}", headers=headers).json()
    assert [(item["id"], item["is_required"]) for item in chore["checklist_items"]] == [
        (optional_id, True),
        (required_id, False),
    ]

    invalid = client.post(
        f"/chores/{chore_id}/checklist-items",
        json={"label": "Take out trash", "is_required": "sometimes"},
        headers=headers,
    )
    assert invalid.status_code == 422

    with connect(database_path) as connection:
        stored = connection.execute(
            "SELECT is_required FROM chore_checklist_items ORDER BY position, id"
        ).fetchall()
    assert [row["is_required"] for row in stored] == [1, 0]


def test_chore_weight_defaults_validates_and_updates(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    headers = admin_headers()

    defaulted = client.post("/chores", json={"name": "Kitchen"}, headers=headers)
    assert defaulted.status_code == 201
    assert defaulted.json()["weight"] == 1

    weighted = client.post(
        "/chores", json={"name": "Yard", "weight": 7}, headers=headers
    )
    assert weighted.status_code == 201
    assert weighted.json()["weight"] == 7
    chore_id = weighted.json()["id"]

    listed = {
        chore["id"]: chore["weight"]
        for chore in client.get("/chores", headers=headers).json()
    }
    assert listed == {defaulted.json()["id"]: 1, chore_id: 7}
    assert client.get(f"/chores/{chore_id}", headers=headers).json()["weight"] == 7

    ten = client.patch(f"/chores/{chore_id}", json={"weight": 10}, headers=headers)
    assert ten.status_code == 200
    assert ten.json()["weight"] == 10

    zero = client.patch(f"/chores/{chore_id}", json={"weight": 0}, headers=headers)
    assert zero.status_code == 200
    assert zero.json()["weight"] == 0

    renamed = client.patch(
        f"/chores/{chore_id}", json={"name": "Yard work"}, headers=headers
    )
    assert renamed.status_code == 200
    assert renamed.json()["weight"] == 0

    for invalid in (-1, 11, "3", 2.5, True, None):
        response = client.patch(
            f"/chores/{chore_id}", json={"weight": invalid}, headers=headers
        )
        assert response.status_code == 422, invalid
        assert client.get(f"/chores/{chore_id}", headers=headers).json()["weight"] == 0

    for invalid in (-1, 11, "3", 2.5, True, None):
        response = client.post(
            "/chores",
            json={"name": "Invalid weight", "weight": invalid},
            headers=headers,
        )
        assert response.status_code == 422, invalid


def test_service_validates_weight_for_direct_callers(tmp_path, monkeypatch):
    _, database_path = prepare_client(tmp_path, monkeypatch)
    service = FamilyChoreManagementService(
        SQLiteFamilyChoreManagementPersistence(database_path)
    )

    for value in (0, 10):
        chore = service.create_chore(f"Chore {value}", "", False, value)
        assert chore["weight"] == value

    for invalid in (-1, 11, 2.5, True, "3"):
        with pytest.raises(ManagementError) as error:
            service.create_chore("Invalid weight", "", False, invalid)
        assert error.value.code == "invalid_weight"

    chore = service.create_chore("Mutable weight", "", False)
    assert chore["weight"] == 1
    for invalid in (-1, 11, 2.5, True, "3"):
        with pytest.raises(ManagementError) as error:
            service.update_chore(chore["id"], {"weight": invalid})
        assert error.value.code == "invalid_weight"
    assert service.get_chore(chore["id"])["weight"] == 1
