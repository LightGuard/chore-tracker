"""SQLite persistence for administrator authentication."""

from __future__ import annotations

import json
from pathlib import Path

from chore_tracker.adapters.sqlite import transaction


class SQLiteAuthPersistence:
    """Own authentication SQL and transaction boundaries."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = database_path

    def setup_status(self) -> tuple[int, int]:
        with transaction(self.database_path) as db:
            row = db.execute(
                """SELECT COUNT(*) AS administrators,
                          SUM(CASE WHEN EXISTS (
                            SELECT 1 FROM administrator_passkey_credentials c
                            WHERE c.administrator_id = administrators.id
                          ) THEN 1 ELSE 0 END) AS enrolled
                   FROM administrators"""
            ).fetchone()
        return row["administrators"], row["enrolled"] or 0

    def claim_initial_administrator(self, email: str, user_id: bytes) -> int:
        with transaction(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id, email FROM administrators ORDER BY id LIMIT 1"
            ).fetchone()
            if row is None:
                return db.execute(
                    """INSERT INTO administrators
                       (email, webauthn_user_id) VALUES (?, ?)""",
                    (email, user_id),
                ).lastrowid
            if row["email"].casefold() != email.casefold():
                raise ValueError("Initial administrator setup is already claimed")
            enrolled = db.execute(
                """SELECT 1 FROM administrator_passkey_credentials
                   WHERE administrator_id = ?""",
                (row["id"],),
            ).fetchone()
            if enrolled:
                raise ValueError("Initial setup is already complete")
            return row["id"]

    def administrator_user_id(self, administrator_id: int) -> bytes | None:
        with transaction(self.database_path) as db:
            row = db.execute(
                "SELECT webauthn_user_id FROM administrators WHERE id = ?",
                (administrator_id,),
            ).fetchone()
        return (
            (row["webauthn_user_id"] if row["webauthn_user_id"] is not None else b"")
            if row
            else None
        )

    def set_administrator_user_id(self, administrator_id: int, user_id: bytes) -> None:
        with transaction(self.database_path) as db:
            db.execute(
                "UPDATE administrators SET webauthn_user_id = ? WHERE id = ?",
                (user_id, administrator_id),
            )

    def create_challenge(
        self,
        challenge_id: str,
        challenge: str,
        purpose: str,
        administrator_id: int,
        expires_at: str,
    ) -> None:
        with transaction(self.database_path) as db:
            db.execute(
                """INSERT INTO authentication_challenges
                   (id, challenge, purpose, administrator_id, expires_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (challenge_id, challenge, purpose, administrator_id, expires_at),
            )

    def get_challenge(self, challenge_id: str, purpose: str, now: str):
        with transaction(self.database_path) as db:
            row = db.execute(
                """SELECT challenge, administrator_id FROM authentication_challenges
                   WHERE id = ? AND purpose = ? AND consumed_at IS NULL
                     AND expires_at > ?""",
                (challenge_id, purpose, now),
            ).fetchone()
        return dict(row) if row else None

    def consume_challenge(self, challenge_id: str, now: str) -> bool:
        with transaction(self.database_path) as db:
            changed = db.execute(
                """UPDATE authentication_challenges SET consumed_at = ?
                   WHERE id = ? AND consumed_at IS NULL AND expires_at > ?""",
                (now, challenge_id, now),
            ).rowcount
        return changed == 1

    def save_credential(
        self,
        administrator_id: int,
        credential_id: str,
        public_key: bytes,
        sign_count: int,
        transports: list[str],
    ) -> None:
        with transaction(self.database_path) as db:
            db.execute(
                """INSERT INTO administrator_passkey_credentials
                   (administrator_id, credential_id, public_key, sign_count, transports)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    administrator_id,
                    credential_id,
                    public_key,
                    sign_count,
                    json.dumps(transports),
                ),
            )

    def login_credentials(self, email: str):
        with transaction(self.database_path) as db:
            admin = db.execute(
                """SELECT a.id FROM administrators a
                   JOIN administrator_passkey_credentials c ON c.administrator_id = a.id
                   WHERE a.email = ? COLLATE NOCASE AND a.is_active = 1""",
                (email,),
            ).fetchone()
            if admin is None:
                return None, []
            rows = db.execute(
                """SELECT credential_id, transports
                   FROM administrator_passkey_credentials
                   WHERE administrator_id = ?""",
                (admin["id"],),
            ).fetchall()
        return admin["id"], [
            {
                "credential_id": row["credential_id"],
                "transports": json.loads(row["transports"]),
            }
            for row in rows
        ]

    def authentication_credential(self, administrator_id: int, credential_id: str):
        with transaction(self.database_path) as db:
            row = db.execute(
                """SELECT credential_id, public_key, sign_count
                   FROM administrator_passkey_credentials
                   WHERE administrator_id = ? AND credential_id = ?""",
                (administrator_id, credential_id),
            ).fetchone()
        return dict(row) if row else None

    def finish_authentication(
        self, challenge_id: str, credential_id: str, new_sign_count: int, now: str
    ) -> bool:
        with transaction(self.database_path) as db:
            changed = db.execute(
                """UPDATE authentication_challenges SET consumed_at = ?
                   WHERE id = ? AND consumed_at IS NULL AND expires_at > ?""",
                (now, challenge_id, now),
            ).rowcount
            if changed != 1:
                return False
            db.execute(
                """UPDATE administrator_passkey_credentials SET sign_count = ?
                   WHERE credential_id = ?""",
                (new_sign_count, credential_id),
            )
        return True

    def create_session(self, token_hash: str, administrator_id: int, expires_at: str):
        with transaction(self.database_path) as db:
            db.execute(
                """INSERT INTO administrator_sessions
                   (token_hash, administrator_id, expires_at) VALUES (?, ?, ?)""",
                (token_hash, administrator_id, expires_at),
            )

    def administrator_for_session(self, token_hash: str, now: str):
        with transaction(self.database_path) as db:
            row = db.execute(
                """SELECT a.id, a.email FROM administrator_sessions s
                   JOIN administrators a ON a.id = s.administrator_id
                   WHERE s.token_hash = ? AND s.expires_at > ? AND a.is_active = 1""",
                (token_hash, now),
            ).fetchone()
        return {"id": row["id"], "email": row["email"]} if row else None

    def revoke_session(self, token_hash: str) -> None:
        with transaction(self.database_path) as db:
            db.execute(
                "DELETE FROM administrator_sessions WHERE token_hash = ?",
                (token_hash,),
            )

    def create_invitation(
        self, email: str, user_id: bytes, token_hash: str, expires_at: str
    ) -> int:
        with transaction(self.database_path) as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM administrators").fetchone()[0]
            if count >= 2:
                raise ValueError("The two administrator accounts already exist")
            try:
                administrator_id = db.execute(
                    "INSERT INTO administrators (email, webauthn_user_id) VALUES (?, ?)",
                    (email, user_id),
                ).lastrowid
            except Exception as error:
                raise ValueError(
                    "An administrator with that email already exists"
                ) from error
            db.execute(
                """INSERT INTO administrator_enrollment_tokens
                   (token_hash, administrator_id, expires_at)
                   VALUES (?, ?, ?)""",
                (token_hash, administrator_id, expires_at),
            )
        return administrator_id

    def get_invitation(self, token_hash: str, now: str):
        with transaction(self.database_path) as db:
            row = db.execute(
                """SELECT t.administrator_id, a.email
                   FROM administrator_enrollment_tokens t
                   JOIN administrators a ON a.id = t.administrator_id
                   WHERE t.token_hash = ? AND t.consumed_at IS NULL
                     AND t.expires_at > ?""",
                (token_hash, now),
            ).fetchone()
        return dict(row) if row else None

    def finish_enrollment(
        self,
        challenge_id: str,
        administrator_id: int,
        credential_id: str,
        public_key: bytes,
        sign_count: int,
        transports: list[str],
        invitation_token_hash: str,
        now: str,
    ) -> bool:
        with transaction(self.database_path) as db:
            changed = db.execute(
                """UPDATE authentication_challenges SET consumed_at = ?
                   WHERE id = ? AND purpose = 'registration'
                     AND administrator_id = ?
                     AND consumed_at IS NULL AND expires_at > ?""",
                (now, challenge_id, administrator_id, now),
            ).rowcount
            if changed != 1:
                return False
            db.execute(
                """INSERT INTO administrator_passkey_credentials
                   (administrator_id, credential_id, public_key, sign_count, transports)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    administrator_id,
                    credential_id,
                    public_key,
                    sign_count,
                    json.dumps(transports),
                ),
            )
            consumed = db.execute(
                """UPDATE administrator_enrollment_tokens SET consumed_at = ?
                   WHERE token_hash = ? AND administrator_id = ?
                     AND consumed_at IS NULL AND expires_at > ?""",
                (now, invitation_token_hash, administrator_id, now),
            ).rowcount
            if consumed != 1:
                raise ValueError("Enrollment invitation has already been used")
        return True

    def finish_registration(
        self,
        challenge_id: str,
        administrator_id: int,
        credential_id: str,
        public_key: bytes,
        sign_count: int,
        transports: list[str],
        now: str,
    ) -> bool:
        with transaction(self.database_path) as db:
            changed = db.execute(
                """UPDATE authentication_challenges SET consumed_at = ?
                   WHERE id = ? AND purpose = 'registration' AND administrator_id = ?
                     AND consumed_at IS NULL AND expires_at > ?""",
                (now, challenge_id, administrator_id, now),
            ).rowcount
            if changed != 1:
                return False
            try:
                db.execute(
                    """INSERT INTO administrator_passkey_credentials
                       (administrator_id, credential_id, public_key, sign_count,
                        transports) VALUES (?, ?, ?, ?, ?)""",
                    (
                        administrator_id,
                        credential_id,
                        public_key,
                        sign_count,
                        json.dumps(transports),
                    ),
                )
            except Exception as error:
                raise ValueError("Passkey is already registered") from error
        return True

    def enrollment_hash_for_administrator(
        self, administrator_id: int, now: str
    ) -> str | None:
        with transaction(self.database_path) as db:
            row = db.execute(
                """SELECT token_hash FROM administrator_enrollment_tokens
                   WHERE administrator_id = ? AND consumed_at IS NULL
                     AND expires_at > ?""",
                (administrator_id, now),
            ).fetchone()
        return row["token_hash"] if row else None
