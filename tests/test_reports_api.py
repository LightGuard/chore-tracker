"""Integration tests for administrator weekly report endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
import chore_tracker.application.services.weekly_reports as weekly_reports_module
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
REWARDED_AT = datetime(2026, 11, 26, 15, 30, tzinfo=UTC)


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
    assert (
        client.put(
            f"/reports/{WEEK_START.isoformat()}/entries/1/reward",
            headers={"Origin": ORIGIN},
        ).status_code
        == 401
    )
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


def _freeze_reward_clock(monkeypatch, moment: datetime = REWARDED_AT) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls.fromtimestamp(moment.timestamp(), tz=tz)

    monkeypatch.setattr(weekly_reports_module, "datetime", FrozenDateTime)


def _report_entries(client, week_start: date = WEEK_START) -> list[dict]:
    response = client.get(f"/reports/{week_start.isoformat()}?limit=100")
    assert response.status_code == 200
    return response.json()["entries"]


def _entry_id(client, family_member_name: str, week_start: date = WEEK_START) -> int:
    return next(
        entry["id"]
        for entry in _report_entries(client, week_start)
        if entry["family_member_name"] == family_member_name
    )


def _reward_url(week_start: date, entry_id: int) -> str:
    return f"/reports/{week_start.isoformat()}/entries/{entry_id}/reward"


def test_report_entries_expose_unrewarded_state_without_a_reward_record(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)

    payload = client.get(f"/reports/{WEEK_START.isoformat()}?limit=100").json()

    assert payload["total"] == 3
    assert all(entry["reward"] is None for entry in payload["entries"])
    headers = client.get("/reports").json()
    assert all("reward" not in header for header in headers)


def test_administrator_marks_a_reward_and_reads_persisted_audit_details(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)
    _freeze_reward_clock(monkeypatch)
    administrator = client.get("/auth/me").json()
    entry_id = _entry_id(client, "Alex")

    response = client.put(_reward_url(WEEK_START, entry_id), headers={"Origin": ORIGIN})

    expected_reward = {
        "rewarded_at": "2026-11-26T15:30:00Z",
        "rewarded_by": {
            "administrator_id": administrator["id"],
            "email": "admin@example.test",
        },
    }
    assert response.status_code == 200
    assert response.json() == expected_reward

    # Any date in the reporting week resolves the same report and entry.
    normalized_entry_id = _entry_id(client, "Alex", WEEK_START + timedelta(days=3))
    assert normalized_entry_id == entry_id
    entries = _report_entries(client, WEEK_START)
    alex = next(entry for entry in entries if entry["family_member_name"] == "Alex")
    assert alex["reward"] == expected_reward
    assert [
        entry["family_member_name"] for entry in entries if entry["reward"] is not None
    ] == ["Alex"]

    with connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT weekly_report_entry_id, rewarded_at,
                   rewarded_by_administrator_id
            FROM weekly_report_rewards
            """
        ).fetchone()
    assert dict(row) == {
        "weekly_report_entry_id": entry_id,
        "rewarded_at": "2026-11-26T15:30:00.000Z",
        "rewarded_by_administrator_id": administrator["id"],
    }


def test_repeated_marking_keeps_the_first_audit_record(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)
    _freeze_reward_clock(monkeypatch)
    url = _reward_url(WEEK_START, _entry_id(client, "Alex"))

    first = client.put(url, headers={"Origin": ORIGIN})
    assert first.status_code == 200

    _freeze_reward_clock(monkeypatch, REWARDED_AT + timedelta(hours=2))
    repeated = client.put(url, headers={"Origin": ORIGIN})

    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_rewards").fetchone()[
                0
            ]
            == 1
        )


def test_rewards_are_independent_per_child_and_reporting_week(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)
    _freeze_reward_clock(monkeypatch)
    target_alex = _entry_id(client, "Alex", WEEK_START)
    previous_sam = _entry_id(client, "Sam", PREVIOUS_WEEK_START)

    assert (
        client.put(
            _reward_url(WEEK_START, target_alex), headers={"Origin": ORIGIN}
        ).status_code
        == 200
    )
    assert (
        client.put(
            _reward_url(PREVIOUS_WEEK_START, previous_sam),
            headers={"Origin": ORIGIN},
        ).status_code
        == 200
    )

    target_entries = {
        entry["family_member_name"]: entry["reward"]
        for entry in _report_entries(client, WEEK_START)
    }
    previous_entries = {
        entry["family_member_name"]: entry["reward"]
        for entry in _report_entries(client, PREVIOUS_WEEK_START)
    }
    assert target_entries["Alex"] is not None
    assert target_entries["Sam"] is None
    assert previous_entries["Sam"] is not None
    assert previous_entries["Alex"] is None
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_rewards").fetchone()[
                0
            ]
            == 2
        )


def test_reward_marking_requires_administrator_and_trusted_origin(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)
    url = _reward_url(WEEK_START, _entry_id(client, "Alex"))

    assert client.put(url, headers={"Origin": "http://evil.test"}).status_code == 403
    assert client.put(url).status_code == 403

    client.post("/auth/logout", headers={"Origin": ORIGIN})

    assert client.put(url, headers={"Origin": ORIGIN}).status_code == 401
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_rewards").fetchone()[
                0
            ]
            == 0
        )


def test_reward_marking_rejects_unknown_report_entry_scopes(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    seed_reports(database_path)
    entry_id = _entry_id(client, "Alex")
    headers = {"Origin": ORIGIN}

    assert (
        client.put(
            _reward_url(date(2026, 12, 7), entry_id), headers=headers
        ).status_code
        == 404
    )
    assert (
        client.put(_reward_url(WEEK_START, 999999), headers=headers).status_code == 404
    )
    assert (
        client.put(
            _reward_url(PREVIOUS_WEEK_START, entry_id), headers=headers
        ).status_code
        == 404
    )
    assert (
        client.put(_reward_url(WEEK_START, 2**63), headers=headers).status_code == 422
    )
    assert (
        client.put(
            f"/reports/not-a-date/entries/{entry_id}/reward", headers=headers
        ).status_code
        == 422
    )
    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_report_rewards").fetchone()[
                0
            ]
            == 0
        )
