"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chore_tracker.api.routes.health import router as health_router
from chore_tracker.config import get_settings

settings = get_settings()

app = FastAPI(title="Chore Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.app_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
