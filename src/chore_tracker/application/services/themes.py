"""Theme catalog and preference use cases.

Theme ids are stable API values. The catalog is the source of truth for which
themes are available and what preview image the frontend should render.
"""

from __future__ import annotations

from typing import Any, Protocol

DEFAULT_THEME_ID = "homestead"
THEME_CATALOG: tuple[dict[str, str], ...] = (
    {
        "id": "homestead",
        "name": "Homestead",
        "preview_image": "/theme-previews/homestead.png",
    },
    {
        "id": "quest",
        "name": "Quest",
        "preview_image": "/theme-previews/quest.png",
    },
    {
        "id": "sticker-club-v2",
        "name": "Sticker Club v2",
        "preview_image": "/theme-previews/sticker-club-v2.png",
    },
)


class ThemeError(Exception):
    """Expected theme failure translated by the HTTP adapter."""

    status_code = 400
    detail = "The theme request could not be completed."


class UnknownTheme(ThemeError):
    status_code = 422
    detail = "Theme is not available"


class ThemeFamilyMemberNotFound(ThemeError):
    status_code = 404
    detail = "Family member was not found"


class ThemeFamilyMemberInactive(ThemeError):
    status_code = 409
    detail = "Family member is inactive"


class ThemeAdministratorNotFound(ThemeError):
    status_code = 404
    detail = "Administrator was not found"


class ThemePersistence(Protocol):
    def family_member_theme_status(
        self, family_member_id: int
    ) -> dict[str, Any] | None: ...
    def set_family_member_theme(self, family_member_id: int, theme_id: str) -> bool: ...
    def set_administrator_theme(self, administrator_id: int, theme_id: str) -> bool: ...


class ThemeService:
    """Validate theme availability and coordinate durable preferences."""

    def __init__(
        self,
        persistence: ThemePersistence,
        catalog: tuple[dict[str, str], ...] = THEME_CATALOG,
    ) -> None:
        self._persistence = persistence
        self._catalog = tuple(dict(theme) for theme in catalog)

    def list_themes(self) -> list[dict[str, Any]]:
        return [dict(theme) for theme in self._catalog]

    def _require_available(self, theme_id: str) -> None:
        if not any(theme["id"] == theme_id for theme in self._catalog):
            raise UnknownTheme

    def set_family_member_theme(
        self, family_member_id: int, theme_id: str
    ) -> dict[str, str]:
        self._require_available(theme_id)
        status = self._persistence.family_member_theme_status(family_member_id)
        if status is None:
            raise ThemeFamilyMemberNotFound
        if not status["is_active"]:
            raise ThemeFamilyMemberInactive
        if not self._persistence.set_family_member_theme(family_member_id, theme_id):
            raise ThemeFamilyMemberNotFound
        return {"theme_id": theme_id}

    def set_administrator_theme(
        self, administrator_id: int, theme_id: str
    ) -> dict[str, str]:
        self._require_available(theme_id)
        if not self._persistence.set_administrator_theme(administrator_id, theme_id):
            raise ThemeAdministratorNotFound
        return {"theme_id": theme_id}
