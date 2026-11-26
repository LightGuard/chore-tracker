"""Integration tests for administrator manual assignment generation."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.weekly_assignments import (
    SQLiteWeeklyAssignmentPersistence,
)
from chore_tracker.application.services.weekly_assignment_generation import (
    WeeklyAssignmentGenerationService,
)
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
TODAY = date(2026, 11, 25)
CURRENT_WEEK = date(2026, 11, 23)
PAST_WEEK = date(2026, 11, 16)
FUTURE_WEEK = date(2026, 12, 7)
MEMBERS = ("Alex", "Zoe")
CHORES = (
    ("Bathroom", "Clean the bathroom", "Clean sink"),
    ("Kitchen", "Clean the kitchen", "Sweep floor"),
    ("Laundry", "Wash the clothes", "Sort laundry"),
)


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "assignments-api.db"
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
        "assignment_generation_service_factory",
        lambda: WeeklyAssignmentGenerationService(
            SQLiteWeeklyAssignmentPersistence(database_path),
            "America/Denver",
            today=lambda: TODAY,
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


def seed_catalog(
    database_path: Path,
    *,
    members: tuple[str, ...] = MEMBERS,
    chores: tuple[tuple[str, str, str], ...] = CHORES,
) -> None:
    with connect(database_path) as connection:
        for display_name in members:
            connection.execute(
                "INSERT INTO family_members (display_name, is_active) VALUES (?, 1)",
                (display_name,),
            )
        for name, description, label in chores:
            chore_id = connection.execute(
                """
                INSERT INTO chores (name, description, is_active)
                VALUES (?, ?, 1)
                """,
                (name, description),
            ).lastrowid
            connection.execute(
                """
                INSERT INTO chore_checklist_items (
                    chore_id, label, position, is_active
                )
                VALUES (?, ?, 0, 1)
                """,
                (chore_id, label),
            )


def generate(client: TestClient, week: date, *, origin: bool = True):
    headers = {"Origin": ORIGIN} if origin else {}
    return client.post(
        "/assignments",
        json={"week": week.isoformat()},
        headers=headers,
    )


def count(database_path: Path, table: str) -> int:
    with connect(database_path) as connection:
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_assignment_generation_requires_an_administrator_and_same_origin(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(database_path)

    unauthenticated = TestClient(app)
    assert generate(unauthenticated, CURRENT_WEEK).status_code == 401
    assert generate(client, CURRENT_WEEK, origin=False).status_code == 403
    assert generate(client, CURRENT_WEEK).status_code == 201


def test_generation_normalizes_the_week_and_reuses_existing_assignments(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(database_path)

    first = generate(client, date(2026, 11, 25))
    assert first.status_code == 201
    payload = first.json()
    assert payload["week_start"] == CURRENT_WEEK.isoformat()
    assert payload["week_end"] == date(2026, 11, 29).isoformat()
    assert payload["status"] == "generated"
    assert payload["assignment_count"] == 2
    assert [
        assignment["family_member_name"] for assignment in payload["assignments"]
    ] == [
        "Alex",
        "Zoe",
    ]
    assert [assignment["chore_name"] for assignment in payload["assignments"]] == [
        "Bathroom",
        "Kitchen",
    ]
    assert all(assignment["chore_weight"] == 1 for assignment in payload["assignments"])
    assignment_ids = [assignment["id"] for assignment in payload["assignments"]]

    second = generate(client, CURRENT_WEEK)
    assert second.status_code == 200
    repeated = second.json()
    assert repeated["status"] == "already_exists"
    assert repeated["assignment_count"] == 2
    assert [assignment["id"] for assignment in repeated["assignments"]] == (
        assignment_ids
    )
    assert count(database_path, "weekly_assignments") == 2
    assert count(database_path, "weekly_assignment_generations") == 1
    assert count(database_path, "assignment_rotation_state") == 1


def test_generation_returns_the_snapshotted_chore_weight(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(database_path)
    with connect(database_path) as connection:
        connection.execute("UPDATE chores SET weight = 7 WHERE name = 'Bathroom'")

    first = generate(client, CURRENT_WEEK)
    assert first.status_code == 201
    generated = {
        assignment["chore_name"]: assignment["chore_weight"]
        for assignment in first.json()["assignments"]
    }
    assert generated["Bathroom"] == 7

    with connect(database_path) as connection:
        connection.execute("UPDATE chores SET weight = 9 WHERE name = 'Bathroom'")

    repeated = generate(client, CURRENT_WEEK)
    assert repeated.status_code == 200
    preserved = {
        assignment["chore_name"]: assignment["chore_weight"]
        for assignment in repeated.json()["assignments"]
    }
    assert preserved["Bathroom"] == 7


def test_generation_rejects_a_future_week_before_the_anchor_exists(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(database_path)

    response = generate(client, FUTURE_WEEK)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "rotation anchor" in detail
    assert CURRENT_WEEK.isoformat() in detail
    assert count(database_path, "weekly_assignment_generations") == 0
    assert count(database_path, "assignment_rotation_state") == 0


def test_generation_allows_a_future_week_after_the_anchor_exists(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(database_path)

    assert generate(client, CURRENT_WEEK).status_code == 201
    response = generate(client, FUTURE_WEEK)

    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "generated"
    assert payload["week_start"] == FUTURE_WEEK.isoformat()
    assert count(database_path, "weekly_assignment_generations") == 2


def test_generation_rejects_a_week_before_the_anchor(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(database_path)
    assert generate(client, CURRENT_WEEK).status_code == 201

    response = generate(client, PAST_WEEK)

    assert response.status_code == 409
    assert "rotation anchor" in response.json()["detail"]
    assert count(database_path, "weekly_assignment_generations") == 1


def test_generation_reports_insufficient_active_chores(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(
        database_path,
        members=("Alex", "Zoe"),
        chores=(("Bathroom", "Clean the bathroom", "Clean sink"),),
    )

    response = generate(client, CURRENT_WEEK)

    assert response.status_code == 409
    assert "require at least" in response.json()["detail"]
    assert count(database_path, "weekly_assignment_generations") == 0
    assert count(database_path, "assignment_rotation_state") == 0


def test_generation_validates_the_week_body_and_date_range(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_catalog(database_path)

    assert (
        client.post("/assignments", json={}, headers={"Origin": ORIGIN}).status_code
        == 422
    )
    assert (
        client.post(
            "/assignments",
            json={"week": "not-a-date"},
            headers={"Origin": ORIGIN},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/assignments",
            json={"week": "2026-11-23", "extra": True},
            headers={"Origin": ORIGIN},
        ).status_code
        == 422
    )
    overflow = generate(client, date(9999, 12, 31))
    assert overflow.status_code == 422
    assert "9999-12-31" in overflow.json()["detail"]
    assert count(database_path, "weekly_assignment_generations") == 0
