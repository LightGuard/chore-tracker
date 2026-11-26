"""Integration tests for the after-20:00 takeover and claim completion rules."""

from __future__ import annotations

import sqlite3
import threading
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
from chore_tracker.adapters.sqlite.child_views import SQLiteChildViewsPersistence
from chore_tracker.application.services.child_views import (
    ChildViewsService,
    ChoreAlreadyClaimed,
)
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
TODAY = "2026-11-25"
WEEK_START = "2026-11-23"
WEEK_END = "2026-11-29"


def _frozen_datetime(hour: int) -> type[datetime]:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 25, hour, 0, tzinfo=tz)

    return FrozenDateTime


def prepare_client(tmp_path, monkeypatch, hour: int = 12):
    database_path = tmp_path / "claim-completions.db"
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
    monkeypatch.setattr(child_views, "datetime", _frozen_datetime(hour))
    return TestClient(app), database_path


def seed(database_path: Path) -> SimpleNamespace:
    """Two assigned chores, one unassigned chore, and one inactive chore."""
    with connect(database_path) as connection:
        alex = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Alex', 1)"
        ).lastrowid
        zoe = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Zoe', 1)"
        ).lastrowid
        riley = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Riley', 1)"
        ).lastrowid
        quinn = connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES ('Quinn', 0)"
        ).lastrowid
        chores = {}
        for name, description, weight, is_active in (
            ("Kitchen", "Cook dinner", 2, 1),
            ("Yard", "Rake leaves", 1, 1),
            ("Bathroom", "Scrub the bathroom", 3, 1),
            ("Storage", "Sort boxes", 1, 0),
        ):
            chores[name] = connection.execute(
                """INSERT INTO chores (name, description, weight, is_active)
                   VALUES (?, ?, ?, ?)""",
                (name, description, weight, is_active),
            ).lastrowid
        assignments = {}
        for member, chore_name, weight in (
            (alex, "Kitchen", 2),
            (zoe, "Yard", 1),
        ):
            assignments[chore_name] = connection.execute(
                """INSERT INTO weekly_assignments
                   (family_member_id, chore_id, week_start, week_end,
                    chore_name_snapshot, chore_description_snapshot,
                    chore_weight_snapshot)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    member,
                    chores[chore_name],
                    WEEK_START,
                    WEEK_END,
                    chore_name,
                    f"{chore_name} description",
                    weight,
                ),
            ).lastrowid
        kitchen_items = []
        for position, label in enumerate(("Wipe counters", "Sweep floor")):
            kitchen_items.append(
                connection.execute(
                    """INSERT INTO assignment_checklist_items
                       (weekly_assignment_id, label_snapshot, position, is_required)
                       VALUES (?, ?, ?, 1)""",
                    (assignments["Kitchen"], label, position),
                ).lastrowid
            )
        yard_item = connection.execute(
            """INSERT INTO assignment_checklist_items
               (weekly_assignment_id, label_snapshot, position, is_required)
               VALUES (?, 'Rake leaves', 0, 1)""",
            (assignments["Yard"],),
        ).lastrowid
    return SimpleNamespace(
        alex=alex,
        zoe=zoe,
        riley=riley,
        quinn=quinn,
        chores=chores,
        assignments=assignments,
        kitchen_items=kitchen_items,
        yard_item=yard_item,
    )


def complete_item(database_path: Path, item_id: int, day: str = TODAY) -> None:
    with connect(database_path) as connection:
        connection.execute(
            """INSERT INTO daily_checklist_completions
               (assignment_checklist_item_id, completion_date,
                is_completed, completed_at)
               VALUES (?, ?, 1, ?)""",
            (item_id, day, f"{day}T12:00:00Z"),
        )


def available(client, member_id: int) -> list[dict]:
    response = client.get(f"/family-members/{member_id}/available-chores")
    assert response.status_code == 200, response.text
    return response.json()["chores"]


def claim(client, member_id: int, chore_id: int):
    return client.post(
        f"/family-members/{member_id}/claimed-chores",
        json={"chore_id": chore_id},
    )


def test_before_2000_only_unassigned_active_chores_are_available(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=12)
    catalog = seed(database_path)

    assert available(client, catalog.alex) == [
        {
            "id": catalog.chores["Bathroom"],
            "name": "Bathroom",
            "description": "Scrub the bathroom",
            "weight": 3,
            "assigned_to": None,
        }
    ]


def test_after_2000_other_childs_undone_chore_is_available(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)

    chores = available(client, catalog.alex)
    assert [(entry["name"], entry["assigned_to"]) for entry in chores] == [
        ("Bathroom", None),
        ("Yard", "Zoe"),
    ]
    # The child's own weekly chore is never offered as a takeover.
    assert "Kitchen" not in [entry["name"] for entry in chores]


def test_after_2000_a_done_chore_is_not_available(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)
    complete_item(database_path, catalog.yard_item)

    assert [entry["name"] for entry in available(client, catalog.alex)] == ["Bathroom"]


def test_takeover_claim_after_2000_creates_one_day_assignment(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)

    response = claim(client, catalog.alex, catalog.chores["Yard"])
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["chore_name"] == "Yard"
    assert payload["claim_date"] == TODAY
    assert payload["week_start"] == WEEK_START
    assert payload["week_end"] == WEEK_END
    assert payload["is_completed"] is False

    assert [entry["name"] for entry in available(client, catalog.alex)] == ["Bathroom"]
    claimed = client.get(f"/family-members/{catalog.alex}/claimed-chores")
    assert [entry["chore_name"] for entry in claimed.json()["claims"]] == ["Yard"]

    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM weekly_assignments").fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM assignment_checklist_items"
            ).fetchone()[0]
            == 3
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_checklist_completions"
            ).fetchone()[0]
            == 0
        )


def test_takeover_claim_is_rejected_before_2000(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=12)
    catalog = seed(database_path)

    response = claim(client, catalog.alex, catalog.chores["Yard"])
    assert response.status_code == 409
    assert response.json()["detail"] == "Chore is already assigned for this week"


def test_takeover_claim_is_rejected_when_chore_is_already_done(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)
    complete_item(database_path, catalog.yard_item)

    response = claim(client, catalog.alex, catalog.chores["Yard"])
    assert response.status_code == 409
    assert response.json()["detail"] == "Chore has already been completed today"


def test_own_weekly_chore_cannot_be_taken_over(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)

    response = claim(client, catalog.alex, catalog.chores["Kitchen"])
    assert response.status_code == 409


def test_competing_takeover_claims_create_exactly_one_assignment(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)
    barrier = threading.Barrier(2)

    def attempt(member_id: int) -> str:
        barrier.wait(timeout=5)
        service = ChildViewsService(SQLiteChildViewsPersistence(database_path))
        try:
            service.claim_chore(
                member_id,
                catalog.chores["Yard"],
                datetime(2026, 11, 25, 21, tzinfo=ZoneInfo("America/Denver")),
            )
        except ChoreAlreadyClaimed:
            return "conflict"
        return "claimed"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=15)
            for future in (
                executor.submit(attempt, catalog.alex),
                executor.submit(attempt, catalog.riley),
            )
        ]
    assert sorted(results) == ["claimed", "conflict"]
    with connect(database_path) as connection:
        rows = connection.execute(
            "SELECT chore_id, claim_date FROM daily_chore_claims"
        ).fetchall()
    assert [tuple(row) for row in rows] == [(catalog.chores["Yard"], TODAY)]


def test_claim_completion_toggles_and_is_reflected(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=12)
    catalog = seed(database_path)
    created = claim(client, catalog.alex, catalog.chores["Bathroom"])
    claim_id = created.json()["id"]

    done = client.put(
        f"/family-members/{catalog.alex}/claimed-chores/{claim_id}/completion",
        json={"is_completed": True},
    )
    assert done.status_code == 200, done.text
    assert done.json()["is_completed"] is True

    listed = client.get(f"/family-members/{catalog.alex}/claimed-chores")
    assert listed.json()["claims"][0]["is_completed"] is True

    undone = client.put(
        f"/family-members/{catalog.alex}/claimed-chores/{claim_id}/completion",
        json={"is_completed": False},
    )
    assert undone.status_code == 200
    assert undone.json()["is_completed"] is False

    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_chore_claim_completions"
            ).fetchone()[0]
            == 1
        )


def test_claim_completion_is_scoped_to_the_profile(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=12)
    catalog = seed(database_path)
    claim_id = claim(client, catalog.alex, catalog.chores["Bathroom"]).json()["id"]

    other = client.put(
        f"/family-members/{catalog.zoe}/claimed-chores/{claim_id}/completion",
        json={"is_completed": True},
    )
    assert other.status_code == 404
    unknown = client.put(
        f"/family-members/{catalog.alex}/claimed-chores/999/completion",
        json={"is_completed": True},
    )
    assert unknown.status_code == 404


def test_takeover_blocks_original_childs_checklist_for_that_day(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)

    taken_over = claim(client, catalog.alex, catalog.chores["Yard"])
    assert taken_over.status_code == 201

    # Zoe can no longer complete the chore Alex took over: her day must not be
    # counted complete and the XP must stay with the claimant.
    url = (
        f"/family-members/{catalog.zoe}/assignments/{catalog.assignments['Yard']}/"
        f"checklist-items/{catalog.yard_item}/completion"
    )
    blocked = client.put(url, json={"completion_date": TODAY, "is_completed": True})
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == ("This chore was claimed by another child today")
    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_checklist_completions"
            ).fetchone()[0]
            == 0
        )

    zoe_stats = client.get(f"/family-members/{catalog.zoe}/derived-stats").json()
    assert zoe_stats["current_week"]["complete_days"] == 0
    assert zoe_stats["current_week"]["xp"] == 0


def test_completion_rejects_a_claim_from_another_day(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=12)
    catalog = seed(database_path)
    with connect(database_path) as connection:
        stale_id = connection.execute(
            """INSERT INTO daily_chore_claims
               (family_member_id, chore_id, claim_date, week_start, week_end,
                chore_name_snapshot, chore_description_snapshot,
                chore_weight_snapshot)
               VALUES (?, ?, '2026-11-24', ?, ?, 'Bathroom',
                       'Scrub the bathroom', 3)""",
            (
                catalog.alex,
                catalog.chores["Bathroom"],
                WEEK_START,
                WEEK_END,
            ),
        ).lastrowid

    response = client.put(
        f"/family-members/{catalog.alex}/claimed-chores/{stale_id}/completion",
        json={"is_completed": True},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "That claim is not for today"
    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_chore_claim_completions"
            ).fetchone()[0]
            == 0
        )


def test_claim_completions_cannot_be_deleted(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=12)
    catalog = seed(database_path)
    claim_id = claim(client, catalog.alex, catalog.chores["Bathroom"]).json()["id"]
    client.put(
        f"/family-members/{catalog.alex}/claimed-chores/{claim_id}/completion",
        json={"is_completed": True},
    )

    with connect(database_path) as connection:
        try:
            connection.execute("DELETE FROM daily_chore_claim_completions")
        except sqlite3.IntegrityError as error:
            assert "cannot be deleted" in str(error)
        else:
            raise AssertionError("claim completion rows must be immutable to deletes")


def test_completed_takeover_awards_xp_to_claimant_not_original_child(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch, hour=21)
    catalog = seed(database_path)

    created = claim(client, catalog.alex, catalog.chores["Yard"])
    assert created.status_code == 201
    client.put(
        f"/family-members/{catalog.alex}/claimed-chores/{created.json()['id']}/completion",
        json={"is_completed": True},
    )

    alex_stats = client.get(f"/family-members/{catalog.alex}/derived-stats").json()
    zoe_stats = client.get(f"/family-members/{catalog.zoe}/derived-stats").json()

    # Yard has weight 1 => 10 XP goes to Alex, who completed the takeover.
    assert alex_stats["current_week"]["xp"] == 10
    assert alex_stats["lifetime"]["xp"] == 10
    assert alex_stats["household"]["xp_rankings"][0]["display_name"] == "Alex"
    assert alex_stats["household"]["xp_rankings"][0]["total_xp"] == 10

    # Zoe keeps no XP and her day is not counted as complete.
    assert zoe_stats["current_week"]["xp"] == 0
    assert zoe_stats["current_week"]["complete_days"] == 0
    today = [day for day in zoe_stats["current_week"]["days"] if day["date"] == TODAY][
        0
    ]
    assert today["state"] == "not_recorded"
    assert zoe_stats["household"]["xp_rankings"][1]["total_xp"] == 0

    # No weekly completion rows were written for the original child.
    with connect(database_path) as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM daily_checklist_completions"
            ).fetchone()[0]
            == 0
        )
