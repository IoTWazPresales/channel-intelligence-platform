"""Discovery V2 API: preview, apply and the site-candidate review queue.

Mounted at ``/listing-capture/discovery``. Everything is tenant-scoped through the caller's tenant.
Writes (start a preview, apply, decide a candidate) need the steward role. Starting a preview writes
nothing to the database: the work runs on the worker in a read-only transaction.
"""

from __future__ import annotations

import importlib.util
import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.security import Role, get_current_user, require_roles
from app.core.tenant_scope import tenant_id_from_user
from app.db.session_sync import SessionLocal
from app.models.customer_web_site import WEB_SITE_CONFIRMED, WEB_SITE_PROPOSED, WEB_SITE_REJECTED
from app.models.dimensions import DimCustomer
from app.services.listing_capture.observation import listing_live_fetch_enabled
from app.services.listing_capture.web_discovery import apply as web_apply
from app.services.listing_capture.web_discovery import preview as web_preview
from app.services.listing_capture.web_discovery.settings import (
    SCOPE_CUSTOMER,
    SCOPE_DOMAIN,
    load_discovery_settings,
)

logger = logging.getLogger(__name__)
router = APIRouter()

PROVIDERS: list[dict[str, Any]] = [
    {"id": "ddg_html", "label": "DuckDuckGo (HTML)", "needs_url": False},
    {"id": "ddg_lite", "label": "DuckDuckGo (Lite)", "needs_url": False},
    {"id": "searxng", "label": "SearXNG (your own server)", "needs_url": True},
    {"id": "ddgs_auto", "label": "Free web search (several engines, no key)", "needs_url": False},
]
TASK_NAME = "listing_capture.discovery_preview"


def get_plan_store() -> web_preview.PlanStore:
    """The plan store (Redis). Tests replace this. There is no in-process fallback."""
    return web_preview.default_plan_store()


def dispatch_preview(tenant_id: str, preview_id: str, request: dict[str, Any]) -> None:
    from app.worker.celery_app import celery_app

    celery_app.send_task(TASK_NAME, args=[tenant_id, preview_id, request], ignore_result=True)


def _error(status_code: int, code: str, message: str = "", **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"code": code, "message": message, **extra})


class PreviewBody(BaseModel):
    scope: str
    customer_id: int | None = None
    domain: str | None = None


class CandidateDecisionBody(BaseModel):
    action: str


@router.get("/capabilities")
def get_capabilities(user: dict = Depends(get_current_user)):
    tenant_id = tenant_id_from_user(user)
    with SessionLocal() as session:
        try:
            missing = load_discovery_settings(session, tenant_id).missing
        except Exception:  # noqa: BLE001 - an unreadable settings table reads as "not set"
            logger.exception("discovery capabilities: settings unreadable")
            session.rollback()
            missing = ["tenant.country", "tenant.domain_endings"]
    return {
        "live_fetch": listing_live_fetch_enabled(),
        "browser_available": importlib.util.find_spec("playwright") is not None,
        "providers": PROVIDERS,
        "settings": {"missing": missing},
    }


@router.post("/previews")
def post_preview(body: PreviewBody, user: dict = Depends(require_roles(Role.STEWARD))):
    tenant_id = tenant_id_from_user(user)
    try:
        request = web_preview.normalize_request(body.model_dump())
    except web_preview.RequestError as exc:
        return _error(422, exc.code, str(exc))
    with SessionLocal() as session:
        if request["scope"] in (SCOPE_CUSTOMER, SCOPE_DOMAIN):
            customer = session.get(DimCustomer, int(request["customer_id"]))
            if not isinstance(customer, DimCustomer) or str(customer.tenant_id) != tenant_id:
                return _error(422, "customer_not_found", "That customer is not in this tenant.")
        missing = load_discovery_settings(session, tenant_id).missing_for(request["scope"])
    if missing:
        return _error(
            409,
            "settings_missing",
            "Set the tenant country and domain endings in Settings → Discovery.",
            missing=missing,
        )
    if not listing_live_fetch_enabled():
        return _error(409, "live_fetch_off", "Live page fetching is switched off on this server.")

    preview_id = web_preview.new_preview_id()
    try:
        store = get_plan_store()
        running = store.acquire(tenant_id, preview_id)
        if running is not None:
            return _error(409, "preview_running", "A preview is already running.", preview_id=running)
        try:
            store.save(tenant_id, preview_id, web_preview.new_plan(tenant_id, preview_id, request))
            dispatch_preview(tenant_id, preview_id, request)
        except Exception:
            store.release(tenant_id, preview_id)
            raise
    except web_preview.StoreUnavailable:
        return _error(503, "store_unavailable", "The preview store is not reachable. Try again shortly.")
    except Exception:  # noqa: BLE001
        logger.exception("discovery preview could not be queued")
        return _error(503, "dispatch_failed", "The preview could not be queued. Try again shortly.")
    return JSONResponse(status_code=202, content={"preview_id": preview_id, "status": web_preview.STATUS_QUEUED})


@router.get("/previews/{preview_id}")
def get_preview(preview_id: str, user: dict = Depends(get_current_user)):
    tenant_id = tenant_id_from_user(user)
    try:
        plan = get_plan_store().load(tenant_id, preview_id)
    except web_preview.StoreUnavailable:
        return _error(503, "store_unavailable", "The preview store is not reachable. Try again shortly.")
    if plan is None:
        return {
            "preview_id": preview_id,
            "status": web_preview.STATUS_EXPIRED,
            "progress": {"done": 0, "total": 0},
            "applied": None,
            "result": None,
        }
    return {
        "preview_id": preview_id,
        "status": plan.get("status"),
        "progress": plan.get("progress") or {"done": 0, "total": 0},
        "applied": plan.get("applied"),
        "result": plan.get("result"),
        "error": plan.get("error"),
    }


@router.post("/previews/{preview_id}/apply")
def post_apply(preview_id: str, user: dict = Depends(require_roles(Role.STEWARD))):
    tenant_id = tenant_id_from_user(user)
    try:
        store = get_plan_store()
        with SessionLocal() as session:
            try:
                return web_apply.apply_plan(session, store, tenant_id=tenant_id, preview_id=preview_id, user=user)
            except Exception:
                session.rollback()
                raise
    except web_apply.ApplyError as exc:
        return _error(exc.status_code, exc.code, str(exc))
    except web_preview.StoreUnavailable:
        return _error(503, "store_unavailable", "The preview store is not reachable. Try again shortly.")


@router.get("/site-candidates")
def get_site_candidates(
    status: str = Query(default=WEB_SITE_PROPOSED),
    user: dict = Depends(get_current_user),
):
    if status not in (WEB_SITE_PROPOSED, WEB_SITE_CONFIRMED, WEB_SITE_REJECTED):
        return _error(422, "status_invalid", "status must be proposed, confirmed or rejected")
    with SessionLocal() as session:
        return {"items": web_apply.list_site_candidates(session, tenant_id_from_user(user), status)}


@router.post("/site-candidates/{candidate_id}")
def post_site_candidate(
    candidate_id: int,
    body: CandidateDecisionBody,
    user: dict = Depends(require_roles(Role.STEWARD)),
):
    with SessionLocal() as session:
        try:
            result = web_apply.decide_site_candidate(
                session,
                tenant_id=tenant_id_from_user(user),
                candidate_id=candidate_id,
                action=body.action,
                user=user,
            )
            session.commit()
        except web_apply.ApplyError as exc:
            session.rollback()
            return _error(exc.status_code, exc.code, str(exc))
        except Exception:
            session.rollback()
            raise
        return result
