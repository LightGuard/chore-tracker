"""Run the API using the configured host and port."""

from pathlib import Path

import uvicorn

from chore_tracker.config import Environment, get_settings

SOURCE_DIRECTORY = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    settings = get_settings()
    reload_enabled = settings.environment is Environment.DEVELOPMENT
    uvicorn.run(
        "chore_tracker.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=reload_enabled,
        # The repository root also contains the frontend and virtual
        # environment. Watch only the backend source in development.
        reload_dirs=[str(SOURCE_DIRECTORY)] if reload_enabled else None,
    )
