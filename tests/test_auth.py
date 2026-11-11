"""Integration tests for administrator passkey setup and authentication."""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.auth as auth
from chore_tracker.adapters.sqlite import connect
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = "http://localhost:5173"
CREDENTIAL_ID = "Y3JlZC0x"


def prepare_client(tmp_path, monkeypatch):
    database_path = tmp_path / "auth.db"
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
    return TestClient(app), database_path


def request_headers():
    return {"Origin": ORIGIN}


def enroll_first_admin(client, monkeypatch, email="first@example.test"):
    started = client.post(
        "/auth/setup/start",
        json={"email": email},
        headers=request_headers(),
    )
    assert started.status_code == 200
    monkeypatch.setattr(
        auth,
        "_verify_registration",
        lambda _challenge, _credential: SimpleNamespace(
            credential_id=b"cred-1", credential_public_key=b"public-key", sign_count=0
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
        headers=request_headers(),
    )
    assert finished.status_code == 200
    return finished


def test_initial_setup_is_available_once_and_creates_admin_session(
    tmp_path, monkeypatch
):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    assert client.get("/auth/setup").json()["setup_required"] is True
    enrolled = enroll_first_admin(client, monkeypatch)

    assert enrolled.json() == {"status": "ok"}
    assert "chore_tracker_session" in enrolled.cookies
    assert client.get("/auth/setup").json()["setup_required"] is False
    assert client.get("/auth/me").json() == {
        "id": 1,
        "email": "first@example.test",
    }
    with connect(database_path) as connection:
        credential = connection.execute(
            "SELECT public_key FROM administrator_passkey_credentials"
        ).fetchone()
        user_handle = connection.execute(
            "SELECT webauthn_user_id FROM administrators WHERE id = 1"
        ).fetchone()["webauthn_user_id"]
    assert credential["public_key"] == b"public-key"
    assert isinstance(user_handle, bytes)
    assert len(user_handle) == 64


def test_initial_setup_cannot_be_claimed_twice(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    first = client.post(
        "/auth/setup/start",
        json={"email": "first@example.test"},
        headers=request_headers(),
    )
    second = client.post(
        "/auth/setup/start",
        json={"email": "attacker@example.test"},
        headers=request_headers(),
    )
    assert first.status_code == 200
    assert second.status_code == 409


def test_setup_rejects_requests_from_an_untrusted_origin(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    response = client.post(
        "/auth/setup/start",
        json={"email": "first@example.test"},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403


def test_login_success_creates_session_and_replay_is_rejected(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    enroll_first_admin(client, monkeypatch)

    options = client.post(
        "/auth/login/options",
        json={"email": "first@example.test"},
        headers=request_headers(),
    )
    assert options.status_code == 200

    monkeypatch.setattr(
        auth,
        "verify_authentication_response",
        lambda **_kwargs: SimpleNamespace(new_sign_count=1),
    )
    payload = {
        "challenge_id": options.json()["challenge_id"],
        "credential": {"id": CREDENTIAL_ID},
    }
    response = client.post(
        "/auth/login/finish", json=payload, headers=request_headers()
    )
    assert response.status_code == 200
    assert "chore_tracker_session" in response.cookies

    replay = client.post("/auth/login/finish", json=payload, headers=request_headers())
    assert replay.status_code == 400


def test_expired_login_challenge_is_rejected(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    enroll_first_admin(client, monkeypatch)
    options = client.post(
        "/auth/login/options",
        json={"email": "first@example.test"},
        headers=request_headers(),
    )
    with connect(database_path) as connection:
        connection.execute(
            "UPDATE authentication_challenges SET expires_at = ? WHERE id = ?",
            (
                (datetime.now(UTC) - timedelta(minutes=1))
                .isoformat()
                .replace("+00:00", "Z"),
                options.json()["challenge_id"],
            ),
        )
    response = client.post(
        "/auth/login/finish",
        json={
            "challenge_id": options.json()["challenge_id"],
            "credential": {"id": CREDENTIAL_ID},
        },
        headers=request_headers(),
    )
    assert response.status_code == 400


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def test_failed_passkey_verification_does_not_create_session(
    tmp_path, monkeypatch
):
    client, _ = prepare_client(tmp_path, monkeypatch)
    enroll_first_admin(client, monkeypatch)
    options = client.post(
        "/auth/login/options",
        json={"email": "first@example.test"},
        headers=request_headers(),
    )
    challenge = options.json()["options"]["challenge"]
    client_data = json.dumps(
        {
            "type": "webauthn.get",
            "challenge": challenge,
            "origin": ORIGIN,
            "crossOrigin": False,
        }
    ).encode("utf-8")
    authenticator_data = (
        hashlib.sha256(b"localhost").digest()
        + bytes([0x05])
        + (0).to_bytes(4, "big")
    )
    credential = {
        "id": CREDENTIAL_ID,
        "rawId": CREDENTIAL_ID,
        "type": "public-key",
        "response": {
            "clientDataJSON": _base64url(client_data),
            "authenticatorData": _base64url(authenticator_data),
            "signature": _base64url(b"invalid signature"),
            "userHandle": None,
        },
        "clientExtensionResults": {},
        "authenticatorAttachment": "platform",
    }

    response = client.post(
        "/auth/login/finish",
        json={
            "challenge_id": options.json()["challenge_id"],
            "credential": credential,
        },
        headers=request_headers(),
    )
    assert response.status_code == 401
    assert "chore_tracker_session" not in response.cookies


def test_real_registration_verifier_rejects_malformed_browser_response(
    tmp_path, monkeypatch
):
    client, _ = prepare_client(tmp_path, monkeypatch)
    started = client.post(
        "/auth/setup/start",
        json={"email": "first@example.test"},
        headers=request_headers(),
    )

    response = client.post(
        "/auth/setup/finish",
        json={
            "challenge_id": started.json()["challenge_id"],
            "credential": {
                "id": CREDENTIAL_ID,
                "rawId": CREDENTIAL_ID,
                "type": "public-key",
                "response": {},
            },
        },
        headers=request_headers(),
    )

    assert response.status_code == 400
    assert client.get("/auth/setup").json()["setup_required"] is True


def test_admin_authorization_and_second_administrator_enrollment(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    assert client.get("/auth/me").status_code == 401
    denied = client.post(
        "/auth/administrators",
        json={"email": "second@example.test"},
        headers=request_headers(),
    )
    assert denied.status_code == 401
    enroll_first_admin(client, monkeypatch)

    created = client.post(
        "/auth/administrators",
        json={"email": "second@example.test"},
        headers=request_headers(),
    )
    assert created.status_code == 200
    token = created.json()["enrollment_token"]
    enrollment = client.post(
        "/auth/enrollment/options",
        json={"token": token},
        headers=request_headers(),
    )
    assert enrollment.status_code == 200

    monkeypatch.setattr(
        auth,
        "_verify_registration",
        lambda _challenge, _credential: SimpleNamespace(
            credential_id=b"second-cred",
            credential_public_key=b"second-public-key",
            sign_count=0,
        ),
    )
    completed = client.post(
        "/auth/enrollment/finish",
        json={
            "challenge_id": enrollment.json()["challenge_id"],
            "credential": {
                "id": "c2Vjb25kLWNyZWQ",
                "response": {"transports": ["internal"]},
            },
        },
        headers=request_headers(),
    )
    assert completed.status_code == 200
    assert client.get("/auth/setup").json()["enrollment_pending"] is False

    with connect(database_path) as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM administrators").fetchone()[0] == 2
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM administrator_passkey_credentials"
            ).fetchone()[0]
            == 2
        )
        user_handles = connection.execute(
            "SELECT webauthn_user_id FROM administrators ORDER BY id"
        ).fetchall()
        assert len({row["webauthn_user_id"] for row in user_handles}) == 2
        invitation = connection.execute(
            "SELECT consumed_at FROM administrator_enrollment_tokens"
        ).fetchone()
    assert invitation["consumed_at"] is not None

    third = client.post(
        "/auth/administrators",
        json={"email": "third@example.test"},
        headers=request_headers(),
    )
    assert third.status_code == 409


def test_logout_revokes_the_server_side_session(tmp_path, monkeypatch):
    client, _ = prepare_client(tmp_path, monkeypatch)
    enroll_first_admin(client, monkeypatch)

    response = client.post("/auth/logout", headers=request_headers())

    assert response.status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_expired_session_is_not_authorized(tmp_path, monkeypatch):
    client, database_path = prepare_client(tmp_path, monkeypatch)
    enroll_first_admin(client, monkeypatch)

    with connect(database_path) as connection:
        connection.execute(
            "UPDATE administrator_sessions SET expires_at = '2000-01-01T00:00:00Z'"
        )

    assert client.get("/auth/me").status_code == 401
