"""Admin schema inspection and authenticated users' private UI layouts."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Response
from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import Role, get_current_user, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.db.session import engine
from app.models.iam import AppUser
from app.services.database_map import DatabaseMap, DatabaseMapReader
from app.services.saved_report_access import parse_user_id
from app.services.user_ui_layouts import (
    UiLayoutDocument,
    UiLayoutWrite,
    read_ui_layout,
    write_ui_layout,
)

router = APIRouter()
map_reader = DatabaseMapReader(engine)

LayoutKey = Annotated[str, Path(pattern=r"^[a-z][a-z0-9_.-]{0,79}$", max_length=80)]


async def layout_owner(
    user: Annotated[dict, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[str, int]:
    """Require a real active account, including in the app's transition/stub auth mode."""
    user_id = parse_user_id(user)
    tenant_id = tenant_id_from_user(user)
    if user_id is None or user_id <= 0:
        raise HTTPException(status_code=403, detail="A signed-in user account is required")
    actual_id = await db.scalar(
        select(AppUser.id).where(
            AppUser.id == user_id,
            AppUser.tenant_id == tenant_id,
            AppUser.is_active.is_(True),
        )
    )
    if actual_id is None:
        raise HTTPException(status_code=403, detail="A signed-in user account is required")
    return tenant_id, user_id


def _layout_storage_error(error: ProgrammingError) -> None:
    if getattr(error.orig, "sqlstate", None) == "42P01":
        raise HTTPException(
            status_code=503,
            detail="Personal layout storage is unavailable. Apply migration 20261120_0065.",
        ) from error
    raise error


@router.get("/admin/db-map", response_model=DatabaseMap)
async def database_map(
    response: Response,
    user: Annotated[dict, Depends(require_roles(Role.ADMIN))],
) -> DatabaseMap:
    """Public schema and estimated sizes only; the server caches metadata for 60 seconds."""
    response.headers["Cache-Control"] = "private, no-store"
    return await map_reader.read()


@router.get("/me/ui-layout/{key}", response_model=UiLayoutDocument)
async def get_ui_layout(
    key: LayoutKey,
    response: Response,
    owner: Annotated[tuple[str, int], Depends(layout_owner)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UiLayoutDocument:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await read_ui_layout(db, tenant_id=owner[0], user_id=owner[1], key=key)
    except ProgrammingError as error:
        _layout_storage_error(error)
        raise AssertionError("unreachable") from error


@router.put("/me/ui-layout/{key}", response_model=UiLayoutDocument)
async def put_ui_layout(
    key: LayoutKey,
    body: UiLayoutWrite,
    response: Response,
    owner: Annotated[tuple[str, int], Depends(layout_owner)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UiLayoutDocument:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return await write_ui_layout(
            db, tenant_id=owner[0], user_id=owner[1], key=key, value=body.value
        )
    except ProgrammingError as error:
        _layout_storage_error(error)
        raise AssertionError("unreachable") from error
