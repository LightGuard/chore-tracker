"""Integration tests for application liveness and database readiness."""

from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

import chore_tracker.api.routes.health as health_route
from chore_tracker.main import app

ROOT = Path(__file__).resolve().parents[1]


def migrate_database(database_path: Path) -> None:
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["database_path"] = str(database_path)
    command.upgrade(config, "head")


def configure_database(monkeypatch, database_path: Path) -> None:
    monkeypatch.setattr(
        health_route,
        "get_settings",
        lambda: SimpleNamespace(database_path=database_path),
    )


def test_liveness_does_not_depend_on_database(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "missing" / "tracker.db"
    configure_database(monkeypatch, database_path)

    response = TestClient(app).get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert not database_path.exists()


def test_readiness_succeeds_with_currently_migrated_database(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "ready.db"
    migrate_database(database_path)
    configure_database(monkeypatch, database_path)

    client = TestClient(app)
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert client.get("/health").status_code == 200


def test_readiness_fails_without_creating_missing_database(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "missing" / "tracker.db"
    configure_database(monkeypatch, database_path)

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert not database_path.exists()


def test_readiness_fails_when_database_has_not_been_migrated(
    tmp_path, monkeypatch
) -> None:
    database_path = tmp_path / "unmigrated.db"
    database_path.touch()
    configure_database(monkeypatch, database_path)

    response = TestClient(app).get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert str(database_path) not in response.text
