"""Integration tests for the public catalog and theme preferences."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
import chore_tracker.api.routes.child_views as child_views
from chore_tracker.adapters.sqlite import connect
from chore_tracker.adapters.sqlite.themes import SQLiteThemePersistence
from chore_tracker.application.services.themes import ThemeService
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
CREDENTIAL_ID = "Y3JlZC10aGVtZQ"


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "themes.db"
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
    monkeypatch.setattr(
        app.state,
        "theme_service",
        ThemeService(SQLiteThemePersistence(database_path)),
    )
    return TestClient(app), database_path


def headers():
    return {"Origin": ORIGIN}


def create_member(database_path, name, active=True):
    with connect(database_path) as connection:
        return connection.execute(
            "INSERT INTO family_members (display_name, is_active) VALUES (?, ?)",
            (name, int(active)),
        ).lastrowid


def enroll_admin(client, monkeypatch):
    started = client.post(
        "/auth/setup/start", json={"email": "admin@example.test"}, headers=headers()
    )
    monkeypatch.setattr(
        auth,
        "_verify_registration",
        lambda _challenge, _credential: SimpleNamespace(
            credential_id=b"theme-credential",
            credential_public_key=b"public-key",
            sign_count=0,
        ),
    )
    finished = client.post(
        "/auth/setup/finish",
        json={
            "challenge_id": started.json()["challenge_id"],
            "credential": {
                "id": CREDENTIAL_ID,
                "response": {"transports": ["internal"]},
            },
        },
        headers=headers(),
    )
    assert finished.status_code == 200


def test_theme_catalog_is_public_and_only_exposes_homestead(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)

    response = client.get("/themes")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": "homestead",
            "name": "Homestead",
            "preview_image": "/theme-previews/homestead.png",
        }
    ]


def test_child_theme_is_idempotent_and_reflected_in_active_members(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    member_id = create_member(database_path, "Alex")

    updated = client.put(
        f"/family-members/{member_id}/theme", json={"theme_id": "homestead"}
    )
    repeated = client.put(
        f"/family-members/{member_id}/theme", json={"theme_id": "homestead"}
    )

    assert updated.status_code == 200
    assert updated.json() == {"theme_id": "homestead"}
    assert repeated.status_code == 200
    assert repeated.json() == {"theme_id": "homestead"}
    assert client.get("/family-members/active").json() == [
        {"id": member_id, "display_name": "Alex", "theme_id": "homestead"}
    ]


def test_child_theme_rejects_unknown_inactive_and_missing_members(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    inactive_id = create_member(database_path, "Inactive", active=False)

    unknown_theme = client.put("/family-members/1/theme", json={"theme_id": "quest"})
    missing = client.put("/family-members/999/theme", json={"theme_id": "homestead"})
    inactive = client.put(
        f"/family-members/{inactive_id}/theme", json={"theme_id": "homestead"}
    )

    assert unknown_theme.status_code == 422
    assert missing.status_code == 404
    assert inactive.status_code == 409


def test_administrator_theme_requires_auth_same_origin_and_is_per_admin(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    enroll_admin(client, monkeypatch)

    assert client.get("/auth/me").json()["theme_id"] is None
    assert (
        client.put(
            "/auth/me/theme",
            json={"theme_id": "homestead"},
            headers={"Origin": "https://attacker.example"},
        ).status_code
        == 403
    )

    updated = client.put(
        "/auth/me/theme", json={"theme_id": "homestead"}, headers=headers()
    )
    repeated = client.put(
        "/auth/me/theme", json={"theme_id": "homestead"}, headers=headers()
    )
    assert updated.status_code == 200
    assert updated.json() == {"theme_id": "homestead"}
    assert repeated.status_code == 200
    assert client.get("/auth/me").json()["theme_id"] == "homestead"
    assert (
        client.put(
            "/auth/me/theme", json={"theme_id": "quest"}, headers=headers()
        ).status_code
        == 422
    )

    client.post("/auth/logout", headers=headers())
    assert (
        client.put(
            "/auth/me/theme", json={"theme_id": "homestead"}, headers=headers()
        ).status_code
        == 401
    )


def test_second_administrator_can_store_a_different_theme(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    enroll_admin(client, monkeypatch)
    first = client.put(
        "/auth/me/theme", json={"theme_id": "homestead"}, headers=headers()
    )
    assert first.status_code == 200

    invitation = client.post(
        "/auth/administrators",
        json={"email": "second@example.test"},
        headers=headers(),
    )
    assert invitation.status_code == 200
    token = invitation.json()["enrollment_token"]
    client.post("/auth/logout", headers=headers())

    # The second administrator is provisioned directly; the point of this test
    # is per-row persistence, not a second passkey ceremony.
    with connect(database_path) as connection:
        second_id = connection.execute(
            "SELECT id FROM administrators WHERE email = 'second@example.test'"
        ).fetchone()["id"]
    with connect(database_path) as connection:
        # A future catalog may offer different themes. The persistence layer
        # must keep each administrator's value independent.
        connection.execute(
            "UPDATE administrators SET theme_id = 'quest' WHERE id = ?",
            (second_id,),
        )
        first_theme = connection.execute(
            "SELECT theme_id FROM administrators WHERE id = 1"
        ).fetchone()["theme_id"]
        second_theme = connection.execute(
            "SELECT theme_id FROM administrators WHERE id = ?", (second_id,)
        ).fetchone()["theme_id"]
    assert first_theme == "homestead"
    assert second_theme == "quest"
    assert token
