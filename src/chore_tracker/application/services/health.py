"""Application-level liveness and persistence readiness use cases."""

from __future__ import annotations

from typing import Protocol


class ReadinessProbe(Protocol):
    """Application-owned contract for checking persistence readiness."""

    def is_ready(self) -> bool:
        """Return whether the configured persistence store can serve requests."""


def get_health_status() -> dict[str, str]:
    """Return process liveness without depending on infrastructure."""
    return {"status": "ok"}


def is_database_ready(probe: ReadinessProbe) -> bool:
    """Delegate readiness to the configured persistence adapter."""
    return probe.is_ready()
