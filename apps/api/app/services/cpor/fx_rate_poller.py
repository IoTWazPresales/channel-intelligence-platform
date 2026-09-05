"""API-lifespan daily FX catch-up — Windows solo has no Celery beat by default."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_S = 6 * 3600
_poller_lock = threading.Lock()
_poller_started = False


def fx_rate_poll_enabled() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    raw = (os.environ.get("CIP_FX_RATE_CATCHUP") or "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def fx_rate_poll_interval_seconds() -> int:
    try:
        raw = int(os.environ.get("CIP_FX_RATE_POLL_SECONDS") or _DEFAULT_INTERVAL_S)
    except ValueError:
        raw = _DEFAULT_INTERVAL_S
    return max(60, min(raw, 24 * 3600))


def fetch_daily_fx_rate_safe(*, reason: str) -> dict:
    """Never raises into the lifespan loop."""
    try:
        from app.db.session_sync import SessionLocal
        from app.services.cpor.fx_rate import ensure_today_rate

        with SessionLocal() as session:
            quote = ensure_today_rate(session)
            session.commit()
            payload = quote.as_json()
            payload["reason"] = reason
            return payload
    except Exception:
        logger.exception("fx daily rate poll failed (%s)", reason)
        return {"ok": False, "reason": reason, "fetch_failed": True}


def spawn_fx_rate_poller() -> None:
    global _poller_started
    if not fx_rate_poll_enabled():
        logger.warning("fx rate poller skipped (pytest or CIP_FX_RATE_CATCHUP=0)")
        return
    with _poller_lock:
        if _poller_started:
            return
        _poller_started = True
    interval = fx_rate_poll_interval_seconds()

    def _loop() -> None:
        fetch_daily_fx_rate_safe(reason="startup")
        while True:
            time.sleep(interval)
            fetch_daily_fx_rate_safe(reason="interval")

    threading.Thread(target=_loop, name="cip-fx-rate-poll", daemon=True).start()
    logger.warning("fx rate poller started interval=%ss", interval)
