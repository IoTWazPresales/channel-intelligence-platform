"""Tenant settings: read for any signed-in user, write for stewards."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import Role, get_current_user, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import SessionLocal
from app.services.tenant_settings import SETTING_VALIDATORS, list_settings, set_setting

router = APIRouter()


def _sync_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class SettingBody(BaseModel):
    value: Any


@router.get("")
def get_settings(db: Session = Depends(_sync_db), user: dict = Depends(get_current_user)):
    stored = list_settings(db, tenant_id_from_user(user))
    return {"settings": stored, "known_keys": sorted(SETTING_VALIDATORS)}


@router.put("/{key}")
def put_setting(
    key: str,
    body: SettingBody,
    db: Session = Depends(_sync_db),
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    actor = str(user.get("id") or user.get("email") or "steward")[:128]
    try:
        clean = set_setting(db, tenant_id_from_user(user), key, body.value, actor=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"key": key, "value": clean}
