"""Tenant scoping helpers for P2-3 isolation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.sql import ColumnElement


DEFAULT_TENANT_ID = "default"


def tenant_id_from_user(user: dict | None) -> str:
    if not user:
        return DEFAULT_TENANT_ID
    raw = user.get("tenant_id")
    tid = str(raw).strip() if raw is not None else ""
    return tid or DEFAULT_TENANT_ID


def where_tenant(column: Any, user: dict | None) -> ColumnElement[bool]:
    """SQLAlchemy boolean expression: column == caller's tenant."""
    return column == tenant_id_from_user(user)
