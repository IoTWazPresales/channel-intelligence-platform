"""When the listing-site autoconfigure task is asked to run outside its beat slot.

Two triggers, both thin and both honouring the gates that already exist:

* **Worker start** (``run_startup_autoconfigure``). When the worker comes up it asks for one
  scheduled-mode run, so discovery does not wait for the next 05:20 UTC beat slot. Same gates as
  the beat: ``dev_beat_disabled()`` and the tenant setting ``discovery.schedule_enabled`` (read
  here only to say why nothing was queued; the task re-checks it). A record in the run-state
  store, also written by every scheduled run, keeps a restart inside the daily cadence from
  running discovery again.
* **After a site is confirmed** (``request_autoconfigure_after_confirm``). A confirmed
  ``customer_web_site`` is only a site key until autoconfigure has searched it and set its reader,
  so a confirm asks for an on-demand run for that tenant. Confirmations that arrive together share
  one run (the queued run starts ``CONFIRM_COALESCE_SECONDS`` later and covers all of them).

Nothing here names a site, a customer or a domain, and nothing here confirms or links anything.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.listing_capture.site_pause import (
    SitePauseStore,
    load_run_state,
    save_run_state,
)

logger = logging.getLogger(__name__)

AUTOCONFIGURE_TASK_NAME = "listing_capture.autoconfigure_sites"
SCHEDULED_RUN_KEY = "autoconfigure:last_scheduled_run"
CONFIRM_REQUEST_KEY_PREFIX = "autoconfigure:after_confirm:"
# The beat runs once a day; a worker restart inside that cadence does not run discovery again.
SCHEDULED_RUN_DEBOUNCE = timedelta(hours=24)
# Confirmations made within this window of the first one are covered by the one queued run.
CONFIRM_COALESCE_SECONDS = 120

Enqueue = Callable[..., Any]


def _now() -> datetime:
    return datetime.now(UTC)


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _send_task(*, kwargs: dict[str, Any], countdown: int | None = None) -> None:
    from app.worker.celery_app import celery_app

    options: dict[str, Any] = {"ignore_result": True}
    if countdown is not None:
        options["countdown"] = int(countdown)
    celery_app.send_task(AUTOCONFIGURE_TASK_NAME, kwargs=kwargs, **options)


def _enabled_tenants() -> list[str]:
    from app.db.session_sync import SessionLocal
    from app.services.tenant_settings import KEY_DISCOVERY_SCHEDULE, tenants_with_true

    with SessionLocal() as session:
        return tenants_with_true(session, KEY_DISCOVERY_SCHEDULE)


def note_scheduled_run(*, store: SitePauseStore | None = None, now: datetime | None = None) -> None:
    """Record that a scheduled run is starting (beat or worker start). Never raises."""
    save_run_state(SCHEDULED_RUN_KEY, {"at": (now or _now()).isoformat()}, store=store)


def run_startup_autoconfigure(
    *,
    enqueue: Enqueue | None = None,
    store: SitePauseStore | None = None,
    now: datetime | None = None,
    enabled_tenants: Callable[[], list[str]] | None = None,
    beat_disabled: bool | None = None,
) -> dict[str, Any]:
    """Ask for one scheduled-mode autoconfigure run now that the worker is up. Never raises."""
    try:
        return _startup(
            enqueue=enqueue or _send_task,
            store=store,
            now=now or _now(),
            enabled_tenants=enabled_tenants or _enabled_tenants,
            beat_disabled=beat_disabled,
        )
    except Exception:  # noqa: BLE001 - a worker must start even if this hook cannot
        logger.exception("listing capture startup discovery: hook failed; the daily beat still applies")
        return {"skipped": True, "reason": "hook_failed"}


def _startup(
    *,
    enqueue: Enqueue,
    store: SitePauseStore | None,
    now: datetime,
    enabled_tenants: Callable[[], list[str]],
    beat_disabled: bool | None,
) -> dict[str, Any]:
    from app.worker.celery_queues import dev_beat_disabled

    if (dev_beat_disabled() if beat_disabled is None else beat_disabled):
        logger.info("listing capture startup discovery: skipped (dev_beat_disabled)")
        return {"skipped": True, "reason": "dev_beat_disabled"}
    tenants = enabled_tenants()
    if not tenants:
        logger.info("listing capture startup discovery: skipped (discovery_schedule_off)")
        return {"skipped": True, "reason": "discovery_schedule_off"}
    last = _parse((load_run_state(SCHEDULED_RUN_KEY, store=store) or {}).get("at"))
    if last is not None and now - last < SCHEDULED_RUN_DEBOUNCE:
        logger.info("listing capture startup discovery: skipped (debounced; last scheduled run %s)", last.isoformat())
        return {"skipped": True, "reason": "debounced", "last_run_at": last.isoformat()}
    enqueue(kwargs={})
    note_scheduled_run(store=store, now=now)
    logger.info("listing capture startup discovery: queued one scheduled run for %s tenant(s)", len(tenants))
    return {"skipped": False, "queued": True, "tenants": len(tenants)}


def request_autoconfigure_after_confirm(
    tenant_id: str,
    *,
    enqueue: Enqueue | None = None,
    store: SitePauseStore | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Queue an on-demand autoconfigure run for ``tenant_id`` after a site was confirmed. Never raises."""
    moment = now or _now()
    key = f"{CONFIRM_REQUEST_KEY_PREFIX}{tenant_id}"
    try:
        due = _parse((load_run_state(key, store=store) or {}).get("run_at"))
        if due is not None and due > moment:
            return {"queued": False, "reason": "coalesced", "run_at": due.isoformat()}
        (enqueue or _send_task)(
            kwargs={"tenant_id": tenant_id, "on_demand": True}, countdown=CONFIRM_COALESCE_SECONDS
        )
        run_at = moment + timedelta(seconds=CONFIRM_COALESCE_SECONDS)
        save_run_state(key, {"run_at": run_at.isoformat()}, store=store)
        return {"queued": True, "run_at": run_at.isoformat()}
    except Exception:  # noqa: BLE001 - the confirm is already saved; the daily run still configures it
        logger.exception("listing capture: could not queue autoconfigure after a site confirm")
        return {"queued": False, "reason": "enqueue_failed"}
