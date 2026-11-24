"""Scheduled Discovery V2: reporting-customer preview then auto-apply (exact evidence only).

Runs inside the existing ``listing_capture.autoconfigure_sites`` beat task when the tenant has
``discovery.schedule_enabled`` on. On-demand steward runs do not use this path.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.services.listing_capture.observation import (
    POLL_RUN_TIME_LIMIT_SECONDS,
    listing_live_fetch_enabled,
)
from app.services.listing_capture.site_fetch import FetchPolicy
from app.services.listing_capture.web_discovery import apply as web_apply
from app.services.listing_capture.web_discovery import preview as web_preview
from app.services.listing_capture.web_discovery.cache import HttpCache, RobotsCache, SearchCache
from app.services.listing_capture.web_discovery.pages import make_page_finder
from app.services.listing_capture.web_discovery.polite import PoliteGetter, dns_resolve
from app.services.listing_capture.web_discovery.settings import SCOPE_REPORTING, load_discovery_settings

logger = logging.getLogger(__name__)


def run_scheduled_reporting_discovery(
    session: Session,
    *,
    tenant_id: str,
    plan_store: web_preview.PlanStore | None = None,
    getter: Any | None = None,
) -> dict[str, Any]:
    """Preview all reporting customers for one tenant, then apply (auto + steward queue outcomes)."""
    if not listing_live_fetch_enabled():
        return {"skipped": True, "reason": "live_fetch_off"}

    settings = load_discovery_settings(session, tenant_id)
    missing = settings.missing_for(SCOPE_REPORTING)
    if missing:
        return {"skipped": True, "reason": "settings_missing", "missing": missing}

    try:
        store = plan_store or web_preview.default_plan_store()
    except web_preview.StoreUnavailable:
        logger.warning("scheduled web discovery: plan store unavailable for %s", tenant_id)
        return {"skipped": True, "reason": "store_unavailable"}

    preview_id = web_preview.new_preview_id()
    request = {"scope": SCOPE_REPORTING}
    polite = getter or PoliteGetter(
        FetchPolicy(time_limit_seconds=POLL_RUN_TIME_LIMIT_SECONDS),
        HttpCache(),
        RobotsCache(),
        resolve=dns_resolve,
    )
    search_cache = SearchCache()
    try:
        web_preview.run_preview(
            session,
            tenant_id=tenant_id,
            preview_id=preview_id,
            request=request,
            getter=polite,
            resolve=dns_resolve,
            plan_store=store,
            search_factory=lambda loaded: web_preview.default_search_fn(loaded, polite, search_cache),
            find_pages=make_page_finder(),
        )
    finally:
        session.rollback()

    plan = store.load(tenant_id, preview_id) or {}
    if plan.get("status") != web_preview.STATUS_DONE:
        return {
            "skipped": False,
            "preview_id": preview_id,
            "status": plan.get("status"),
            "error": plan.get("error"),
        }

    try:
        applied = web_apply.apply_plan(
            session, store, tenant_id=tenant_id, preview_id=preview_id, user=None
        )
    except web_apply.ApplyError as exc:
        logger.info(
            "scheduled web discovery: apply refused for %s preview %s: %s",
            tenant_id,
            preview_id,
            exc.code,
        )
        return {"skipped": False, "preview_id": preview_id, "apply_error": exc.code}

    return {"skipped": False, "preview_id": preview_id, "applied": applied}