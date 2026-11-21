"""User-owned UI state, following tenant_settings' JSONB/upsert storage pattern."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAX_LAYOUT_BYTES = 262_144


class UiLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: dict[str, Any]

    @field_validator("value")
    @classmethod
    def bounded_json_object(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_LAYOUT_BYTES:
            raise ValueError("Layout must be at most 256 KiB")
        return value


class UiLayoutDocument(BaseModel):
    key: str
    value: dict[str, Any] | None
    updated_at: datetime | None


async def read_ui_layout(
    db: AsyncSession, *, tenant_id: str, user_id: int, key: str
) -> UiLayoutDocument:
    row = (
        await db.execute(
            text(
                "SELECT value, updated_at FROM public.user_ui_layout "
                "WHERE tenant_id = :tenant_id AND user_id = :user_id AND key = :key"
            ),
            {"tenant_id": tenant_id, "user_id": user_id, "key": key},
        )
    ).mappings().one_or_none()
    return UiLayoutDocument(
        key=key,
        value=row["value"] if row is not None else None,
        updated_at=row["updated_at"] if row is not None else None,
    )


async def write_ui_layout(
    db: AsyncSession,
    *,
    tenant_id: str,
    user_id: int,
    key: str,
    value: dict[str, Any],
) -> UiLayoutDocument:
    row = (
        await db.execute(
            text(
                "INSERT INTO public.user_ui_layout (tenant_id, user_id, key, value) "
                "VALUES (:tenant_id, :user_id, :key, CAST(:value AS jsonb)) "
                "ON CONFLICT (tenant_id, user_id, key) DO UPDATE "
                "SET value = EXCLUDED.value, updated_at = now() "
                "RETURNING value, updated_at"
            ),
            {
                "tenant_id": tenant_id,
                "user_id": user_id,
                "key": key,
                "value": json.dumps(value, ensure_ascii=False, allow_nan=False),
            },
        )
    ).mappings().one()
    document = UiLayoutDocument(key=key, value=row["value"], updated_at=row["updated_at"])
    await db.commit()
    return document
