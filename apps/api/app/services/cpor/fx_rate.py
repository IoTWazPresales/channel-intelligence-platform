"""Booked FX rate lifecycle — daily fetch, proposed suggestion, book at approval.

``cpor_case.roe_snapshot`` remains the booked/declared case rate (NS-1a).
Proposed columns are a separate history; booking never overwrites them.

Fetch source: Frankfurter (ECB daily reference, no API key, ZAR quoted).
Failed fetches never block a case — last known row is used and flagged.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase
from app.models.fx_rate import FxDailyRate
from app.services.cpor.settle_readiness import FX_MODES, fx_declared, fx_mode_valid

logger = logging.getLogger(__name__)

QUOTE_PAIR = "USDZAR"
SOURCE_FRANKFURTER = "frankfurter.ecb"
SOURCE_LAST_KNOWN = "last_known"
SOURCE_OPERATOR = "operator"

FRANKFURTER_LATEST = "https://api.frankfurter.app/latest?from=USD&to=ZAR"
FRANKFURTER_ON_DATE = "https://api.frankfurter.app/{rate_date}?from=USD&to=ZAR"
FETCH_TIMEOUT_S = 10
USER_AGENT = "cip-fx-rate/1.0"

POST_APPROVAL_STATUSES = frozenset({"approved", "active", "ended"})


@dataclass(frozen=True)
class RateQuote:
    rate: float | None
    rate_date: date | None
    source: str
    is_fallback: bool
    fetch_failed: bool = False

    def as_json(self) -> dict[str, Any]:
        return {
            "rate": self.rate,
            "rate_date": self.rate_date.isoformat() if self.rate_date else None,
            "source": self.source,
            "is_fallback": self.is_fallback,
            "fetch_failed": self.fetch_failed,
            "quote_pair": QUOTE_PAIR,
        }


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def parse_frankfurter_payload(payload: dict[str, Any]) -> tuple[date, float]:
    raw_date = payload.get("date")
    rates = payload.get("rates") or {}
    raw_zar = rates.get("ZAR")
    if not raw_date or raw_zar is None:
        raise ValueError("frankfurter payload missing date or ZAR rate")
    published = date.fromisoformat(str(raw_date))
    rate = float(Decimal(str(raw_zar)))
    if rate <= 0:
        raise ValueError("frankfurter ZAR rate is not positive")
    return published, rate


def _http_get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT_S) as resp:
        body = resp.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("frankfurter response is not an object")
    return parsed


def fetch_frankfurter(*, on_date: date | None = None) -> tuple[date, float]:
    url = (
        FRANKFURTER_ON_DATE.format(rate_date=on_date.isoformat())
        if on_date is not None
        else FRANKFURTER_LATEST
    )
    return parse_frankfurter_payload(_http_get_json(url))


def _positive_rate(value: Any) -> float | None:
    if value is None:
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError, InvalidOperation):
        return None
    if rate <= 0:
        return None
    return rate


def load_rate_on_or_before(session: Session, on_date: date) -> FxDailyRate | None:
    return session.scalars(
        select(FxDailyRate)
        .where(
            FxDailyRate.quote_pair == QUOTE_PAIR,
            FxDailyRate.rate_date <= on_date,
        )
        .order_by(FxDailyRate.rate_date.desc())
        .limit(1)
    ).first()


def load_rate_on_date(session: Session, on_date: date) -> FxDailyRate | None:
    return session.scalars(
        select(FxDailyRate).where(
            FxDailyRate.quote_pair == QUOTE_PAIR,
            FxDailyRate.rate_date == on_date,
        )
    ).first()


def upsert_daily_rate(
    session: Session,
    *,
    rate_date: date,
    rate: float,
    source: str,
    is_fallback: bool,
    fetched_at: datetime | None = None,
) -> FxDailyRate:
    now = fetched_at or _now()
    existing = load_rate_on_date(session, rate_date)
    if existing is not None:
        if is_fallback and not existing.is_fallback:
            return existing
        existing.rate = rate
        existing.source = source
        existing.fetched_at = now
        existing.is_fallback = is_fallback
        session.add(existing)
        return existing
    row = FxDailyRate(
        rate_date=rate_date,
        quote_pair=QUOTE_PAIR,
        rate=rate,
        source=source,
        fetched_at=now,
        is_fallback=is_fallback,
    )
    session.add(row)
    return row


def ensure_rate_for_date(session: Session, on_date: date) -> RateQuote:
    """Fetch and store the ECB rate for ``on_date`` (or last published on/before it).

    Never raises. On fetch failure, returns last known and flags fallback.
    """
    try:
        published, rate = fetch_frankfurter(on_date=on_date)
        row = upsert_daily_rate(
            session,
            rate_date=published,
            rate=rate,
            source=SOURCE_FRANKFURTER,
            is_fallback=False,
        )
        session.flush()
        return RateQuote(
            rate=float(row.rate),
            rate_date=row.rate_date,
            source=row.source,
            is_fallback=False,
            fetch_failed=False,
        )
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        logger.warning("fx fetch failed for %s: %s", on_date.isoformat(), exc)
        known = load_rate_on_or_before(session, on_date)
        if known is None:
            return RateQuote(
                rate=None,
                rate_date=None,
                source=SOURCE_LAST_KNOWN,
                is_fallback=True,
                fetch_failed=True,
            )
        return RateQuote(
            rate=float(known.rate),
            rate_date=known.rate_date,
            source=SOURCE_LAST_KNOWN,
            is_fallback=True,
            fetch_failed=True,
        )


def ensure_today_rate(session: Session) -> RateQuote:
    return ensure_rate_for_date(session, _utc_today())


def set_proposed(
    case: CporCase,
    rate: float,
    actor: str,
    *,
    source: str,
    now: datetime | None = None,
) -> bool:
    """Write proposed rate. Never touches roe_snapshot / fx_declared_*."""
    positive = _positive_rate(rate)
    if positive is None:
        return False
    stamp = now or _now()
    case.fx_proposed_rate = positive
    case.fx_proposed_at = stamp
    case.fx_proposed_by = actor
    case.fx_proposed_source = source
    return True


def book_rate(
    case: CporCase,
    rate: float,
    actor: str,
    *,
    now: datetime | None = None,
) -> bool:
    """Stamp the booked/declared case rate. Never overwrites proposed columns."""
    positive = _positive_rate(rate)
    if positive is None:
        return False
    stamp = now or _now()
    case.roe_snapshot = positive
    case.fx_declared_at = stamp
    case.fx_declared_by = actor
    if not fx_mode_valid(case):
        case.fx_mode = "booked"
    return True


def apply_create_fx(
    session: Session,
    case: CporCase,
    *,
    actor: str,
    proposed_override: float | None,
    explicit_roe: float | None,
) -> RateQuote:
    """Seed proposed rate on create. Does not declare unless explicit_roe is already on the case."""
    if not getattr(case, "fx_mode", None):
        case.fx_mode = "booked"
    elif case.fx_mode not in FX_MODES:
        case.fx_mode = "booked"

    override = _positive_rate(proposed_override)
    explicit = _positive_rate(explicit_roe)
    suggestion = ensure_today_rate(session)

    if override is not None:
        set_proposed(case, override, actor, source=SOURCE_OPERATOR)
    elif suggestion.rate is not None:
        set_proposed(
            case,
            suggestion.rate,
            actor,
            source=SOURCE_LAST_KNOWN if suggestion.is_fallback else SOURCE_FRANKFURTER,
        )

    if explicit is not None:
        # Historical / back-compat create-with-ROE: keep declared snapshot, seed proposed if empty.
        if _positive_rate(getattr(case, "fx_proposed_rate", None)) is None:
            set_proposed(case, explicit, actor, source=SOURCE_OPERATOR)
        if fx_mode_valid(case):
            case.fx_declared_at = _now()
            case.fx_declared_by = actor
    else:
        case.roe_snapshot = None
        case.fx_declared_at = None
        case.fx_declared_by = None

    return suggestion


def book_on_approve(
    case: CporCase,
    *,
    actor: str,
    override: float | None,
) -> float | None:
    """Book at approval. Override wins, else proposed, else existing snapshot. Missing rate does not block."""
    rate = _positive_rate(override)
    source = SOURCE_OPERATOR if rate is not None else None
    if rate is None:
        rate = _positive_rate(getattr(case, "fx_proposed_rate", None))
    if rate is None:
        rate = _positive_rate(getattr(case, "roe_snapshot", None))
    if rate is None:
        return None
    if source == SOURCE_OPERATOR and _positive_rate(getattr(case, "fx_proposed_rate", None)) is None:
        set_proposed(case, rate, actor, source=SOURCE_OPERATOR)
    book_rate(case, rate, actor)
    return rate


def declare_fx_mode(
    case: CporCase,
    mode: str,
    actor: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Set fx_mode only. Never writes roe_snapshot. Never infers a rate.

    Operator-confirmed path only — callers must require confirm=true at the HTTP boundary.
    """
    chosen = (mode or "").strip().lower()
    if chosen not in FX_MODES:
        return {"ok": False, "reason": "invalid_mode"}
    if not fx_declared(case):
        return {"ok": False, "reason": "rate_missing"}
    stamp = now or _now()
    already = fx_mode_valid(case) and str(case.fx_mode) == chosen
    if already:
        return {"ok": True, "skipped": True, "mode": chosen}
    case.fx_mode = chosen
    case.fx_declared_at = stamp
    case.fx_declared_by = actor
    return {"ok": True, "skipped": False, "mode": chosen}


def confirm_backfill_suggestion(
    case: CporCase,
    rate: float,
    actor: str,
    *,
    source: str = SOURCE_OPERATOR,
) -> dict[str, Any]:
    """Operator-confirmed suggestion. Never auto-declares from a fetch job.

    Draft/rejected/proposed: proposed only (books later at approval).
    Approved/active/ended: keep proposed history, then book — approval already happened.
    """
    positive = _positive_rate(rate)
    if positive is None:
        return {"ok": False, "reason": "rate_not_positive"}
    if fx_declared(case):
        return {"ok": False, "reason": "already_declared"}

    proposed_before = _positive_rate(getattr(case, "fx_proposed_rate", None))
    if proposed_before is None:
        set_proposed(case, positive, actor, source=source)
    booked = False
    status = (case.status or "").strip().lower()
    if status in POST_APPROVAL_STATUSES:
        booked = book_rate(case, positive, actor)
    return {
        "ok": True,
        "proposed": True,
        "booked": booked,
        "rate": positive,
        "status": status,
    }


def fx_fields_json(case: CporCase) -> dict[str, Any]:
    proposed = _positive_rate(getattr(case, "fx_proposed_rate", None))
    proposed_at = getattr(case, "fx_proposed_at", None)
    return {
        "fx_proposed_rate": proposed,
        "fx_proposed_at": proposed_at.isoformat() if proposed_at else None,
        "fx_proposed_by": getattr(case, "fx_proposed_by", None),
        "fx_proposed_source": getattr(case, "fx_proposed_source", None),
        "fx_booked": fx_declared(case),
    }
