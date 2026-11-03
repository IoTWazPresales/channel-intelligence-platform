"""Lightweight feature toggles (env-based, default on for backward compatibility)."""

from __future__ import annotations

import os


def _env_truthy(name: str, *, default: bool = True) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def commercial_planner_enabled() -> bool:
    return _env_truthy("CIP_COMMERCIAL_PLANNER_ENABLED", default=True)
