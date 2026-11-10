"""Health and readiness HTTP endpoint."""

from fastapi import APIRouter

from chore_tracker.application.services.health import get_health_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Report whether the application is ready to receive requests."""
    return get_health_status()
