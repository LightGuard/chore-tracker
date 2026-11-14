"""FastAPI application entry point."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from chore_tracker.adapters.sqlite.child_views import SQLiteChildViewsPersistence
from chore_tracker.adapters.sqlite.family_chore_management import (
    SQLiteFamilyChoreManagementPersistence,
)
from chore_tracker.api.routes.auth import router as auth_router
from chore_tracker.api.routes.child_views import router as child_views_router
from chore_tracker.api.routes.chores import router as chores_router
from chore_tracker.api.routes.family_members import router as family_members_router
from chore_tracker.api.routes.health import router as health_router
from chore_tracker.application.services.child_views import ChildViewsService
from chore_tracker.application.services.family_chore_management import (
    FamilyChoreManagementService,
)
from chore_tracker.config import get_settings

settings = get_settings()

app = FastAPI(title="Chore Tracker API")
app.state.settings = settings
app.state.management_service_factory = lambda: FamilyChoreManagementService(
    SQLiteFamilyChoreManagementPersistence(settings.database_path)
)
app.state.child_views_service = ChildViewsService(
    SQLiteChildViewsPersistence(settings.database_path)
)
app.state.child_views_service_factory = lambda configured_settings: ChildViewsService(
    SQLiteChildViewsPersistence(configured_settings.database_path)
)
app.state.child_views_today = lambda: datetime.now(
    ZoneInfo(settings.report_timezone)
).date()
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
# Register child views before the dynamic /family-members/{family_member_id} route.
app.include_router(child_views_router)
app.include_router(family_members_router)
