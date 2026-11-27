"""When the listing-site autoconfigure task is asked to run outside its beat slot.

Two triggers, both thin and both honouring the gates that already exist:

* **Worker start** (``run_startup_autoconfigure``). When the worker comes up it asks for one
  scheduled-mode run, so discovery does not wait for the next 05:20 UTC beat slot. Same gates as
  the beat: ``dev_beat_disabled()`` and the tenant setting ``discovery.schedule_enabled`` (read
  here only to say why nothing was queued; the task re-checks it). A record in the run-state
  store, also written by every scheduled run, keeps a restart inside that tenant's saved
  debounce from running discovery again. A tenant with the schedule on but either timing unset
  is skipped. Nothing is filled in.
* **After a site is confirmed** (``request_autoconfigure_after_confirm``). A confirmed
  ``customer_web_site`` is only a site key until autoconfigure has searched it and set its reader,
  so a confirm asks for an on-demand run for that tenant. Confirmations that arrive together share
  one run. The wait is ``discovery.confirm_coalesce_seconds``. When it is unset, nothing is queued.

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


def scheduled_run_key(tenant_id: str) -> str:
    return f"{SCHEDULED_RUN_KEY}:{tenant_id}"

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


def note_scheduled_run(
    *, tenant_id: str, store: SitePauseStore | None = None, now: datetime | None = None
) -> None:
    """Record that a scheduled run is starting for one tenant (beat or worker start). Never raises."""
    save_run_state(scheduled_run_key(tenant_id), {"at": (now or _now()).isoformat()}, store=store)


def _timing(session: Any, tenant_id: str) -> tuple[timedelta, int] | None:
    """The tenant's debounce and confirm wait, or None when either is unset."""
    from app.services.tenant_settings import (
        KEY_DISCOVERY_CONFIRM_COALESCE_SECONDS,
        KEY_DISCOVERY_RUN_DEBOUNCE_HOURS,
        get_setting,
    )

    hours = get_setting(session, tenant_id, KEY_DISCOVERY_RUN_DEBOUNCE_HOURS)
    seconds = get_setting(session, tenant_id, KEY_DISCOVERY_CONFIRM_COALESCE_SECONDS)
    if isinstance(hours, bool) or not isinstance(hours, (int, float)) or hours <= 0:
        return None
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or int(seconds) != float(seconds):
        return None
    if int(seconds) <= 0:
        return None
    return timedelta(hours=float(hours)), int(seconds)


def due_scheduled_tenants(
    session: Any, *, store: SitePauseStore | None = None, now: datetime | None = None
) -> tuple[list[str], list[dict[str, Any]]]:
    """Tenants whose schedule is on, both timings are saved, and the debounce has elapsed.

    A tenant with the schedule on but either timing missing is skipped. Nothing is filled in.
    """
    from app.services.tenant_settings import KEY_DISCOVERY_SCHEDULE, tenants_with_true

    moment = now or _now()
    due: list[str] = []
    skipped: list[dict[str, Any]] = []
    for tenant_id in tenants_with_true(session, KEY_DISCOVERY_SCHEDULE):
        timing = _timing(session, tenant_id)
        if timing is None:
            skipped.append({"tenant_id": tenant_id, "reason": "discovery_timing_not_configured"})
            continue
        debounce, _seconds = timing
        last = _parse((load_run_state(scheduled_run_key(tenant_id), store=store) or {}).get("at"))
        if last is not None and moment - last < debounce:
            skipped.append(
                {"tenant_id": tenant_id, "reason": "debounced", "last_run_at": last.isoformat()}
            )
            continue
        due.append(tenant_id)
    return due, skipped


def coalesce_seconds_for(tenant_id: str) -> int | None:
    """The tenant's confirm wait, or None when it is not saved."""
    from app.db.session_sync import SessionLocal

    try:
        with SessionLocal() as session:
            timing = _timing(session, tenant_id)
    except Exception:  # noqa: BLE001 - a missing setting reads as not configured
        logger.exception("listing capture: could not read the confirm wait")
        return None
    if timing is None:
        return None
    return timing[1]


def run_startup_autoconfigure(
    *,
    enqueue: Enqueue | None = None,
    store: SitePauseStore | None = None,
    now: datetime | None = None,
    beat_disabled: bool | None = None,
) -> dict[str, Any]:
    """Ask for one scheduled-mode autoconfigure run now that the worker is up. Never raises."""
    try:
        return _startup(
            enqueue=enqueue or _send_task,
            store=store,
            now=now or _now(),
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
    beat_disabled: bool | None,
) -> dict[str, Any]:
    from app.worker.celery_queues import dev_beat_disabled

    if (dev_beat_disabled() if beat_disabled is None else beat_disabled):
        logger.info("listing capture startup discovery: skipped (dev_beat_disabled)")
        return {"skipped": True, "reason": "dev_beat_disabled"}
    from app.db.session_sync import SessionLocal

    try:
        with SessionLocal() as session:
            due, skipped = due_scheduled_tenants(session, store=store, now=now)
    except Exception:  # noqa: BLE001 - the caller already swallows hook failures
        raise
    if not due and not skipped:
        logger.info("listing capture startup discovery: skipped (discovery_schedule_off)")
        return {"skipped": True, "reason": "discovery_schedule_off"}
    if not due:
        logger.info("listing capture startup discovery: skipped (%s)", skipped)
        return {"skipped": True, "reason": "no_tenant_due", "tenants": skipped}
    for tenant_id in due:
        note_scheduled_run(tenant_id=tenant_id, store=store, now=now)
    enqueue(kwargs={"tenant_ids": due})
    logger.info("listing capture startup discovery: queued one scheduled run for %s tenant(s)", len(due))
    return {"skipped": False, "queued": True, "tenants": len(due)}


def request_autoconfigure_after_confirm(
    tenant_id: str,
    *,
    enqueue: Enqueue | None = None,
    store: SitePauseStore | None = None,
    now: datetime | None = None,
    coalesce_seconds: int | None = None,
) -> dict[str, Any]:
    """Queue an on-demand autoconfigure run for ``tenant_id`` after a site was confirmed. Never raises."""
    moment = now or _now()
    key = f"{CONFIRM_REQUEST_KEY_PREFIX}{tenant_id}"
    try:
        seconds = coalesce_seconds if coalesce_seconds is not None else coalesce_seconds_for(tenant_id)
        if seconds is None:
            return {"queued": False, "reason": "confirm_coalesce_not_configured"}
        due = _parse((load_run_state(key, store=store) or {}).get("run_at"))
        if due is not None and due > moment:
            return {"queued": False, "reason": "coalesced", "run_at": due.isoformat()}
        (enqueue or _send_task)(
            kwargs={"tenant_id": tenant_id, "on_demand": True}, countdown=int(seconds)
        )
        run_at = moment + timedelta(seconds=int(seconds))
        save_run_state(key, {"run_at": run_at.isoformat()}, store=store)
        return {"queued": True, "run_at": run_at.isoformat()}
    except Exception:  # noqa: BLE001 - the confirm is already saved; the daily run still configures it
        logger.exception("listing capture: could not queue autoconfigure after a site confirm")
        return {"queued": False, "reason": "enqueue_failed"}
