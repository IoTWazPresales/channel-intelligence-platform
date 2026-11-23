"""Listing Capture registry API (LC-U1)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.security import Role, get_current_user, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimProduct
from app.models.listing_capture import CustomerListing, ListingObservation
from app.services.grid_fields import customer_labels_sync, fact_row_dict, reference_fields
from app.services.listing_capture import sites as site_service
from app.services.listing_capture.adapters import adapter_keys, configured_adapter
from app.services.listing_capture.intelligence_v1 import build_listing_intelligence
from app.services.listing_capture.marketplace_vocab import (
    LISTING_SOURCES,
    LISTING_STATUSES,
)
from app.services.listing_capture.registry import (
    confirm_proposal,
    confirm_suggested_proposals,
    create_listing,
    import_listings_csv,
    last_ok_fetch_by_listing,
    list_proposals,
    list_recent_observations,
    listing_to_dict,
    observation_to_dict,
    poll_active_listings,
    product_labels,
    reject_proposal,
    reparse_observation,
    set_listing_status,
)

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
    """Vocabulary for the listing forms. ``marketplaces`` are the tenant's active sites."""
    with SessionLocal() as session:
        try:
            rows = [r for r in site_service.list_sites(session) if r.is_active]
        except Exception:
            rows = []
        return {
            "marketplaces": [r.site_key for r in rows],
            "sites": [
                {
                    "site_key": r.site_key,
                    "display_name": r.display_name,
                    "configured": configured_adapter(site_service.site_config_from_row(r)) is not None,
                }
                for r in rows
            ],
            "adapter_keys": list(adapter_keys()),
            "statuses": list(LISTING_STATUSES),
            "sources": list(LISTING_SOURCES),
        }


class SiteFields(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    adapter_key: str | None = Field(default=None, max_length=32)
    product_url_pattern: str | None = Field(default=None, max_length=1024)
    page_id_pattern: str | None = Field(default=None, max_length=256)
    search_url_pattern: str | None = Field(default=None, max_length=1024)
    details_url_pattern: str | None = Field(default=None, max_length=1024)
    first_party_seller: str | None = Field(default=None, max_length=256)
    rate_limit_seconds: float | None = None
    is_active: bool | None = None


class SiteCreate(SiteFields):
    site_key: str = Field(min_length=1, max_length=32)


class SiteSellerBody(BaseModel):
    seller_names: list[str] = Field(default_factory=list, max_length=20)
    seller_ids: list[str] = Field(default_factory=list, max_length=20)


def _user_actor(user: dict) -> str:
    return str(user.get("email") or user.get("id") or "unknown")


def _site_payload(session, row) -> dict:
    customers = customer_labels_sync(session, [s.customer_id for s in row.sellers or []])
    return site_service.site_to_dict(row, customers=customers)


@router.get("/sites")
def get_sites():
    """The tenant's listing sites, their page reader and link patterns, and each customer's sellers."""
    with SessionLocal() as session:
        try:
            rows = site_service.list_sites(session)
        except Exception:
            return {"items": [], "adapter_keys": list(adapter_keys()), "data_unavailable": True}
        customers = customer_labels_sync(session, [s.customer_id for r in rows for s in r.sellers or []])
        return {
            "items": [site_service.site_to_dict(r, customers=customers) for r in rows],
            "adapter_keys": list(adapter_keys()),
            "data_unavailable": False,
        }


@router.post("/sites")
def post_site(body: SiteCreate, user: dict = Depends(require_roles(Role.STEWARD))):
    with SessionLocal() as session:
        try:
            row = site_service.create_site(
                session,
                tenant_id=tenant_id_from_user(user),
                site_key=body.site_key,
                fields=body.model_dump(exclude={"site_key"}, exclude_unset=True),
                actor=_user_actor(user),
            )
            session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _site_payload(session, site_service.get_site(session, row.id))


class SiteOnboardBody(BaseModel):
    customer_id: int
    site_key: str = Field(min_length=1, max_length=32)
    domain: str = Field(min_length=1, max_length=253)
    example_urls: list[str] = Field(default_factory=list, max_length=8)


@router.post("/sites/onboard")
def post_site_onboard(body: SiteOnboardBody, user: dict = Depends(require_roles(Role.STEWARD))):
    """Record a site key and domain for a reporting customer that has neither. Steward only."""
    from app.services.listing_capture.site_onboarding import SiteOnboardError, record_customer_site

    with SessionLocal() as session:
        try:
            result = record_customer_site(
                session,
                tenant_id=tenant_id_from_user(user),
                customer_id=body.customer_id,
                site_key=body.site_key,
                domain=body.domain,
                example_urls=body.example_urls,
                actor=_user_actor(user),
            )
            session.commit()
        except SiteOnboardError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result


@router.patch("/sites/{site_id}")
def patch_site(site_id: int, body: SiteFields, user: dict = Depends(require_roles(Role.STEWARD))):
    with SessionLocal() as session:
        row = site_service.get_site(session, site_id)
        if row is None:
            raise HTTPException(status_code=404, detail="site not found")
        try:
            site_service.update_site(session, row, fields=body.model_dump(exclude_unset=True), actor=_user_actor(user))
            session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _site_payload(session, site_service.get_site(session, site_id))


@router.put("/sites/{site_id}/sellers/{customer_id}")
def put_site_seller(
    site_id: int,
    customer_id: int,
    body: SiteSellerBody,
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    """Set a customer's own seller names / ids on a site (the buy box is theirs when it matches)."""
    with SessionLocal() as session:
        row = site_service.get_site(session, site_id)
        if row is None:
            raise HTTPException(status_code=404, detail="site not found")
        try:
            site_service.set_site_seller(
                session,
                row,
                customer_id=customer_id,
                seller_names=body.seller_names,
                seller_ids=body.seller_ids,
                actor=_user_actor(user),
            )
            session.commit()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _site_payload(session, site_service.get_site(session, site_id))


@router.post("/sites/autoconfigure")
def post_autoconfigure_sites(user: dict = Depends(require_roles(Role.STEWARD))):
    """Fill empty listing sites for this tenant's reporting customers. Steward only."""
    from app.services.listing_capture.autoconfig import autoconfigure_sites
    from app.services.listing_capture.observation import default_http_get, listing_live_fetch_enabled
    from app.services.listing_capture.site_fetch import STEWARD_RUN_TIME_LIMIT_SECONDS

    live = listing_live_fetch_enabled()
    with SessionLocal() as session:
        try:
            report = autoconfigure_sites(
                session,
                tenant_id=tenant_id_from_user(user),
                http_get=default_http_get if live else None,
                # The steward waits for this answer: a short budget per phase, the rest
                # resumes on the next run.
                time_limit_seconds=STEWARD_RUN_TIME_LIMIT_SECONDS,
            )
            session.commit()
        except Exception:
            session.rollback()
            logging.getLogger(__name__).exception("listing site autoconfigure failed")
            return {"configured": [], "excluded": [], "needs_pattern": [], "data_unavailable": True}
        return {**report, "data_unavailable": False}


@router.get("/capture-health")
def get_capture_health(user: dict = Depends(get_current_user)):
    """Per-site capture posture for the caller's tenant: configured, newest price, skips, exclusions."""
    from app.services.listing_capture.autoconfig import capture_health

    with SessionLocal() as session:
        try:
            return capture_health(session, tenant_id=tenant_id_from_user(user))
        except Exception:
            session.rollback()
            logging.getLogger(__name__).exception("listing capture health failed")
            return {
                "tenant_id": tenant_id_from_user(user),
                "data_unavailable": True,
                "sites": [],
                "listings_due": 0,
                "skipped_not_configured": {},
                "not_polled": [],
                "last_poll_run": None,
                "last_autoconfigure_run": None,
                "exclusions": [],
                "configured": [],
            }


@router.get("/stock-not-listed")
def get_stock_not_listed(
    customer_id: int | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    user: dict = Depends(get_current_user),
):
    """Reported products in stock on the latest report with no watched listing. Read-only."""
    from app.services.listing_capture.stock_not_listed import stock_not_listed

    with SessionLocal() as session:
        return stock_not_listed(
            session, tenant_id_from_user(user), customer_id=customer_id, limit=limit
        )


@router.delete("/sites/{site_id}/sellers/{customer_id}")
def delete_site_seller(site_id: int, customer_id: int, user: dict = Depends(require_roles(Role.STEWARD))):
    with SessionLocal() as session:
        row = site_service.get_site(session, site_id)
        if row is None:
            raise HTTPException(status_code=404, detail="site not found")
        if not site_service.delete_site_seller(session, row, customer_id=customer_id):
            raise HTTPException(status_code=404, detail="seller not found for this customer")
        session.commit()
        return _site_payload(session, site_service.get_site(session, site_id))


def listing_grid_row_dict(
    row: CustomerListing,
    *,
    products: dict[int, tuple[str | None, str | None]],
    last_ok_fetch: dict,
    customers: dict[int, tuple[str, str]],
    site=None,
) -> dict:
    """Listings grid row (grid ``listings``): registry columns under ``listing_to_dict``, plus customer name and code."""
    return {
        **fact_row_dict(row, "listings"),
        **listing_to_dict(row, products=products, last_ok_fetch=last_ok_fetch, site=site),
        **reference_fields(customer_id=row.customer_id, customers=customers),
    }


def _listing_conditions(
    *, customer_id: int | None, marketplace: str | None, status: str | None
) -> tuple[list, list]:
    """(conditions without the status filter, the status condition if any)."""
    base: list = []
    if customer_id is not None:
        base.append(CustomerListing.customer_id == customer_id)
    if marketplace and marketplace.strip():
        base.append(CustomerListing.marketplace == marketplace.strip().lower())
    status_cond: list = []
    if status and status.strip():
        status_cond.append(CustomerListing.status == status.strip().lower())
    return base, status_cond


def listing_counts(
    session,
    *,
    customer_id: int | None,
    marketplace: str | None,
    status: str | None,
) -> tuple[int, dict[str, int], int]:
    """Real counts over ALL rows matching the filters, never the page (BACKLOG-226).

    Returns ``(total, status_counts, unlinked)``. ``total`` and ``unlinked`` follow every filter.
    ``status_counts`` follows the customer and marketplace filters only, so choosing one status
    still shows how the rest are split.
    """
    base, status_cond = _listing_conditions(
        customer_id=customer_id, marketplace=marketplace, status=status
    )
    head = session.execute(
        select(
            func.count(CustomerListing.id).label("total"),
            func.count(CustomerListing.id).filter(CustomerListing.product_id.is_(None)).label("unlinked"),
        ).where(*base, *status_cond)
    )
    row = next(iter(head), None)
    total = int(row.total) if row is not None else 0
    unlinked = int(row.unlinked) if row is not None else 0
    by_status = session.execute(
        select(CustomerListing.status.label("status"), func.count(CustomerListing.id).label("n"))
        .where(*base)
        .group_by(CustomerListing.status)
    )
    return total, {str(r.status): int(r.n) for r in by_status}, unlinked


@router.get("/listings")
def list_listings(
    customer_id: int | None = Query(default=None),
    marketplace: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
):
    """One page of listings plus real counts over every row matching the filters.

    ``total`` counts all matching rows; ``status_counts`` splits the customer/marketplace-filtered
    set by status; ``unlinked`` counts matching rows with no product.
    """
    with SessionLocal() as session:
        try:
            base, status_cond = _listing_conditions(
                customer_id=customer_id, marketplace=marketplace, status=status
            )
            total, status_counts, unlinked = listing_counts(
                session, customer_id=customer_id, marketplace=marketplace, status=status
            )
            page_rows = list(
                session.scalars(
                    select(CustomerListing)
                    .where(*base, *status_cond)
                    .order_by(CustomerListing.id.desc())
                    .limit(page_size)
                    .offset((page - 1) * page_size)
                ).all()
            )
        except Exception:
            return {
                "items": [],
                "total": 0,
                "status_counts": {},
                "unlinked": 0,
                "data_unavailable": True,
            }
        products = product_labels(session, [r.product_id for r in page_rows])
        last_ok = last_ok_fetch_by_listing(session, [r.id for r in page_rows])
        customers = customer_labels_sync(session, [r.customer_id for r in page_rows])
        resolver = site_service.SiteResolver.load(session, page_rows)
        return {
            "items": [
                listing_grid_row_dict(
                    r,
                    products=products,
                    last_ok_fetch=last_ok,
                    customers=customers,
                    site=resolver.site_for(r),
                )
                for r in page_rows
            ],
            "total": total,
            "status_counts": status_counts,
            "unlinked": unlinked,
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
            return listing_to_dict(
                row,
                products=product_labels(session, [row.product_id]),
                site=site_service.site_for_listing(session, row),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={"message": "listing tables unavailable - migration pending?", "error": str(exc)},
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
            return listing_to_dict(
                row,
                products=product_labels(session, [row.product_id]),
                last_ok_fetch=last_ok_fetch_by_listing(session, [row.id]),
                site=site_service.site_for_listing(session, row),
            )
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
            return listing_to_dict(
                listing,
                products=product_labels(session, [listing.product_id]),
                site=site_service.site_for_listing(session, listing),
            )
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
    """P5 intelligence v1: =14d span, activation, price drift, not_activated worklist."""
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
                "timing_alerts": [],
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
            detail="CIP_LISTING_LIVE_FETCH is not enabled - cannot poll live storefronts",
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


@router.get("/quality")
def get_listing_quality():
    """One row per listing from the latest stored snapshot. No fetch."""
    from sqlalchemy import text

    from app.services.listing_capture.quality import CHECK_KEYS

    with SessionLocal() as session:
        rows = session.execute(
            text(
                """
                SELECT l.id, l.marketplace, l.product_id, o.fetched_at, o.parse_status, o.parse_flags
                FROM customer_listing l
                LEFT JOIN LATERAL (
                    SELECT fetched_at, parse_status, parse_flags
                    FROM listing_observation
                    WHERE listing_id = l.id
                      AND raw_snapshot IS NOT NULL
                    ORDER BY fetched_at DESC
                    LIMIT 1
                ) o ON true
                ORDER BY l.id
                """
            )
        ).mappings().all()
        items = []
        for row in rows:
            flags = row["parse_flags"] if isinstance(row["parse_flags"], dict) else {}
            quality = flags.get("quality") if isinstance(flags.get("quality"), dict) else {}
            checks = quality.get("checks") if isinstance(quality.get("checks"), dict) else {}
            item = {
                "listing_id": int(row["id"]),
                "marketplace": row["marketplace"],
                "product_id": row["product_id"],
                "fetched_at": row["fetched_at"].isoformat() if row["fetched_at"] is not None else None,
                "flag_count": int(quality.get("flag_count") or 0),
                "rules_version": quality.get("rules_version"),
                "search_position": "deferred",
            }
            for key in CHECK_KEYS:
                cell = checks.get(key) if isinstance(checks.get(key), dict) else None
                item[key] = cell["status"] if cell else "no_data"
                item[f"{key}_evidence"] = cell["evidence"] if cell else "No data"
            items.append(item)
        configured = [
            row.site_key
            for row in site_service.list_sites(session)
            if configured_adapter(site_service.site_config_from_row(row)) is not None
        ]
        return {"items": items, "retailers_checked": configured, "search_position": "deferred"}


@router.post("/observations/{observation_id}/reparse")
def post_reparse(observation_id: int):
    with SessionLocal() as session:
        obs = session.get(ListingObservation, observation_id)
        if obs is None:
            raise HTTPException(status_code=404, detail="observation not found")
        listing = session.get(CustomerListing, obs.listing_id)
        reparse_observation(session, obs)
        session.commit()
        session.refresh(obs)
        return observation_to_dict(obs, listing)


class QueueDecision(BaseModel):
    action: str
    url: str | None = None
    product_id: int | None = Field(default=None, gt=0)


def _queue_dict(
    row,
    *,
    customer_name: str | None = None,
    listing_url: str | None = None,
    product_label: str | None = None,
    candidates: list | None = None,
) -> dict:
    return {
        "id": int(row.id),
        "site_id": int(row.site_id),
        "product_id": int(row.product_id) if row.product_id is not None else None,
        "customer_id": row.customer_id,
        "customer_name": customer_name,
        "listing_id": row.listing_id,
        "listing_url": listing_url,
        "product_label": product_label,
        "reason": row.reason,
        "candidates": candidates if candidates is not None else row.candidates or [],
        "status": row.status,
        "evidence": row.evidence or {},
    }


def _queue_payloads(session, rows: list, tenant_id: str) -> list[dict]:
    customer_ids = {row.customer_id for row in rows if row.customer_id is not None}
    listing_ids = {row.listing_id for row in rows if row.listing_id is not None}
    product_ids = {row.product_id for row in rows if row.product_id is not None}
    for row in rows:
        product_ids.update(
            int(candidate["product_id"])
            for candidate in row.candidates or []
            if isinstance(candidate, dict) and candidate.get("product_id") is not None
        )
    customers = dict(
        session.execute(
            select(DimCustomer.id, DimCustomer.name).where(
                DimCustomer.tenant_id == tenant_id,
                DimCustomer.id.in_(customer_ids),
            )
        ).all()
    )
    listings = dict(
        session.execute(
            select(CustomerListing.id, CustomerListing.url)
            .join(DimCustomer, DimCustomer.id == CustomerListing.customer_id)
            .where(
                DimCustomer.tenant_id == tenant_id,
                CustomerListing.id.in_(listing_ids),
            )
        ).all()
    )
    products = {
        int(product.id): str(product.name or product.sales_model_name or product.sku)
        for product in session.scalars(
            select(DimProduct).where(
                DimProduct.tenant_id == tenant_id,
                DimProduct.id.in_(product_ids),
            )
        ).all()
    }
    payloads = []
    for row in rows:
        candidates = []
        for candidate in row.candidates or []:
            if not isinstance(candidate, dict):
                continue
            item = dict(candidate)
            if item.get("product_id") is not None:
                pid = int(item["product_id"])
                if pid not in products:
                    continue
                item["label"] = products[pid]
            candidates.append(item)
        payloads.append(
            _queue_dict(
                row,
                customer_name=customers.get(row.customer_id),
                listing_url=listings.get(row.listing_id),
                product_label=products.get(row.product_id),
                candidates=candidates,
            )
        )
    return payloads


@router.get("/link-queue")
def get_link_queue(user: dict = Depends(get_current_user)):
    """Product-page and unlinked-listing cases awaiting a steward decision."""
    from app.services.listing_capture.links import list_open_queue

    tenant_id = tenant_id_from_user(user)
    with SessionLocal() as session:
        try:
            rows = list_open_queue(session, tenant_id)
            items = _queue_payloads(session, rows, tenant_id)
        except Exception:
            session.rollback()
            return {"items": [], "data_unavailable": True}
        return {"items": items, "data_unavailable": False}


@router.post("/link-queue/{queue_id}")
def post_link_queue(queue_id: int, body: QueueDecision, user: dict = Depends(require_roles(Role.STEWARD))):
    from app.models.listing_link import ListingLinkQueue
    from app.services.listing_capture.links import decide_queue

    tenant_id = tenant_id_from_user(user)
    with SessionLocal() as session:
        row = session.scalar(
            select(ListingLinkQueue)
            .where(
                ListingLinkQueue.id == queue_id,
                ListingLinkQueue.tenant_id == tenant_id,
            )
            .with_for_update()
        )
        if row is None:
            raise HTTPException(status_code=404, detail="queue item not found")
        try:
            decide_queue(
                session,
                row,
                action=body.action.strip().lower(),
                url=body.url,
                product_id=body.product_id,
                actor=_user_actor(user),
            )
            session.commit()
        except ValueError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _queue_payloads(session, [row], tenant_id)[0]


@router.post("/links/{link_id}/undo")
def post_undo_auto_link(
    link_id: int,
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    """One-click Undo for an automatic Discovery V2 link."""
    from app.services.listing_capture.links import undo_auto_link

    with SessionLocal() as session:
        try:
            result = undo_auto_link(
                session,
                tenant_id=tenant_id_from_user(user),
                link_id=link_id,
                user=user,
            )
            session.commit()
        except LookupError as exc:
            session.rollback()
            raise HTTPException(status_code=404, detail="link not found") from exc
        except ValueError as exc:
            session.rollback()
            raise HTTPException(
                status_code=409,
                detail={"code": "changed_since_apply", "message": str(exc)},
            ) from exc
        return result


@router.post("/listings/{listing_id}/learn")
def post_learn_link(listing_id: int, user: dict = Depends(require_roles(Role.STEWARD))):
    """Search the site for this product's page. A single corroborated match is remembered."""
    import os

    from app.services.listing_capture.adapters import adapter_module
    from app.services.listing_capture.links import learn_link
    from app.services.listing_capture.observation import default_http_get

    live = os.environ.get("CIP_LISTING_LIVE_FETCH", "").strip().lower() in ("1", "true", "on")
    if not live:
        raise HTTPException(status_code=503, detail="CIP_LISTING_LIVE_FETCH is not enabled")
    with SessionLocal() as session:
        listing = session.get(CustomerListing, listing_id)
        if listing is None:
            raise HTTPException(status_code=404, detail="listing not found")
        site = site_service.site_for_listing(session, listing)
        if site is None:
            raise HTTPException(status_code=422, detail="site is not configured")
        module = adapter_module(site.adapter_key)
        headers = module.request_headers(site) if module is not None else {}

        def http_get(url: str, _headers=None):
            return default_http_get(url, headers=headers)

        result = learn_link(session, listing, site, http_get=http_get, actor=_user_actor(user))
        session.commit()
        return result


@router.get("/listings/{listing_id}/offers")
def get_listing_offers(listing_id: int):
    """Offers on the latest observation. The buy-box row is the shopper's price."""
    from app.models.listing_offer import ListingOffer

    with SessionLocal() as session:
        obs_id = session.scalar(
            select(ListingObservation.id)
            .where(ListingObservation.listing_id == listing_id)
            .order_by(ListingObservation.fetched_at.desc(), ListingObservation.id.desc())
            .limit(1)
        )
        if obs_id is None:
            return {"items": [], "shoppers_price": None, "buy_box_label": None}
        rows = list(session.scalars(select(ListingOffer).where(ListingOffer.observation_id == int(obs_id))).all())
        items = [
            {
                "seller_name": r.seller_name,
                "seller_id": r.seller_id,
                "price": float(r.price) if r.price is not None else None,
                "availability": r.availability,
                "is_buy_box": bool(r.is_buy_box),
                "is_own_seller": r.is_own_seller,
                "label": "Own" if r.is_own_seller is True else "Competition" if r.is_own_seller is False else None,
                "condition": r.condition,
            }
            for r in rows
        ]
        buy = next((i for i in items if i["is_buy_box"]), None)
        return {
            "items": items,
            "shoppers_price": buy["price"] if buy else None,
            "buy_box_seller": buy["seller_name"] if buy else None,
            "buy_box_label": buy["label"] if buy else None,
        }


@router.get("/supply")
def get_supply(
    customer_id: int = Query(),
    product_id: int = Query(),
    user: dict = Depends(get_current_user),
):
    """Distributor sell-out that supplied this customer with this product, or "not linked"."""
    from app.services.listing_capture.supply import sellout_supply

    with SessionLocal() as session:
        try:
            return sellout_supply(
                session,
                customer_id=customer_id,
                product_id=product_id,
                tenant_id=tenant_id_from_user(user),
            )
        except Exception:
            return {"status": "not linked", "rows": [], "data_unavailable": True}
