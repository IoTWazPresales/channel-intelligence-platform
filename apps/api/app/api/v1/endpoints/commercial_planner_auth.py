"""Commercial planner feature-flag guard (shared across route modules)."""

from __future__ import annotations

from fastapi import HTTPException

from app.core.feature_flags import commercial_planner_enabled


async def require_commercial_planner_enabled() -> None:
    if not commercial_planner_enabled():
        raise HTTPException(status_code=404, detail="Commercial planner is disabled")
