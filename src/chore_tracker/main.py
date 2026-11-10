"""FastAPI application entry point."""

from fastapi import FastAPI

from chore_tracker.api.routes.health import router as health_router

app = FastAPI(title="Chore Tracker API")
app.include_router(health_router)
