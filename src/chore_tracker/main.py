"""FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import State

from chore_tracker.adapters.sqlite.auth import SQLiteAuthPersistence
from chore_tracker.adapters.sqlite.child_views import SQLiteChildViewsPersistence
from chore_tracker.adapters.sqlite.family_chore_management import (
    SQLiteFamilyChoreManagementPersistence,
)
from chore_tracker.adapters.sqlite.health import SQLiteReadinessProbe
from chore_tracker.adapters.sqlite.themes import SQLiteThemePersistence
from chore_tracker.adapters.sqlite.weekly_assignments import (
    SQLiteWeeklyAssignmentPersistence,
)
from chore_tracker.adapters.sqlite.weekly_reports import (
    SQLiteWeeklyReportPersistence,
)
from chore_tracker.adapters.sqlite.weekly_rollover import (
    SQLiteWeeklyRolloverPersistence,
)
from chore_tracker.api.routes.auth import router as auth_router
from chore_tracker.api.routes.child_views import router as child_views_router
from chore_tracker.api.routes.chores import router as chores_router
from chore_tracker.api.routes.family_members import router as family_members_router
from chore_tracker.api.routes.health import router as health_router
from chore_tracker.api.routes.reports import router as reports_router
from chore_tracker.api.routes.themes import router as themes_router
from chore_tracker.application.services.authentication import AuthenticationService
from chore_tracker.application.services.child_views import ChildViewsService
from chore_tracker.application.services.family_chore_management import (
    FamilyChoreManagementService,
)
from chore_tracker.application.services.themes import ThemeService
from chore_tracker.application.services.weekly_assignment_generation import (
    WeeklyAssignmentGenerationService,
)
from chore_tracker.application.services.weekly_reports import WeeklyReportService
from chore_tracker.application.services.weekly_rollover import WeeklyRolloverService
from chore_tracker.application.services.weekly_rollover_scheduler import (
    WeeklyRolloverScheduler,
)
from chore_tracker.config import Settings, get_settings


class _TestableState(State):
    """Application state that also mirrors values into the instance dictionary.

    Starlette keeps state values only in an internal mapping, so pytest's
    monkeypatch cannot restore a replaced attribute and instead deletes it.
    Mirroring keeps the application's dependency seams stable across tests.
    """

    def __setattr__(self, key: str, value: object) -> None:
        self._state[key] = value
        self.__dict__[key] = value

    def __delattr__(self, key: str) -> None:
        del self._state[key]
        self.__dict__.pop(key, None)

    def __setitem__(self, key: str, value: object) -> None:
        self._state[key] = value
        self.__dict__[key] = value

    def __delitem__(self, key: str) -> None:
        del self._state[key]
        self.__dict__.pop(key, None)


settings = get_settings()


def create_weekly_rollover_scheduler(
    configured_settings: Settings,
) -> WeeklyRolloverScheduler:
    """Compose the scheduler from configured persistence and reporting services."""
    timezone_name = configured_settings.report_timezone
    return WeeklyRolloverScheduler(
        WeeklyRolloverService(
            reports=WeeklyReportService(
                SQLiteWeeklyReportPersistence(configured_settings.database_path),
                timezone_name,
            ),
            assignments=WeeklyAssignmentGenerationService(
                SQLiteWeeklyAssignmentPersistence(configured_settings.database_path),
                timezone_name,
            ),
            persistence=SQLiteWeeklyRolloverPersistence(
                configured_settings.database_path
            ),
            timezone_name=timezone_name,
            delivery_time=configured_settings.report_delivery_time,
        )
    )


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Run scheduler catch-up on startup and stop it cleanly on shutdown."""
    configured_settings = application.state.settings
    scheduler_task: asyncio.Task[None] | None = None
    if configured_settings.weekly_rollover_enabled:
        scheduler = application.state.weekly_rollover_scheduler_factory(
            configured_settings
        )
        scheduler_task = asyncio.create_task(
            scheduler.run_forever(), name="weekly-rollover"
        )
    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task


app = FastAPI(title="Chore Tracker API", lifespan=lifespan)
app.state = _TestableState()
app.state.settings = settings
app.state.weekly_rollover_scheduler_factory = create_weekly_rollover_scheduler
app.state.readiness_probe_factory = lambda configured_settings: SQLiteReadinessProbe(
    configured_settings.database_path
)
app.state.authentication_service_factory = lambda configured_settings, **verifiers: (
    AuthenticationService(
        SQLiteAuthPersistence(configured_settings.database_path),
        rp_id=configured_settings.passkey_rp_id,
        origin=configured_settings.passkey_origin,
        **verifiers,
    )
)
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
app.state.weekly_assignment_generation_service = WeeklyAssignmentGenerationService(
    SQLiteWeeklyAssignmentPersistence(settings.database_path),
    settings.report_timezone,
)
app.state.report_service_factory = lambda: WeeklyReportService(
    SQLiteWeeklyReportPersistence(settings.database_path),
    settings.report_timezone,
)
app.state.theme_service = ThemeService(SQLiteThemePersistence(settings.database_path))
app.add_middleware(
    CORSMiddleware,
    allow_origins=sorted({settings.app_origin, settings.passkey_origin}),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(health_router)
app.include_router(themes_router)
app.include_router(auth_router)
app.include_router(chores_router)
app.include_router(reports_router)
# Register child views before the dynamic /family-members/{family_member_id} route.
app.include_router(child_views_router)
app.include_router(family_members_router)
