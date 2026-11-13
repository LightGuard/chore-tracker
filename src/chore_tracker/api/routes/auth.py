"""HTTP endpoints for administrator setup, passkeys, and sessions."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from webauthn import verify_authentication_response, verify_registration_response
from webauthn.helpers import base64url_to_bytes

from chore_tracker.application.services.authentication import (
    AuthenticationError,
    AuthenticationService,
)
from chore_tracker.config import get_settings

router = APIRouter(prefix="/auth", tags=["authentication"])
SESSION_COOKIE = "chore_tracker_session"


class EmailRequest(BaseModel):
    email: str


class CeremonyRequest(BaseModel):
    challenge_id: str
    credential: dict[str, Any]


class EnrollmentStartRequest(BaseModel):
    token: str


def _verify_registration(challenge: str, credential_data: dict[str, Any]):
    settings = get_settings()
    return verify_registration_response(
        credential=credential_data,
        expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=settings.passkey_rp_id,
        expected_origin=settings.passkey_origin,
        require_user_verification=True,
    )


def _service(request: Request) -> AuthenticationService:
    settings = get_settings()
    factory = request.app.state.authentication_service_factory
    return factory(
        settings,
        registration_verifier=_verify_registration,
        authentication_verifier=verify_authentication_response,
    )


def _raise_http(error: AuthenticationError) -> None:
    statuses = {
        "invalid_email": 422,
        "administrator_missing": 404,
        "setup_claimed": 409,
        "setup_complete": 409,
        "administrator_not_enrolled": 401,
        "registration_challenge_invalid": 400,
        "registration_verification_failed": 400,
        "credential_duplicate": 409,
        "registration_challenge_used": 400,
        "authentication_challenge_invalid": 400,
        "credential_missing": 401,
        "authentication_failed": 401,
        "authentication_challenge_used": 400,
        "administrator_limit": 409,
        "duplicate_email": 409,
        "invitation_invalid": 400,
        "invitation_challenge_invalid": 400,
        "invitation_used": 400,
    }
    raise HTTPException(
        status_code=statuses.get(error.code, 400), detail=str(error)
    ) from error


def _call(operation, *args):
    try:
        return operation(*args)
    except AuthenticationError as error:
        _raise_http(error)


def _set_session(response: Response, token: str) -> None:
    settings = get_settings()
    from datetime import timedelta

    response.set_cookie(
        SESSION_COOKIE, token, httponly=True,
        secure=settings.passkey_origin.startswith("https://"),
        samesite="strict", path="/", max_age=int(timedelta(days=7).total_seconds()),
    )


def require_same_origin(request: Request) -> None:
    """Reject browser state changes from origins other than the configured app."""
    if request.headers.get("origin") != get_settings().passkey_origin:
        raise HTTPException(status_code=403, detail="Request origin is not allowed")


def require_admin(
    request: Request,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> dict[str, Any]:
    """Resolve an active administrator from a server-side session cookie."""
    administrator = _call(_service(request).administrator_for_session, session_token)
    if administrator is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return administrator


@router.get("/setup")
def setup_status(request: Request) -> dict[str, Any]:
    return _call(_service(request).setup_status)


@router.post("/setup/start")
def setup_start(
    request: EmailRequest, http_request: Request,
    origin: None = Depends(require_same_origin),
):
    return _call(_service(http_request).setup_start, request.email)


@router.post("/setup/finish")
def setup_finish(
    request: CeremonyRequest, response: Response, http_request: Request,
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    token = _call(
        _service(http_request).finish_setup, request.challenge_id, request.credential
    )
    _set_session(response, token)
    return {"status": "ok"}


@router.post("/login/options")
def login_options(
    request: EmailRequest, http_request: Request,
    origin: None = Depends(require_same_origin),
) -> dict[str, Any]:
    return _call(_service(http_request).login_options, request.email)


@router.post("/login/finish")
def login_finish(
    request: CeremonyRequest, response: Response, http_request: Request,
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    token = _call(
        _service(http_request).login_finish, request.challenge_id, request.credential
    )
    _set_session(response, token)
    return {"status": "ok"}


@router.get("/me")
def current_admin(
    administrator: Annotated[dict[str, Any], Depends(require_admin)],
) -> dict[str, Any]:
    return administrator


@router.post("/logout")
def logout(
    response: Response, request: Request,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    _call(_service(request).logout, session_token)
    response.delete_cookie(
        SESSION_COOKIE, path="/", httponly=True, samesite="strict",
        secure=get_settings().passkey_origin.startswith("https://"),
    )
    return {"status": "ok"}


@router.post("/administrators")
def create_administrator(
    request: EmailRequest, http_request: Request,
    administrator: Annotated[dict[str, Any], Depends(require_admin)],
    origin: None = Depends(require_same_origin),
) -> dict[str, Any]:
    return _call(_service(http_request).create_administrator, request.email)


@router.post("/enrollment/options")
def enrollment_options(
    request: EnrollmentStartRequest, http_request: Request,
    origin: None = Depends(require_same_origin),
) -> dict[str, Any]:
    return _call(_service(http_request).enrollment_options, request.token)


@router.post("/enrollment/finish")
def enrollment_finish(
    request: CeremonyRequest, response: Response, http_request: Request,
    origin: None = Depends(require_same_origin),
) -> dict[str, str]:
    token = _call(
        _service(http_request).enrollment_finish,
        request.challenge_id, request.credential,
    )
    _set_session(response, token)
    return {"status": "ok"}
