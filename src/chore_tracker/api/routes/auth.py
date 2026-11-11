"""Administrator setup, passkey authentication, and session endpoints."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ValidationError
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from chore_tracker.adapters.sqlite import transaction
from chore_tracker.config import get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE = "chore_tracker_session"
SESSION_DURATION = timedelta(days=7)
CHALLENGE_DURATION = timedelta(minutes=5)
ENROLLMENT_DURATION = timedelta(hours=24)


class EmailRequest(BaseModel):
    email: str


class CeremonyRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]


class EnrollmentStartRequest(BaseModel):
    token: str


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _validate_email(email: str) -> str:
    normalized = email.strip()
    if len(normalized) > 254 or normalized.count("@") != 1:
        raise HTTPException(status_code=422, detail="A valid email address is required")
    local, domain = normalized.rsplit("@", 1)
    if not local or "." not in domain or any(char.isspace() for char in normalized):
        raise HTTPException(status_code=422, detail="A valid email address is required")
    return normalized


def require_same_origin(request: Request) -> None:
    """Reject browser state changes from origins other than the configured app."""
    if request.headers.get("origin") != get_settings().passkey_origin:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def _registration_options(
    administrator_id: int, email: str, database_path
) -> tuple[str, dict[str, Any]]:
    challenge_id = str(uuid.uuid4())
    with transaction(database_path) as connection:
        administrator = connection.execute(
            "SELECT webauthn_user_id FROM administrators WHERE id = ?",
            (administrator_id,),
        ).fetchone()
        if administrator is None:
            raise HTTPException(status_code=404, detail="Administrator was not found")
        user_id = administrator["webauthn_user_id"]
        if user_id is None:
            user_id = secrets.token_bytes(64)
            connection.execute(
                "UPDATE administrators SET webauthn_user_id = ? WHERE id = ?",
                (user_id, administrator_id),
            )
    options = generate_registration_options(
        rp_id=get_settings().passkey_rp_id,
        rp_name="Chore Tracker",
        user_id=user_id,
        user_name=email,
        user_display_name=email,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    with transaction(database_path) as connection:
        connection.execute(
            """INSERT INTO authentication_challenges
               (id, challenge, purpose, administrator_id, expires_at)
               VALUES (?, ?, 'registration', ?, ?)""",
            (
                challenge_id,
                bytes_to_base64url(options.challenge),
                administrator_id,
                _timestamp(_now() + CHALLENGE_DURATION),
            ),
        )
    return challenge_id, json.loads(options_to_json(options))


def _set_session(response: Response, administrator_id: int, database_path) -> None:
    token = _new_token()
    expires = _now() + SESSION_DURATION
    with transaction(database_path) as connection:
        connection.execute(
            """INSERT INTO administrator_sessions
               (token_hash, administrator_id, expires_at) VALUES (?, ?, ?)""",
            (_digest(token), administrator_id, _timestamp(expires)),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=get_settings().passkey_origin.startswith("https://"),
        samesite="strict",
        path="/",
        max_age=int(SESSION_DURATION.total_seconds()),
    )


def require_admin(
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, Any]:
    """Resolve an active administrator from a server-side session cookie."""
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    with transaction(get_settings().database_path) as connection:
        row = connection.execute(
            """SELECT a.id, a.email FROM administrator_sessions s
               JOIN administrators a ON a.id = s.administrator_id
               WHERE s.token_hash = ? AND s.expires_at > ? AND a.is_active = 1""",
            (_digest(session_token), _timestamp(_now())),
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return {"id": row["id"], "email": row["email"]}


@router.get("/setup")
def setup_status() -> dict[str, Any]:
    """Report whether first-administrator setup is required."""
    with transaction(get_settings().database_path) as connection:
        row = connection.execute(
            """SELECT COUNT(*) AS administrators,
                      SUM(CASE WHEN EXISTS (
                        SELECT 1 FROM administrator_passkey_credentials c
                        WHERE c.administrator_id = administrators.id
                      ) THEN 1 ELSE 0 END) AS enrolled
               FROM administrators"""
        ).fetchone()
    count = row["administrators"]
    enrolled = row["enrolled"] or 0
    return {
        "setup_required": count == 0 or (count == 1 and enrolled == 0),
        "enrollment_pending": count > 0 and enrolled < count,
    }


@router.post("/setup/start")
def setup_start(request: EmailRequest, origin: None = Depends(require_same_origin)):
    """Claim the initial administrator slot and begin browser passkey enrollment."""
    email = _validate_email(request.email)
    database_path = get_settings().database_path
    with transaction(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, email FROM administrators ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            administrator_id = connection.execute(
                "INSERT INTO administrators (email, webauthn_user_id) VALUES (?, ?)",
                (email, secrets.token_bytes(64)),
            ).lastrowid
        elif row["email"].casefold() == email.casefold():
            administrator_id = row["id"]
            enrolled = connection.execute(
                """SELECT 1 FROM administrator_passkey_credentials
                   WHERE administrator_id = ?""",
                (administrator_id,),
            ).fetchone()
            if enrolled:
                raise HTTPException(
                    status_code=409, detail="Initial setup is already complete"
                )
        else:
            raise HTTPException(
                status_code=409, detail="Initial administrator setup is already claimed"
            )
    challenge_id, options = _registration_options(
        administrator_id, email, database_path
    )
    return {
        "administrator_id": administrator_id,
        "challenge_id": challenge_id,
        "options": options,
    }


def _verify_registration(challenge: str, credential_data: dict[str, Any]):
    return verify_registration_response(
        credential=credential_data,
        expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=get_settings().passkey_rp_id,
        expected_origin=get_settings().passkey_origin,
        require_user_verification=True,
    )


def _save_registration(
    challenge_id: str, credential_data: dict[str, Any], verified, database_path
) -> int:
    with transaction(database_path) as connection:
        challenge = connection.execute(
            """SELECT challenge, administrator_id FROM authentication_challenges
               WHERE id = ? AND purpose = 'registration'
                 AND consumed_at IS NULL AND expires_at > ?""",
            (challenge_id, _timestamp(_now())),
        ).fetchone()
        if challenge is None or challenge["administrator_id"] is None:
            raise HTTPException(
                status_code=400, detail="Registration challenge is invalid or expired"
            )
        changed = connection.execute(
            """UPDATE authentication_challenges SET consumed_at = ?
               WHERE id = ? AND consumed_at IS NULL AND expires_at > ?""",
            (_timestamp(_now()), challenge_id, _timestamp(_now())),
        ).rowcount
        if changed != 1:
            raise HTTPException(
                status_code=400, detail="Registration challenge has already been used"
            )
        try:
            connection.execute(
                """INSERT INTO administrator_passkey_credentials
                   (administrator_id, credential_id, public_key, sign_count, transports)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    challenge["administrator_id"],
                    bytes_to_base64url(verified.credential_id),
                    verified.credential_public_key,
                    verified.sign_count,
                    json.dumps(
                        credential_data.get("response", {}).get("transports", [])
                    ),
                ),
            )
        except Exception as error:
            raise HTTPException(
                status_code=409, detail="Passkey is already registered"
            ) from error
        return challenge["administrator_id"]


@router.post("/setup/finish")
def setup_finish(
    request: CeremonyRequest,
    response: Response,
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    """Verify and persist the first administrator's public credential."""
    database_path = get_settings().database_path
    with transaction(database_path) as connection:
        challenge = connection.execute(
            """SELECT challenge, administrator_id FROM authentication_challenges
               WHERE id = ? AND purpose = 'registration'
                 AND consumed_at IS NULL AND expires_at > ?""",
            (request.challenge_id, _timestamp(_now())),
        ).fetchone()
    if challenge is None or challenge["administrator_id"] is None:
        raise HTTPException(
            status_code=400, detail="Registration challenge is invalid or expired"
        )
    try:
        verified = _verify_registration(challenge["challenge"], request.credential)
    except Exception as error:
        raise HTTPException(
            status_code=400, detail="Passkey registration could not be verified"
        ) from error
    administrator_id = _save_registration(
        request.challenge_id, request.credential, verified, database_path
    )
    _set_session(response, administrator_id, database_path)
    return {"status": "ok"}


@router.post("/login/options")
def login_options(
    request: EmailRequest, origin: None = Depends(require_same_origin)
) -> dict[str, Any]:
    email = _validate_email(request.email)
    database_path = get_settings().database_path
    with transaction(database_path) as connection:
        administrator = connection.execute(
            """SELECT a.id FROM administrators a
               JOIN administrator_passkey_credentials c ON c.administrator_id = a.id
               WHERE a.email = ? COLLATE NOCASE AND a.is_active = 1""",
            (email,),
        ).fetchone()
        if administrator is None:
            raise HTTPException(
                status_code=401,
                detail="No enrolled administrator matches that email",
            )
        credentials = connection.execute(
            """SELECT credential_id, transports
               FROM administrator_passkey_credentials
               WHERE administrator_id = ?""",
            (administrator["id"],),
        ).fetchall()
    descriptors = [
        PublicKeyCredentialDescriptor(
            id=base64url_to_bytes(row["credential_id"]),
            transports=[
                AuthenticatorTransport(value) for value in json.loads(row["transports"])
            ],
        )
        for row in credentials
    ]
    options = generate_authentication_options(
        rp_id=get_settings().passkey_rp_id,
        allow_credentials=descriptors,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    challenge_id = str(uuid.uuid4())
    with transaction(database_path) as connection:
        connection.execute(
            """INSERT INTO authentication_challenges
               (id, challenge, purpose, administrator_id, expires_at)
               VALUES (?, ?, 'authentication', ?, ?)""",
            (
                challenge_id,
                bytes_to_base64url(options.challenge),
                administrator["id"],
                _timestamp(_now() + CHALLENGE_DURATION),
            ),
        )
    return {
        "challenge_id": challenge_id,
        "options": json.loads(options_to_json(options)),
    }


@router.post("/login/finish")
def login_finish(
    request: CeremonyRequest,
    response: Response,
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    database_path = get_settings().database_path
    with transaction(database_path) as connection:
        challenge = connection.execute(
            """SELECT challenge, administrator_id FROM authentication_challenges
               WHERE id = ? AND purpose = 'authentication'
                 AND consumed_at IS NULL AND expires_at > ?""",
            (request.challenge_id, _timestamp(_now())),
        ).fetchone()
        stored = None
        if challenge is not None:
            stored = connection.execute(
                """SELECT credential_id, public_key, sign_count
                   FROM administrator_passkey_credentials
                   WHERE administrator_id = ? AND credential_id = ?""",
                (challenge["administrator_id"], request.credential.get("id")),
            ).fetchone()
    if challenge is None:
        raise HTTPException(
            status_code=400, detail="Authentication challenge is invalid or expired"
        )
    if stored is None:
        raise HTTPException(status_code=401, detail="Passkey is not registered")
    try:
        verified = verify_authentication_response(
            credential=request.credential,
            expected_challenge=base64url_to_bytes(challenge["challenge"]),
            expected_rp_id=get_settings().passkey_rp_id,
            expected_origin=get_settings().passkey_origin,
            credential_public_key=stored["public_key"],
            credential_current_sign_count=stored["sign_count"],
            require_user_verification=True,
        )
    except Exception as error:
        raise HTTPException(
            status_code=401, detail="Passkey authentication failed"
        ) from error
    with transaction(database_path) as connection:
        changed = connection.execute(
            """UPDATE authentication_challenges SET consumed_at = ?
               WHERE id = ? AND consumed_at IS NULL AND expires_at > ?""",
            (_timestamp(_now()), request.challenge_id, _timestamp(_now())),
        ).rowcount
        if changed != 1:
            raise HTTPException(
                status_code=400, detail="Authentication challenge has already been used"
            )
        connection.execute(
            """UPDATE administrator_passkey_credentials SET sign_count = ?
               WHERE credential_id = ?""",
            (verified.new_sign_count, stored["credential_id"]),
        )
    _set_session(response, challenge["administrator_id"], database_path)
    return {"status": "ok"}


@router.get("/me")
def current_admin(
    administrator: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    return administrator


@router.post("/logout")
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    if session_token:
        with transaction(get_settings().database_path) as connection:
            connection.execute(
                "DELETE FROM administrator_sessions WHERE token_hash = ?",
                (_digest(session_token),),
            )
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        samesite="strict",
        secure=get_settings().passkey_origin.startswith("https://"),
    )
    return {"status": "ok"}


@router.post("/administrators")
def create_administrator(
    request: EmailRequest,
    administrator: Annotated[dict[str, Any], Depends(require_admin)],
    origin: None = Depends(require_same_origin),
) -> dict[str, Any]:
    """Create the second administrator and return its one-time enrollment token."""
    email = _validate_email(request.email)
    database_path = get_settings().database_path
    token = _new_token()
    with transaction(database_path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        count = connection.execute("SELECT COUNT(*) FROM administrators").fetchone()[0]
        if count >= 2:
            raise HTTPException(
                status_code=409, detail="The two administrator accounts already exist"
            )
        try:
            administrator_id = connection.execute(
                "INSERT INTO administrators (email, webauthn_user_id) VALUES (?, ?)",
                (email, secrets.token_bytes(64)),
            ).lastrowid
        except Exception as error:
            raise HTTPException(
                status_code=409,
                detail="An administrator with that email already exists",
            ) from error
        connection.execute(
            """INSERT INTO administrator_enrollment_tokens
               (token_hash, administrator_id, expires_at)
               VALUES (?, ?, ?)""",
            (
                _digest(token),
                administrator_id,
                _timestamp(_now() + ENROLLMENT_DURATION),
            ),
        )
    return {
        "administrator_id": administrator_id,
        "email": email,
        "enrollment_token": token,
    }


@router.post("/enrollment/options")
def enrollment_options(
    request: EnrollmentStartRequest,
    origin: None = Depends(require_same_origin),
) -> dict[str, Any]:
    """Start passkey enrollment using the one-time invitation token."""
    database_path = get_settings().database_path
    with transaction(database_path) as connection:
        enrollment = connection.execute(
            """SELECT t.administrator_id, a.email
               FROM administrator_enrollment_tokens t
               JOIN administrators a ON a.id = t.administrator_id
               WHERE t.token_hash = ? AND t.consumed_at IS NULL
                 AND t.expires_at > ?""",
            (_digest(request.token), _timestamp(_now())),
        ).fetchone()
    if enrollment is None:
        raise HTTPException(
            status_code=400, detail="Enrollment token is invalid or expired"
        )
    challenge_id, options = _registration_options(
        enrollment["administrator_id"], enrollment["email"], database_path
    )
    return {
        "administrator_id": enrollment["administrator_id"],
        "challenge_id": challenge_id,
        "options": options,
    }


@router.post("/enrollment/finish")
def enrollment_finish(
    request: CeremonyRequest,
    response: Response,
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    """Complete invited administrator enrollment and consume its invitation."""
    database_path = get_settings().database_path
    with transaction(database_path) as connection:
        challenge = connection.execute(
            """SELECT challenge, administrator_id FROM authentication_challenges
               WHERE id = ? AND purpose = 'registration'
                 AND consumed_at IS NULL AND expires_at > ?""",
            (request.challenge_id, _timestamp(_now())),
        ).fetchone()
        invitation = None
        if challenge is not None:
            invitation = connection.execute(
                """SELECT token_hash FROM administrator_enrollment_tokens
                   WHERE administrator_id = ? AND consumed_at IS NULL
                     AND expires_at > ?""",
                (challenge["administrator_id"], _timestamp(_now())),
            ).fetchone()
    if challenge is None or invitation is None:
        raise HTTPException(
            status_code=400, detail="Enrollment invitation or challenge is invalid"
        )
    try:
        verified = _verify_registration(challenge["challenge"], request.credential)
    except Exception as error:
        raise HTTPException(
            status_code=400, detail="Passkey registration could not be verified"
        ) from error
    with transaction(database_path) as connection:
        changed = connection.execute(
            """UPDATE authentication_challenges SET consumed_at = ?
               WHERE id = ? AND consumed_at IS NULL AND expires_at > ?""",
            (_timestamp(_now()), request.challenge_id, _timestamp(_now())),
        ).rowcount
        if changed != 1:
            raise HTTPException(
                status_code=400, detail="Registration challenge has already been used"
            )
        connection.execute(
            """INSERT INTO administrator_passkey_credentials
               (administrator_id, credential_id, public_key, sign_count, transports)
               VALUES (?, ?, ?, ?, ?)""",
            (
                challenge["administrator_id"],
                bytes_to_base64url(verified.credential_id),
                verified.credential_public_key,
                verified.sign_count,
                json.dumps(
                    request.credential.get("response", {}).get("transports", [])
                ),
            ),
        )
        consumed = connection.execute(
            """UPDATE administrator_enrollment_tokens SET consumed_at = ?
               WHERE token_hash = ? AND consumed_at IS NULL AND expires_at > ?""",
            (_timestamp(_now()), invitation["token_hash"], _timestamp(_now())),
        ).rowcount
        if consumed != 1:
            raise HTTPException(
                status_code=400, detail="Enrollment invitation has already been used"
            )
    _set_session(response, challenge["administrator_id"], database_path)
    return {"status": "ok"}
