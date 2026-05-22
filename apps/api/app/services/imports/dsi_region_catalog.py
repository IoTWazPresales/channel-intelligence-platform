"""Governed ``dim_region`` helpers for ISO country fallback (DSI steward)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.dimensions import DimRegion
from app.reference.iso3166_countries import alpha2_name_index
from app.services.imports.dsi_steward_candidate_ops import StewardOpError


def ensure_dim_region_from_iso_sync(sess: Session, *, iso_alpha2: str) -> dict[str, object]:
    """Return existing ``dim_region`` for ISO alpha-2 or create one (code=alpha2, name=ISO name)."""
    code = (iso_alpha2 or "").strip().upper()
    if len(code) != 2 or code not in alpha2_name_index():
        raise StewardOpError(f"Unknown ISO alpha-2 country code: {iso_alpha2}", status_code=400)

    name = alpha2_name_index()[code]
    row = sess.scalar(select(DimRegion).where(func.lower(DimRegion.code) == code.lower()))
    if row is not None:
        return {
            "region_id": int(row.id),
            "region_code": row.code,
            "region_name": row.name,
            "created": False,
        }

    reg = DimRegion(code=code, name=name)
    sess.add(reg)
    try:
        sess.flush()
    except IntegrityError as exc:
        sess.rollback()
        row2 = sess.scalar(select(DimRegion).where(func.lower(DimRegion.code) == code.lower()))
        if row2 is not None:
            return {
                "region_id": int(row2.id),
                "region_code": row2.code,
                "region_name": row2.name,
                "created": False,
            }
        raise StewardOpError("dim_region code or name violates uniqueness", status_code=409) from exc

    return {
        "region_id": int(reg.id),
        "region_code": reg.code,
        "region_name": reg.name,
        "created": True,
    }


def suggest_region_id_for_iso_code(region_code_lower: dict[str, int], iso_alpha2: str | None) -> int | None:
    if not iso_alpha2:
        return None
    return region_code_lower.get(iso_alpha2.strip().lower())
