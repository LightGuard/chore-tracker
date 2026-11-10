"""Application-level health status."""


def get_health_status() -> dict[str, str]:
    """Return a stable, non-sensitive health response."""
    return {"status": "ok"}
