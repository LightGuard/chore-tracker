"""Run the API using the configured host and port."""

import uvicorn

from chore_tracker.config import Environment, get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "chore_tracker.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.environment is Environment.DEVELOPMENT,
    )
