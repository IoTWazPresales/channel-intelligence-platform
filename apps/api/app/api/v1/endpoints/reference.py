"""Reference data for steward UIs (ISO countries, etc.) — not full operational catalog dumps."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.reference.iso3166_countries import list_countries_for_api
from app.services.imports.dsi_region_catalog import ensure_dim_region_from_iso_sync
from app.services.imports.dsi_steward_candidate_ops import StewardOpError

router = APIRouter()


@router.get("/countries")
async def list_iso_countries():
    """ISO 3166-1 alpha-2 list for DSI operating-region fallback (not demo commercial regions)."""
    return {"countries": list_countries_for_api()}


class EnsureRegionFromCountryBody(BaseModel):
    iso_alpha2: str = Field(..., min_length=2, max_length=2)


@router.post("/regions/ensure-from-country", status_code=200)
async def ensure_region_from_country(body: EnsureRegionFromCountryBody, db: AsyncSession = Depends(get_db)):
    """Return ``dim_region`` for ISO code, creating a governed row when missing."""

    def _work(sess) -> dict[str, object]:
        out = ensure_dim_region_from_iso_sync(sess, iso_alpha2=body.iso_alpha2)
        sess.commit()
        return out

    try:
        return await db.run_sync(_work)
    except StewardOpError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
