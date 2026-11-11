"""Integration test for the existing health endpoint and application startup."""

from fastapi.testclient import TestClient

from chore_tracker.main import app


def test_health_endpoint_returns_successful_response() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
