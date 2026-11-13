"""Application-level administrator authentication use cases."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

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


class AuthenticationError(Exception):
    """Expected authentication failure with an HTTP-independent error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def validate_email(email: str) -> str:
    normalized = email.strip()
    if (len(normalized) > 254 or normalized.count("@") != 1
            or not normalized.rsplit("@", 1)[0]
            or "." not in normalized.rsplit("@", 1)[1]
            or any(char.isspace() for char in normalized)):
        raise AuthenticationError("invalid_email", "A valid email address is required")
    return normalized


class AuthenticationService:
    """Orchestrate WebAuthn ceremonies without HTTP or persistence dependencies."""

    session_duration = timedelta(days=7)
    challenge_duration = timedelta(minutes=5)
    enrollment_duration = timedelta(hours=24)

    def __init__(
        self, persistence, *, rp_id: str, origin: str,
        registration_verifier=None, authentication_verifier=None,
    ) -> None:
        self.persistence = persistence
        self.rp_id = rp_id
        self.origin = origin
        self.registration_verifier = registration_verifier or verify_registration_response
        self.authentication_verifier = authentication_verifier or verify_authentication_response

    def setup_status(self) -> dict[str, bool]:
        count, enrolled = self.persistence.setup_status()
        return {
            "setup_required": count == 0 or (count == 1 and enrolled == 0),
            "enrollment_pending": count > 0 and enrolled < count,
        }

    def _registration_options(self, administrator_id: int, email: str):
        user_id = self.persistence.administrator_user_id(administrator_id)
        if user_id is None:
            raise AuthenticationError("administrator_missing", "Administrator was not found")
        if not user_id:
            user_id = secrets.token_bytes(64)
            self.persistence.set_administrator_user_id(administrator_id, user_id)
        options = generate_registration_options(
            rp_id=self.rp_id, rp_name="Chore Tracker", user_id=user_id,
            user_name=email, user_display_name=email,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.REQUIRED,
            ),
        )
        challenge_id = str(uuid.uuid4())
        self.persistence.create_challenge(
            challenge_id, bytes_to_base64url(options.challenge), "registration",
            administrator_id, _timestamp(_now() + self.challenge_duration),
        )
        return challenge_id, json.loads(options_to_json(options))

    def setup_start(self, email: str) -> dict[str, Any]:
        email = validate_email(email)
        try:
            administrator_id = self.persistence.claim_initial_administrator(
                email, secrets.token_bytes(64)
            )
        except ValueError as error:
            message = str(error)
            code = "setup_complete" if "complete" in message else "setup_claimed"
            raise AuthenticationError(code, message) from error
        challenge_id, options = self._registration_options(administrator_id, email)
        return {"administrator_id": administrator_id, "challenge_id": challenge_id,
                "options": options}

    def _verify_registration(self, challenge: str, credential: dict[str, Any]):
        return self.registration_verifier(
            credential=credential, expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=self.rp_id, expected_origin=self.origin,
            require_user_verification=True,
        )

    def _verify_authentication(self, challenge: str, credential: dict[str, Any], stored):
        return self.authentication_verifier(
            credential=credential, expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=self.rp_id, expected_origin=self.origin,
            credential_public_key=stored["public_key"],
            credential_current_sign_count=stored["sign_count"],
            require_user_verification=True,
        )

    def _new_session(self, administrator_id: int) -> str:
        token = _new_token()
        self.persistence.create_session(
            _digest(token), administrator_id,
            _timestamp(_now() + self.session_duration),
        )
        return token

    def finish_setup(self, challenge_id: str, credential: dict[str, Any]):
        challenge = self.persistence.get_challenge(
            challenge_id, "registration", _timestamp(_now())
        )
        if challenge is None or challenge["administrator_id"] is None:
            raise AuthenticationError(
                "registration_challenge_invalid",
                "Registration challenge is invalid or expired",
            )
        try:
            verified = self._verify_registration(challenge["challenge"], credential)
        except Exception as error:
            raise AuthenticationError(
                "registration_verification_failed",
                "Passkey registration could not be verified",
            ) from error
        now = _timestamp(_now())
        if not self.persistence.finish_registration(
            challenge_id, challenge["administrator_id"],
            bytes_to_base64url(verified.credential_id),
            verified.credential_public_key, verified.sign_count,
            credential.get("response", {}).get("transports", []), now,
        ):
            raise AuthenticationError(
                "registration_challenge_used",
                "Registration challenge has already been used",
            )
        return self._new_session(challenge["administrator_id"])

    def login_options(self, email: str) -> dict[str, Any]:
        email = validate_email(email)
        administrator_id, credentials = self.persistence.login_credentials(email)
        if administrator_id is None:
            raise AuthenticationError(
                "administrator_not_enrolled",
                "No enrolled administrator matches that email",
            )
        descriptors = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(row["credential_id"]),
                transports=[AuthenticatorTransport(value) for value in row["transports"]],
            ) for row in credentials
        ]
        options = generate_authentication_options(
            rp_id=self.rp_id, allow_credentials=descriptors,
            user_verification=UserVerificationRequirement.REQUIRED,
        )
        challenge_id = str(uuid.uuid4())
        self.persistence.create_challenge(
            challenge_id, bytes_to_base64url(options.challenge), "authentication",
            administrator_id, _timestamp(_now() + self.challenge_duration),
        )
        return {"challenge_id": challenge_id, "options": json.loads(options_to_json(options))}

    def login_finish(self, challenge_id: str, credential: dict[str, Any]) -> str:
        challenge = self.persistence.get_challenge(
            challenge_id, "authentication", _timestamp(_now())
        )
        if challenge is None:
            raise AuthenticationError(
                "authentication_challenge_invalid",
                "Authentication challenge is invalid or expired",
            )
        stored = self.persistence.authentication_credential(
            challenge["administrator_id"], credential.get("id", "")
        )
        if stored is None:
            raise AuthenticationError("credential_missing", "Passkey is not registered")
        try:
            verified = self._verify_authentication(challenge["challenge"], credential, stored)
        except Exception as error:
            raise AuthenticationError(
                "authentication_failed", "Passkey authentication failed"
            ) from error
        if not self.persistence.finish_authentication(
            challenge_id, stored["credential_id"], verified.new_sign_count,
            _timestamp(_now()),
        ):
            raise AuthenticationError(
                "authentication_challenge_used",
                "Authentication challenge has already been used",
            )
        return self._new_session(challenge["administrator_id"])

    def administrator_for_session(self, token: str):
        if not token:
            return None
        return self.persistence.administrator_for_session(_digest(token), _timestamp(_now()))

    def logout(self, token: str | None) -> None:
        if token:
            self.persistence.revoke_session(_digest(token))

    def create_administrator(self, email: str) -> dict[str, Any]:
        email = validate_email(email)
        token = _new_token()
        try:
            administrator_id = self.persistence.create_invitation(
                email, secrets.token_bytes(64), _digest(token),
                _timestamp(_now() + self.enrollment_duration),
            )
        except ValueError as error:
            message = str(error)
            code = "administrator_limit" if "two administrator" in message else "duplicate_email"
            raise AuthenticationError(code, message) from error
        return {"administrator_id": administrator_id, "email": email,
                "enrollment_token": token}

    def enrollment_options(self, token: str) -> dict[str, Any]:
        enrollment = self.persistence.get_invitation(_digest(token), _timestamp(_now()))
        if enrollment is None:
            raise AuthenticationError(
                "invitation_invalid", "Enrollment token is invalid or expired"
            )
        challenge_id, options = self._registration_options(
            enrollment["administrator_id"], enrollment["email"]
        )
        return {"administrator_id": enrollment["administrator_id"],
                "challenge_id": challenge_id, "options": options}

    def enrollment_finish(self, challenge_id: str, credential: dict[str, Any]):
        challenge = self.persistence.get_challenge(
            challenge_id, "registration", _timestamp(_now())
        )
        if challenge is None:
            raise AuthenticationError(
                "invitation_challenge_invalid",
                "Enrollment invitation or challenge is invalid",
            )
        invitation_hash = self.persistence.enrollment_hash_for_administrator(
            challenge["administrator_id"], _timestamp(_now())
        )
        if invitation_hash is None:
            raise AuthenticationError(
                "invitation_challenge_invalid",
                "Enrollment invitation or challenge is invalid",
            )
        try:
            verified = self._verify_registration(challenge["challenge"], credential)
        except Exception as error:
            raise AuthenticationError(
                "registration_verification_failed",
                "Passkey registration could not be verified",
            ) from error
        try:
            completed = self.persistence.finish_enrollment(
                challenge_id, challenge["administrator_id"],
                bytes_to_base64url(verified.credential_id),
                verified.credential_public_key, verified.sign_count,
                credential.get("response", {}).get("transports", []),
                invitation_hash, _timestamp(_now()),
            )
        except ValueError as error:
            raise AuthenticationError("invitation_used", str(error)) from error
        if not completed:
            raise AuthenticationError(
                "registration_challenge_used",
                "Registration challenge has already been used",
            )
        return self._new_session(challenge["administrator_id"])
