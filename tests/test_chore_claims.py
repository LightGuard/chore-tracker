"""Integration tests for one-day child chore claims."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
import chore_tracker.api.routes.child_views as child_views
from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.child_views import SQLiteChildViewsPersistence
from chore_tracker.adapters.sqlite.weekly_assignments import (
    SQLiteWeeklyAssignmentPersistence,
)
from chore_tracker.application.services.child_views import (
    ChildViewsService,
    ChoreAlreadyClaimed,
)
from chore_tracker.application.services.weekly_assignment_generation import (
    WeeklyAssignmentGenerationService,
)
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
TODAY = datetime(2026, 11, 25, 12, tzinfo=ZoneInfo("America/Denver"))
WEEK_START = "2026-11-23"
WEEK_END = "2026-11-29"


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls.fromtimestamp(TODAY.timestamp(), tz=tz)


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "claims.db"
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


def seed_catalog(database_path: Path) -> SimpleNamespace:
    with connect(database_path) as connection:
        alex = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Alex', 1)"
        ).lastrowid
        zoe = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Zoe', 1)"
        ).lastrowid
        quinn = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Quinn', 0)"
        ).lastrowid
        chores = {}
        for name, description, weight, is_active in (
            ("Kitchen", "Cook dinner", 1, 1),
            ("Yard", "Rake leaves", 1, 1),
            ("Bathroom", "Scrub the bathroom", 2, 1),
            ("Garage", "Sweep the garage", 0, 1),
            ("Storage", "Sort boxes", 1, 0),
        ):
            chores[name] = connection.execute(
                """INSERT INTO chores (name, description, weight, is_active)
                   VALUES (?, ?, ?, ?)""",
                (name, description, weight, is_active),
            ).lastrowid
        for member, chore_name in ((alex, "Kitchen"), (zoe, "Yard")):
            connection.execute(
                """INSERT INTO weekly_assignments
                   (family_member_id, chore_id, week_start, week_end,
                    chore_name_snapshot, chore_description_snapshot,
                    chore_weight_snapshot)
                   VALUES (?, ?, ?, ?, ?, '', 1)""",
                (member, chores[chore_name], WEEK_START, WEEK_END, chore_name),
            )
    return SimpleNamespace(
        alex=alex,
        zoe=zoe,
        quinn=quinn,
        chores=chores,
    )


def insert_claim(
    database_path: Path,
    *,
    family_member_id: int,
    chore_id: int,
    claim_date: str = "2026-11-25",
    claimed_at: str = "2026-11-25T10:00:00Z",
) -> int:
    with connect(database_path) as connection:
        return connection.execute(
            """INSERT INTO daily_chore_claims
               (family_member_id, chore_id, claim_date, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot,
                chore_weight_snapshot, claimed_at)
               VALUES (?, ?, ?, ?, ?, 'Bathroom', 'Scrub the bathroom', 2, ?)""",
            (
                family_member_id,
                chore_id,
                claim_date,
                WEEK_START,
                WEEK_END,
                claimed_at,
            ),
        ).lastrowid


def available_names(client: TestClient, member_id: int) -> list[str]:
    response = client.get(f"/family-members/{member_id}/available-chores")
    assert response.status_code == 200
    return [chore["name"] for chore in response.json()["chores"]]


def test_available_chores_are_active_unassigned_and_still_claimable(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)

    response = client.get(f"/family-members/{catalog.alex}/available-chores")

    assert response.status_code == 200
    assert response.json() == {
        "claim_date": "2026-11-25",
        "chores": [
            {
                "id": catalog.chores["Bathroom"],
                "name": "Bathroom",
                "description": "Scrub the bathroom",
                "weight": 2,
            },
            {
                "id": catalog.chores["Garage"],
                "name": "Garage",
                "description": "Sweep the garage",
                "weight": 0,
            },
        ],
    }

    insert_claim(
        database_path,
        family_member_id=catalog.zoe,
        chore_id=catalog.chores["Bathroom"],
        claimed_at="2026-11-25T11:00:00Z",
    )

    assert available_names(client, catalog.alex) == ["Garage"]


def test_availability_returns_an_empty_list_when_every_chore_is_taken(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)
    insert_claim(
        database_path,
        family_member_id=catalog.zoe,
        chore_id=catalog.chores["Bathroom"],
    )
    with connect(database_path) as connection:
        connection.execute(
            "UPDATE chores SET is_active = 0 WHERE id = ?",
            (catalog.chores["Garage"],),
        )

    response = client.get(f"/family-members/{catalog.alex}/available-chores")

    assert response.status_code == 200
    assert response.json() == {"claim_date": "2026-11-25", "chores": []}


def test_availability_and_claims_are_day_specific(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)

    claim = client.post(
        f"/family-members/{catalog.alex}/claimed-chores",
        json={"chore_id": catalog.chores["Bathroom"]},
    )
    assert claim.status_code == 201
    assert claim.json()["claim_date"] == "2026-11-25"
    assert available_names(client, catalog.alex) == ["Garage"]

    class TomorrowDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 26, 12, tzinfo=tz)

    monkeypatch.setattr(child_views, "datetime", TomorrowDateTime)

    response = client.get(f"/family-members/{catalog.alex}/available-chores")
    assert response.status_code == 200
    assert response.json()["claim_date"] == "2026-11-26"
    assert [chore["name"] for chore in response.json()["chores"]] == [
        "Bathroom",
        "Garage",
    ]
    assert client.get(f"/family-members/{catalog.alex}/claimed-chores").json() == {
        "claim_date": "2026-11-26",
        "claims": [],
    }

    next_day_claim = client.post(
        f"/family-members/{catalog.zoe}/claimed-chores",
        json={"chore_id": catalog.chores["Bathroom"]},
    )
    assert next_day_claim.status_code == 201
    assert next_day_claim.json()["claim_date"] == "2026-11-26"
    assert next_day_claim.json()["week_start"] == WEEK_START
    assert next_day_claim.json()["week_end"] == WEEK_END

    with connect(database_path) as connection:
        rows = connection.execute(
            """SELECT family_member_id, claim_date
               FROM daily_chore_claims ORDER BY id"""
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        (catalog.alex, "2026-11-25"),
        (catalog.zoe, "2026-11-26"),
    ]


def test_successful_claim_creates_an_immutable_one_day_snapshot(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)

    response = client.post(
        f"/family-members/{catalog.alex}/claimed-chores",
        json={"chore_id": catalog.chores["Bathroom"]},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload == {
        "id": payload["id"],
        "family_member_id": catalog.alex,
        "chore_id": catalog.chores["Bathroom"],
        "claim_date": "2026-11-25",
        "week_start": WEEK_START,
        "week_end": WEEK_END,
        "chore_name": "Bathroom",
        "chore_description": "Scrub the bathroom",
        "chore_weight": 2,
        "claimed_at": payload["claimed_at"],
    }
    assert payload["claimed_at"].endswith("Z")
    assert (
        datetime.fromisoformat(payload["claimed_at"].replace("Z", "+00:00")).tzinfo
        is not None
    )

    claimed = client.get(f"/family-members/{catalog.alex}/claimed-chores")
    assert claimed.status_code == 200
    assert claimed.json() == {"claim_date": "2026-11-25", "claims": [payload]}
    assert available_names(client, catalog.alex) == ["Garage"]

    with connect(database_path) as connection:
        connection.execute(
            """UPDATE chores
               SET name = 'Bathroom v2', description = 'Updated',
                   weight = 9
               WHERE id = ?""",
            (catalog.chores["Bathroom"],),
        )

    claimed_again = client.get(f"/family-members/{catalog.alex}/claimed-chores")
    assert claimed_again.json()["claims"][0]["chore_name"] == "Bathroom"
    assert claimed_again.json()["claims"][0]["chore_description"] == (
        "Scrub the bathroom"
    )
    assert claimed_again.json()["claims"][0]["chore_weight"] == 2

    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM daily_chore_claims").fetchone()[0]
            == 1
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_assignments").fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM weekly_assignment_generations"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM assignment_checklist_items"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_checklist_completions"
            ).fetchone()[0]
            == 0
        )


def test_claim_rejects_unknown_inactive_assigned_and_taken_chores(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)

    def claim(member_id: int, chore_id: int):
        return client.post(
            f"/family-members/{member_id}/claimed-chores",
            json={"chore_id": chore_id},
        )

    unknown_member = claim(999, catalog.chores["Bathroom"])
    assert unknown_member.status_code == 404
    assert unknown_member.json()["detail"] == "Family member was not found"

    inactive_member = claim(catalog.quinn, catalog.chores["Bathroom"])
    assert inactive_member.status_code == 409
    assert inactive_member.json()["detail"] == "Family member is inactive"

    unknown_chore = claim(catalog.alex, 999)
    assert unknown_chore.status_code == 404
    assert unknown_chore.json()["detail"] == "Chore was not found"

    inactive_chore = claim(catalog.alex, catalog.chores["Storage"])
    assert inactive_chore.status_code == 409
    assert inactive_chore.json()["detail"] == "Chore is not active"

    assigned_chore = claim(catalog.alex, catalog.chores["Kitchen"])
    assert assigned_chore.status_code == 409
    assert assigned_chore.json()["detail"] == (
        "Chore is already assigned for this week"
    )

    insert_claim(
        database_path,
        family_member_id=catalog.zoe,
        chore_id=catalog.chores["Bathroom"],
    )
    taken_chore = claim(catalog.alex, catalog.chores["Bathroom"])
    assert taken_chore.status_code == 409
    assert taken_chore.json()["detail"] == (
        "Chore has already been claimed for this day"
    )

    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM daily_chore_claims").fetchone()[0]
            == 1
        )


def test_claim_is_scoped_to_the_profile_in_the_path(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)

    on_behalf_of_another = client.post(
        f"/family-members/{catalog.alex}/claimed-chores",
        json={
            "chore_id": catalog.chores["Bathroom"],
            "family_member_id": catalog.zoe,
        },
    )
    assert on_behalf_of_another.status_code == 422

    claim = client.post(
        f"/family-members/{catalog.alex}/claimed-chores",
        json={"chore_id": catalog.chores["Bathroom"]},
    )
    assert claim.status_code == 201
    assert claim.json()["family_member_id"] == catalog.alex

    assert (
        client.get(f"/family-members/{catalog.zoe}/claimed-chores").json()["claims"]
        == []
    )
    assert (
        len(
            client.get(f"/family-members/{catalog.alex}/claimed-chores").json()[
                "claims"
            ]
        )
        == 1
    )


def test_availability_and_claims_reject_unknown_or_inactive_profiles(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)

    assert client.get("/family-members/999/available-chores").status_code == 404
    assert client.get("/family-members/999/claimed-chores").status_code == 404
    assert (
        client.get(f"/family-members/{catalog.quinn}/available-chores").status_code
        == 409
    )
    assert (
        client.get(f"/family-members/{catalog.quinn}/claimed-chores").status_code == 409
    )


def test_claim_does_not_change_weekly_rotation_or_generation(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    catalog = seed_catalog(database_path)
    with connect(database_path) as connection:
        before = connection.execute(
            """SELECT id, family_member_id, chore_id, chore_name_snapshot
               FROM weekly_assignments ORDER BY id"""
        ).fetchall()

    response = client.post(
        f"/family-members/{catalog.alex}/claimed-chores",
        json={"chore_id": catalog.chores["Bathroom"]},
    )
    assert response.status_code == 201

    with connect(database_path) as connection:
        after = connection.execute(
            """SELECT id, family_member_id, chore_id, chore_name_snapshot
               FROM weekly_assignments ORDER BY id"""
        ).fetchall()
    assert after == before

    service = WeeklyAssignmentGenerationService(
        SQLiteWeeklyAssignmentPersistence(database_path),
        "America/Denver",
        today=lambda: TODAY.date(),
    )
    generated = service.generate(date(2026, 11, 30))

    assert generated.created is True
    assert {
        (assignment.family_member_id, assignment.chore_id)
        for assignment in generated.assignments
    } == {
        (catalog.alex, catalog.chores["Bathroom"]),
        (catalog.zoe, catalog.chores["Garage"]),
    }


def test_competing_claims_create_exactly_one_one_day_assignment(tmp_path):
    database_path = tmp_path / "concurrent-claims.db"
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    command.upgrade(config, "head")
    catalog = seed_catalog(database_path)
    barrier = threading.Barrier(2)

    def attempt(member_id: int) -> str:
        barrier.wait(timeout=5)
        service = ChildViewsService(SQLiteChildViewsPersistence(database_path))
        try:
            service.claim_chore(member_id, catalog.chores["Bathroom"], TODAY.date())
        except ChoreAlreadyClaimed:
            return "conflict"
        return "claimed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(attempt, catalog.alex),
            executor.submit(attempt, catalog.zoe),
        ]
        results = [future.result(timeout=15) for future in futures]

    assert sorted(results) == ["claimed", "conflict"]
    with connect(database_path) as connection:
        rows = connection.execute(
            """SELECT family_member_id, chore_id, claim_date
               FROM daily_chore_claims"""
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        (
            catalog.alex if results[0] == "claimed" else catalog.zoe,
            catalog.chores["Bathroom"],
            "2026-11-25",
        )
    ]
