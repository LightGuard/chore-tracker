"""Tests for application startup and the health endpoint."""

from fastapi.testclient import TestClient

from chore_tracker.main import app


def test_application_starts_and_health_endpoint_returns_stable_status() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
