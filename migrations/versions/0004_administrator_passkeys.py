"""Add passkey credentials, one-time enrollment, challenges, and sessions.

Revision ID: 0004_administrator_passkeys
Revises: 0003_immutable_assignment_history
"""

from __future__ import annotations

from alembic import op

revision = "0004_administrator_passkeys"
down_revision = "0003_immutable_assignment_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE administrators ADD COLUMN webauthn_user_id BLOB")
    op.execute(
        "CREATE UNIQUE INDEX ix_administrators_webauthn_user_id "
        "ON administrators(webauthn_user_id)"
    )
    op.execute("""
        CREATE TABLE administrator_passkey_credentials (
            id INTEGER PRIMARY KEY,
            administrator_id INTEGER NOT NULL
                REFERENCES administrators(id) ON DELETE CASCADE,
            credential_id TEXT NOT NULL UNIQUE,
            public_key BLOB NOT NULL,
            sign_count INTEGER NOT NULL DEFAULT 0 CHECK (sign_count >= 0),
            transports TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
    """)
    op.execute("""
        CREATE TABLE authentication_challenges (
            id TEXT PRIMARY KEY,
            challenge TEXT NOT NULL,
            purpose TEXT NOT NULL CHECK (purpose IN ('registration', 'authentication')),
            administrator_id INTEGER REFERENCES administrators(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            consumed_at TEXT
        )
    """)
    op.execute("""
        CREATE TABLE administrator_enrollment_tokens (
            token_hash TEXT PRIMARY KEY,
            administrator_id INTEGER NOT NULL UNIQUE
                REFERENCES administrators(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            consumed_at TEXT
        )
    """)
    op.execute("""
        CREATE TABLE administrator_sessions (
            token_hash TEXT PRIMARY KEY,
            administrator_id INTEGER NOT NULL
                REFERENCES administrators(id) ON DELETE CASCADE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
    """)
    op.execute(
        "CREATE INDEX ix_admin_sessions_expiry ON administrator_sessions(expires_at)"
    )
    op.execute(
        "CREATE INDEX ix_auth_challenges_expiry "
        "ON authentication_challenges(expires_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX ix_administrators_webauthn_user_id")
    op.execute("ALTER TABLE administrators DROP COLUMN webauthn_user_id")
    op.execute("DROP INDEX ix_auth_challenges_expiry")
    op.execute("DROP INDEX ix_admin_sessions_expiry")
    op.execute("DROP TABLE administrator_sessions")
    op.execute("DROP TABLE administrator_enrollment_tokens")
    op.execute("DROP TABLE authentication_challenges")
    op.execute("DROP TABLE administrator_passkey_credentials")
