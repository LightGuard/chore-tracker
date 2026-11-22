"""Integration tests for administrator weekly report endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.weekly_reports import SQLiteWeeklyReportPersistence
from chore_tracker.application.services.weekly_reports import (
    WeeklyReport,
    WeeklyReportService,
)
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
WEEK_START = date(2026, 11, 16)
PREVIOUS_WEEK_START = WEEK_START - timedelta(days=7)
TARGET_GENERATED_AT = datetime(2026, 11, 23, 10, 0, tzinfo=UTC)
PREVIOUS_GENERATED_AT = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "reports-api.db"
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
        "report_service_factory",
        lambda: WeeklyReportService(
            SQLiteWeeklyReportPersistence(database_path), "America/Denver"
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


def _assign(
    connection,
    *,
    family_member_id: int,
    chore_id: int,
    checklist_item_ids: list[int],
    week_start: date,
) -> tuple[int, list[int]]:
    week_end = week_start + timedelta(days=6)
    assignment_id = connection.execute(
        """
        INSERT INTO weekly_assignments (
            family_member_id, chore_id, week_start, week_end,
            chore_name_snapshot, chore_description_snapshot
        )
        VALUES (?, ?, ?, ?, 'Kitchen', 'Clean the kitchen')
        """,
        (
            family_member_id,
            chore_id,
            week_start.isoformat(),
            week_end.isoformat(),
        ),
    ).lastrowid
    snapshot_ids = []
    for position, item_id in enumerate(checklist_item_ids):
        label = connection.execute(
            "SELECT label FROM chore_checklist_items WHERE id = ?", (item_id,)
        ).fetchone()["label"]
        snapshot_ids.append(
            connection.execute(
                """
                INSERT INTO assignment_checklist_items (
                    weekly_assignment_id, source_checklist_item_id,
                    label_snapshot, position
                )
                VALUES (?, ?, ?, ?)
                """,
                (assignment_id, item_id, label, position),
            ).lastrowid
        )
    return assignment_id, snapshot_ids


def _complete(connection, snapshot_ids: list[int], day: date, positions: set[int]):
    for position, item_id in enumerate(snapshot_ids):
        completed = position in positions
        connection.execute(
            """
            INSERT INTO daily_checklist_completions (
                assignment_checklist_item_id, completion_date,
                is_completed, completed_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                item_id,
                day.isoformat(),
                int(completed),
                f"{day.isoformat()}T18:00:00Z" if completed else None,
            ),
        )


def seed_reports(database_path: Path) -> tuple[WeeklyReport, WeeklyReport]:
    with connect(database_path) as connection:
        member_ids = [
            connection.execute(
                "INSERT INTO family_members (display_name) VALUES (?)", (name,)
            ).lastrowid
            for name in ("Alex", "Sam", "Riley")
        ]
        chore_id = connection.execute(
            """
            INSERT INTO chores (name, description, is_active)
            VALUES ('Kitchen', 'Clean the kitchen', 1)
            """
        ).lastrowid
        item_ids = [
            connection.execute(
                """
                INSERT INTO chore_checklist_items (
                    chore_id, label, position, is_active
                )
                VALUES (?, ?, ?, 1)
                """,
                (chore_id, label, position),
            ).lastrowid
            for position, label in enumerate(("Sweep floor", "Wipe counters"))
        ]
        target_snapshots = []
        previous_snapshots = []
        for family_member_id in member_ids:
            target_snapshots.append(
                _assign(
                    connection,
                    family_member_id=family_member_id,
                    chore_id=chore_id,
                    checklist_item_ids=item_ids,
                    week_start=WEEK_START,
                )[1]
            )
            previous_snapshots.append(
                _assign(
                    connection,
                    family_member_id=family_member_id,
                    chore_id=chore_id,
                    checklist_item_ids=item_ids,
                    week_start=PREVIOUS_WEEK_START,
                )[1]
            )

        for day_index in range(7):
            day = WEEK_START + timedelta(days=day_index)
            previous_day = PREVIOUS_WEEK_START + timedelta(days=day_index)
            _complete(connection, target_snapshots[0], day, {0, 1})
            if day_index < 4:
                _complete(connection, target_snapshots[1], day, {0, 1})
            _complete(connection, previous_snapshots[0], previous_day, {0, 1})

    service = WeeklyReportService(
        SQLiteWeeklyReportPersistence(database_path), "America/Denver"
    )
    previous = service.generate(PREVIOUS_WEEK_START, generated_at=PREVIOUS_GENERATED_AT)
    target = service.generate(WEEK_START, generated_at=TARGET_GENERATED_AT)
    return target, previous


def test_report_endpoints_require_an_administrator_session(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)

    assert client.get("/reports").status_code == 200
    assert client.get(f"/reports/{WEEK_START.isoformat()}").status_code == 200

    client.post("/auth/logout", headers={"Origin": ORIGIN})

    assert client.get("/reports").status_code == 401
    assert client.get(f"/reports/{WEEK_START.isoformat()}").status_code == 401
    client.cookies.set("chore_tracker_session", "not-a-real-session")
    assert client.get("/reports").status_code == 401


def test_administrator_lists_reports_newest_first(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    target, previous = seed_reports(database_path)

    response = client.get("/reports")

    assert response.status_code == 200
    reports = response.json()
    assert [report["week_start"] for report in reports] == [
        WEEK_START.isoformat(),
        PREVIOUS_WEEK_START.isoformat(),
    ]
    assert [report["id"] for report in reports] == [target.id, previous.id]
    assert reports[0]["summary"] == {
        "family_member_count": 3,
        "total_days": 21,
        "completed_days": 11,
        "incomplete_days": 10,
    }
    assert reports[0]["generated_at"].endswith("Z")
    assert reports[0]["week_end"] == (WEEK_START + timedelta(days=6)).isoformat()


def test_administrator_reads_persisted_report_entries_and_pagination(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    target, _ = seed_reports(database_path)

    first_page = client.get(
        f"/reports/{target.week_start.isoformat()}?limit=2&offset=0"
    )
    assert first_page.status_code == 200
    payload = first_page.json()
    assert payload["total"] == 3
    assert payload["limit"] == 2
    assert payload["offset"] == 0
    assert payload["summary"]["completed_days"] == 11
    assert [entry["family_member_name"] for entry in payload["entries"]] == [
        "Alex",
        "Riley",
    ]
    assert len(payload["entries"][0]["days"]) == 7
    assert payload["entries"][0]["chore_name"] == "Kitchen"

    second_page = client.get(
        f"/reports/{target.week_start.isoformat()}?limit=2&offset=2"
    )
    assert second_page.status_code == 200
    second_payload = second_page.json()
    assert second_payload["total"] == 3
    assert [entry["family_member_name"] for entry in second_payload["entries"]] == [
        "Sam"
    ]

    with connect(database_path) as connection:
        connection.execute(
            "UPDATE family_members SET display_name = 'Alex Renamed' WHERE id = 1"
        )
        connection.execute("UPDATE chores SET name = 'Renamed chore' WHERE id = 1")
        connection.execute("DELETE FROM daily_checklist_completions")

    persisted = client.get(
        f"/reports/{target.week_start.isoformat()}?limit=2&offset=0"
    ).json()
    assert [entry["family_member_name"] for entry in persisted["entries"]] == [
        "Alex",
        "Riley",
    ]
    assert persisted["entries"][0]["chore_name"] == "Kitchen"
    assert persisted["entries"][0]["days"][0]["status"] == "complete"
    assert persisted["summary"] == payload["summary"]


def test_report_endpoint_returns_not_found_and_validates_pagination(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)

    assert client.get("/reports/2026-12-07").status_code == 404
    for query in ("limit=0", "limit=101", "offset=-1"):
        assert (
            client.get(f"/reports/{WEEK_START.isoformat()}?{query}").status_code == 422
        )
