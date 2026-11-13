"""Health and readiness HTTP endpoints."""

from fastapi import APIRouter, Request, Response

from chore_tracker.application.services.health import (
    get_health_status,
    is_database_ready,
)
from chore_tracker.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health/live")
def liveness() -> dict[str, str]:
    """Report process liveness without checking infrastructure."""
    return get_health_status()


@router.get("/health")
@router.get("/health/ready")
def readiness(request: Request, response: Response) -> dict[str, str]:
    """Report whether the configured database is ready for application requests."""
    probe = request.app.state.readiness_probe_factory(get_settings())
    if not is_database_ready(probe):
        response.status_code = 503
        return {"status": "not_ready"}
    return {"status": "ok"}
