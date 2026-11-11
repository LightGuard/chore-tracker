"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chore_tracker.api.routes.auth import router as auth_router
from chore_tracker.api.routes.chores import router as chores_router
from chore_tracker.api.routes.health import router as health_router
from chore_tracker.config import get_settings

settings = get_settings()

app = FastAPI(title="Chore Tracker API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted({settings.app_origin, settings.passkey_origin}),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(chores_router)
