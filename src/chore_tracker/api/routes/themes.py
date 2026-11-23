"""Public theme catalog endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/themes", tags=["themes"])


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    preview_image: str


@router.get("", response_model=list[Theme], summary="List available themes")
def list_themes(request: Request) -> list[dict[str, Any]]:
    return request.app.state.theme_service.list_themes()
