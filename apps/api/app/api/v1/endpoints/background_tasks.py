"""Pollable background task registry (Redis-backed)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException

from app.services.background_tasks.store import BackgroundTaskStore

router = APIRouter()


def _require_admin(x_user_role: str | None) -> None:
    if (x_user_role or "").strip().lower() != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def _isoify_task(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for k in ("created_at", "updated_at"):
        v = out.get(k)
        if isinstance(v, (int, float)):
            from datetime import datetime, timezone

            out[k] = datetime.fromtimestamp(float(v), tz=timezone.utc).isoformat()
    return out


@router.get("")
async def list_background_tasks(
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> dict[str, Any]:
    _require_admin(x_user_role)
    rows = BackgroundTaskStore.list_tasks(limit=100)
    from app.core.redis_sync import redis_available

    return {"items": [_isoify_task(r) for r in rows], "redis_available": redis_available()}


@router.get("/{task_id}")
async def get_background_task(
    task_id: str,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> dict[str, Any]:
    _require_admin(x_user_role)
    row = BackgroundTaskStore.get_task(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return _isoify_task(row)


@router.post("/{task_id}/dismiss")
async def dismiss_background_task(
    task_id: str,
    x_user_role: str | None = Header(default=None, alias="X-User-Role"),
) -> dict[str, Any]:
    _require_admin(x_user_role)
    ok = BackgroundTaskStore.dismiss_task(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"id": task_id, "dismissed": True}
