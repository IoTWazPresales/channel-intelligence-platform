"""Listing Capture registry API (LC-U1)."""

from __future__ import annotations

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.db.session_sync import SessionLocal
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.listing_capture.marketplace_vocab import (
    LISTING_MARKETPLACES,
    LISTING_SOURCES,
    LISTING_STATUSES,
)
from app.services.listing_capture.intelligence_v1 import build_listing_intelligence
from app.services.listing_capture.registry import (
    confirm_proposal,
    confirm_suggested_proposals,
    create_listing,
    import_listings_csv,
    list_proposals,
    list_recent_observations,
    listing_to_dict,
    observation_to_dict,
    poll_active_listings,
    reject_proposal,
    reparse_observation,
    set_listing_status,
)
from sqlalchemy import select

router = APIRouter()


def _actor(x_user_id: str | None) -> str:
    return (x_user_id or "demo-user").strip() or "demo-user"


class ListingCreate(BaseModel):
    customer_id: int
    url: str
    marketplace: str
    product_id: int | None = None
    external_id: str | None = None
    notes: str | None = None


class StatusBody(BaseModel):
    status: str


class ConfirmProposalBody(BaseModel):
    url: str = Field(min_length=1)


class PollBody(BaseModel):
    marketplaces: list[str] | None = None
    limit: int | None = Field(default=None, ge=1, le=500)


@router.get("/meta")
def listing_meta():
    return {
        "marketplaces": list(LISTING_MARKETPLACES),
        "statuses": list(LISTING_STATUSES),
        "sources": list(LISTING_SOURCES),
    }


@router.get("/listings")
def list_listings(
    customer_id: int | None = Query(default=None),
    marketplace: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    with SessionLocal() as session:
        try:
            stmt = select(CustomerListing).order_by(CustomerListing.id.desc())
            if customer_id is not None:
                stmt = stmt.where(CustomerListing.customer_id == customer_id)
            if marketplace:
                stmt = stmt.where(CustomerListing.marketplace == marketplace.strip().lower())
            if status:
                stmt = stmt.where(CustomerListing.status == status.strip().lower())
            rows = list(session.scalars(stmt).all())
        except Exception:
            return {"items": [], "total": 0, "data_unavailable": True}
        total = len(rows)
        start = (page - 1) * page_size
        page_rows = rows[start : start + page_size]
        return {
            "items": [listing_to_dict(r) for r in page_rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "data_unavailable": False,
        }


@router.post("/listings")
def post_listing(
    body: ListingCreate,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with SessionLocal() as session:
        try:
            row = create_listing(
                session,
                customer_id=body.customer_id,
                url=body.url,
                marketplace=body.marketplace,
                product_id=body.product_id,
                source="manual",
                registered_by=_actor(x_user_id),
                external_id=body.external_id,
                notes=body.notes,
            )
            session.commit()
            session.refresh(row)
            return listing_to_dict(row)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "listing tables unavailable — migration pending?", "error": str(exc)},
            ) from exc


@router.patch("/listings/{listing_id}/status")
def patch_status(
    listing_id: int,
    body: StatusBody,
):
    with SessionLocal() as session:
        row = session.get(CustomerListing, listing_id)
        if row is None:
            raise HTTPException(status_code=404, detail="listing not found")
        try:
            set_listing_status(session, row, status=body.status)
            session.commit()
            session.refresh(row)
            return listing_to_dict(row)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/listings/import-csv")
async def post_import_csv(
    file: UploadFile = File(...),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    raw = await file.read()
    text = raw.decode("utf-8-sig", errors="replace")
    with SessionLocal() as session:
        try:
            result = import_listings_csv(session, csv_text=text, registered_by=_actor(x_user_id))
            session.commit()
            return result
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "listing import unavailable", "error": str(exc)},
            ) from exc


@router.get("/proposals")
def get_proposals(status: str = Query(default="proposed")):
    with SessionLocal() as session:
        try:
            return {"items": list_proposals(session, status=status), "data_unavailable": False}
        except Exception:
            return {"items": [], "data_unavailable": True}


@router.post("/proposals/confirm-suggested")
def post_confirm_suggested(
    limit: int | None = Query(default=None, ge=1, le=500),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    """Steward bulk-confirm: only seeds with an auto-finder URL. Human-initiated."""
    with SessionLocal() as session:
        try:
            result = confirm_suggested_proposals(
                session, registered_by=_actor(x_user_id), limit=limit
            )
            session.commit()
            return result
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "confirm-suggested unavailable", "error": str(exc)},
            ) from exc


@router.post("/proposals/{seed_id}/confirm")
def post_confirm_proposal(
    seed_id: int,
    body: ConfirmProposalBody,
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
):
    with SessionLocal() as session:
        try:
            listing = confirm_proposal(
                session, seed_id=seed_id, url=body.url, registered_by=_actor(x_user_id)
            )
            session.commit()
            session.refresh(listing)
            return listing_to_dict(listing)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/proposals/{seed_id}/reject")
def post_reject_proposal(seed_id: int):
    with SessionLocal() as session:
        try:
            seed = reject_proposal(session, seed_id=seed_id)
            session.commit()
            return {"id": seed.id, "status": seed.status}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/observations")
def get_observations(
    marketplace: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Latest poll extractions + CPOR activation flags (SQL-backed)."""
    with SessionLocal() as session:
        try:
            items = list_recent_observations(session, marketplace=marketplace, limit=limit)
            return {"items": items, "total": len(items), "data_unavailable": False}
        except Exception:
            return {"items": [], "total": 0, "data_unavailable": True}


@router.get("/intelligence")
def get_listing_intelligence():
    """P5 intelligence v1: ≥14d span, activation, price drift, not_activated worklist."""
    with SessionLocal() as session:
        try:
            return build_listing_intelligence(session)
        except Exception:
            return {
                "min_span_days": 14,
                "listings": 0,
                "ready": 0,
                "accumulating": 0,
                "not_activated_worklist": 0,
                "items": [],
                "worklist": [],
                "data_unavailable": True,
            }


@router.post("/poll")
def post_poll(body: PollBody | None = None):
    """Manual one-shot poll of active listings (writes listing_observation rows)."""
    import os

    from app.services.listing_capture.observation import default_http_get

    body = body or PollBody()
    live = os.environ.get("CIP_LISTING_LIVE_FETCH", "").strip().lower() in ("1", "true", "on")
    if not live:
        raise HTTPException(
            status_code=503,
            detail="CIP_LISTING_LIVE_FETCH is not enabled — cannot poll live storefronts",
        )
    with SessionLocal() as session:
        try:
            result = poll_active_listings(
                session,
                marketplaces=body.marketplaces,
                http_get=default_http_get,
                limit=body.limit,
            )
            session.commit()
            return result
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "listing poll unavailable", "error": str(exc)},
            ) from exc


@router.post("/observations/{observation_id}/reparse")
def post_reparse(observation_id: int):
    with SessionLocal() as session:
        obs = session.get(ListingObservation, observation_id)
        if obs is None:
            raise HTTPException(status_code=404, detail="observation not found")
        listing = session.get(CustomerListing, obs.listing_id)
        mkt = listing.marketplace if listing else "takealot"
        reparse_observation(session, obs, marketplace=mkt)
        session.commit()
        session.refresh(obs)
        return observation_to_dict(obs, listing)
