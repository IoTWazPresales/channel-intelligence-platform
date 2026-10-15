"""Booked FX rate lifecycle — daily fetch, proposed suggestion, book at approval.

``cpor_case.roe_snapshot`` remains the booked/declared case rate (NS-1a).
Proposed columns are a separate history; booking never overwrites them.

N-0083 rules (Warren): a case's rate comes from the stored daily rate for the case's own
date, or from an explicit manual override that carries a reason. It is fixed at the first
approval and never revisited. Rates are fetched daily and can be refreshed.

Fetch source: Frankfurter (ECB daily reference, no API key, ZAR quoted).
Failed fetches never block a case: the case stays unbooked and flagged. A last-known
row is never passed off as the rate for the case's date.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseEvent
from app.models.fx_rate import FxDailyRate
from app.services.cpor.settle_readiness import FX_MODES, fx_declared, fx_mode_valid

logger = logging.getLogger(__name__)

QUOTE_PAIR = "USDZAR"
SOURCE_FRANKFURTER = "frankfurter.ecb"
SOURCE_LAST_KNOWN = "last_known"
SOURCE_OPERATOR = "operator"
SOURCE_FETCH_FAILED = "fetch_failed"

FRANKFURTER_LATEST = "https://api.frankfurter.app/latest?from=USD&to=ZAR"
FRANKFURTER_ON_DATE = "https://api.frankfurter.app/{rate_date}?from=USD&to=ZAR"
FETCH_TIMEOUT_S = 10
USER_AGENT = "cip-fx-rate/1.0"

POST_APPROVAL_STATUSES = frozenset({"approved", "active", "ended"})

BOOKED_STORED = "stored"
BOOKED_OVERRIDE = "manual_override"
BOOKED_EXISTING = "existing"
BOOKED_KEPT = "kept"

# The ECB publishes on business days. A stored row this many days before the case date still
# is "the rate for its date" (weekend plus a bank holiday); older than that is fetched.
STORED_GAP_DAYS = 4
_SAME_RATE_TOLERANCE = 1e-6


class FxOverrideReasonRequired(ValueError):
    """A manual rate that differs from the stored rate must say why."""


class FxRateFixed(ValueError):
    """The case rate was fixed at its first approval."""


@dataclass(frozen=True)
class RateQuote:
    rate: float | None
    rate_date: date | None
    source: str
    is_fallback: bool
    fetch_failed: bool = False
    persisted: bool = True

    @property
    def live(self) -> bool:
        return self.rate is not None and not self.fetch_failed and not self.is_fallback

    def as_json(self) -> dict[str, Any]:
        return {
            "rate": self.rate,
            "rate_date": self.rate_date.isoformat() if self.rate_date else None,
            "source": self.source,
            "is_fallback": self.is_fallback,
            "fetch_failed": self.fetch_failed,
            "persisted": self.persisted,
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
    """Fetch the ECB rate for ``on_date``. Persist when the table is writable.

    Never raises. HTTP failure returns no rate (FLAG, do not substitute last-known).
    Persist failure still returns the fetched rate so case create is not blocked.
    """
    try:
        published, rate = fetch_frankfurter(on_date=on_date)
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as exc:
        logger.warning("fx fetch failed for %s: %s", on_date.isoformat(), exc)
        return RateQuote(
            rate=None,
            rate_date=None,
            source=SOURCE_FETCH_FAILED,
            is_fallback=True,
            fetch_failed=True,
        )

    try:
        with session.begin_nested():
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
    except Exception as exc:
        logger.error("fx persist failed for %s: %s", on_date.isoformat(), exc)
        return RateQuote(
            rate=rate,
            rate_date=published,
            source=SOURCE_FRANKFURTER,
            is_fallback=False,
            fetch_failed=False,
            persisted=False,
        )


def ensure_today_rate(session: Session) -> RateQuote:
    return ensure_rate_for_date(session, _utc_today())


def case_rate_date(case: CporCase, today: date | None = None) -> date:
    """The case's own date: its window start, or today when the window has not started yet."""
    now = today or _utc_today()
    start = getattr(case, "window_start", None)
    if start is None or start > now:
        return now
    return start


def rate_for_case_date(session: Session, on_date: date, *, today: date | None = None) -> RateQuote:
    """The stored daily rate for ``on_date``. Fetches and stores it only when none is stored.

    Stored first: a row for the date, or for a past date the last row no more than
    ``STORED_GAP_DAYS`` earlier (weekend or bank holiday). Otherwise one ECB fetch, which is
    stored under the date the ECB published. A failed fetch gives no rate; nothing older is
    substituted.
    """
    now = today or _utc_today()
    row = load_rate_on_date(session, on_date)
    if row is None and on_date < now:
        earlier = load_rate_on_or_before(session, on_date)
        if earlier is not None and (on_date - earlier.rate_date).days <= STORED_GAP_DAYS:
            row = earlier
    if row is not None and not row.is_fallback and _positive_rate(row.rate) is not None:
        return RateQuote(
            rate=float(row.rate),
            rate_date=row.rate_date,
            source=row.source,
            is_fallback=False,
            fetch_failed=False,
        )
    return ensure_rate_for_date(session, on_date)


def _same_rate(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(float(a) - float(b)) < _SAME_RATE_TOLERANCE


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
    source: str | None = None,
    rate_date: date | None = None,
    reason: str | None = None,
) -> bool:
    """Stamp the booked/declared case rate. Never overwrites proposed columns.

    ``source`` says how the rate was chosen (stored, manual_override, existing);
    ``rate_date`` is the ECB date of a stored rate; ``reason`` is the override reason.
    """
    positive = _positive_rate(rate)
    if positive is None:
        return False
    stamp = now or _now()
    case.roe_snapshot = positive
    case.fx_declared_at = stamp
    case.fx_declared_by = actor
    case.fx_booked_source = source
    case.fx_booked_rate_date = rate_date
    case.fx_override_reason = (reason or "").strip() or None
    if not fx_mode_valid(case):
        case.fx_mode = "booked"
    return True


def _book_stored(case: CporCase, quote: RateQuote, actor: str) -> None:
    if _positive_rate(getattr(case, "fx_proposed_rate", None)) is None:
        set_proposed(case, quote.rate, actor, source=quote.source)  # type: ignore[arg-type]
    book_rate(
        case,
        quote.rate,  # type: ignore[arg-type]
        actor,
        source=BOOKED_STORED,
        rate_date=quote.rate_date,
    )


def _book_override(
    case: CporCase,
    rate: float,
    actor: str,
    stored: RateQuote | None,
    *,
    reason: str,
) -> None:
    """Book an operator's rate. The proposed columns keep the stored rate when there is one."""
    if _positive_rate(getattr(case, "fx_proposed_rate", None)) is None:
        if stored is not None and stored.live:
            set_proposed(case, stored.rate, actor, source=stored.source)  # type: ignore[arg-type]
        else:
            set_proposed(case, rate, actor, source=SOURCE_OPERATOR)
    book_rate(case, rate, actor, source=BOOKED_OVERRIDE, reason=reason)


def apply_create_fx(
    session: Session,
    case: CporCase,
    *,
    actor: str,
    proposed_override: float | None,
    explicit_roe: float | None,
) -> RateQuote:
    """Seed FX at create from the stored rate for the case's own date.

    The draft rate is provisional: it is booked again at approval from the same rule. A rate
    the operator supplies that differs from the stored rate is a manual override and is
    recorded as one. Fetch failure never blocks: the case is created unbooked and flagged.
    """
    override = _positive_rate(proposed_override)
    explicit = _positive_rate(explicit_roe)
    quote = rate_for_case_date(session, case_rate_date(case))
    stored_rate = quote.rate if quote.live else None

    chosen = override if override is not None else explicit
    if chosen is not None:
        if _same_rate(chosen, stored_rate):
            _book_stored(case, quote, actor)
        else:
            _book_override(
                case,
                chosen,
                actor,
                quote,
                reason=(
                    "Rate entered when the case was created; no stored rate was available"
                    if stored_rate is None
                    else "Rate entered when the case was created"
                ),
            )
        return quote

    if stored_rate is not None:
        _book_stored(case, quote, actor)
    else:
        case.fx_proposed_rate = None
        case.fx_proposed_at = _now()
        case.fx_proposed_by = actor
        case.fx_proposed_source = SOURCE_FETCH_FAILED if quote.fetch_failed else SOURCE_LAST_KNOWN
        case.roe_snapshot = None
        case.fx_declared_at = None
        case.fx_declared_by = None
        case.fx_mode = None
        case.fx_booked_source = None
        case.fx_booked_rate_date = None
        case.fx_override_reason = None
    return quote


@dataclass(frozen=True)
class BookOutcome:
    rate: float | None
    source: str | None
    rate_date: date | None = None
    stored_rate: float | None = None
    stored_rate_date: date | None = None
    reason: str | None = None
    notes: list[str] = field(default_factory=list)

    def as_json(self) -> dict[str, Any]:
        return {
            "rate": self.rate,
            "source": self.source,
            "rate_date": self.rate_date.isoformat() if self.rate_date else None,
            "stored_rate": self.stored_rate,
            "stored_rate_date": self.stored_rate_date.isoformat() if self.stored_rate_date else None,
            "reason": self.reason,
            "notes": list(self.notes),
        }


def has_prior_approval(session: Session, case_id: int | None) -> bool:
    if case_id is None:
        return False
    count = session.scalar(
        select(func.count())
        .select_from(CporCaseEvent)
        .where(CporCaseEvent.case_id == case_id, CporCaseEvent.event_type == "transition_approve")
    )
    return bool(count)


def book_on_approve(
    session: Session,
    case: CporCase,
    *,
    actor: str,
    override: float | None,
    reason: str | None = None,
    today: date | None = None,
) -> BookOutcome:
    """Fix the case rate at its first approval. A missing rate does not block approval.

    Order: an operator override that differs from the stored rate (needs a reason); else a
    rate the operator already chose for this case (an override booked at create, or a legacy
    rate), kept and not silently replaced; else the stored rate for the case's own date; else
    a proposed rate; else nothing. A later approval of the same case (reapproval) keeps the
    rate and refuses a new one.
    """
    ov = _positive_rate(override)
    if has_prior_approval(session, getattr(case, "id", None)):
        current = _positive_rate(getattr(case, "roe_snapshot", None))
        if ov is not None and not _same_rate(ov, current):
            raise FxRateFixed("The case rate was fixed at its first approval and is not revisited.")
        return BookOutcome(
            rate=current,
            source=BOOKED_KEPT,
            rate_date=getattr(case, "fx_booked_rate_date", None),
        )

    stored = rate_for_case_date(session, case_rate_date(case, today), today=today)
    stored_rate = stored.rate if stored.live else None
    stored_date = stored.rate_date if stored_rate is not None else None
    notes: list[str] = []
    if stored.live and not stored.persisted:
        notes.append("stored_rate_not_persisted")

    if ov is not None and not _same_rate(ov, stored_rate):
        why = (reason or "").strip()
        if not why:
            raise FxOverrideReasonRequired("A rate that differs from the stored daily rate needs a reason.")
        _book_override(case, ov, actor, stored, reason=why)
        return BookOutcome(
            rate=ov,
            source=BOOKED_OVERRIDE,
            stored_rate=stored_rate,
            stored_rate_date=stored_date,
            reason=why,
            notes=notes,
        )

    existing = _positive_rate(getattr(case, "roe_snapshot", None))
    existing_source = getattr(case, "fx_booked_source", None)
    if ov is None and existing is not None and existing_source in (BOOKED_OVERRIDE, None):
        kept_source = BOOKED_OVERRIDE if existing_source == BOOKED_OVERRIDE else BOOKED_EXISTING
        kept_reason = getattr(case, "fx_override_reason", None)
        book_rate(case, existing, actor, source=kept_source, reason=kept_reason)
        return BookOutcome(
            rate=existing,
            source=kept_source,
            stored_rate=stored_rate,
            stored_rate_date=stored_date,
            reason=kept_reason,
            notes=notes,
        )

    if stored_rate is not None:
        _book_stored(case, stored, actor)
        return BookOutcome(
            rate=stored_rate,
            source=BOOKED_STORED,
            rate_date=stored.rate_date,
            stored_rate=stored_rate,
            stored_rate_date=stored_date,
            notes=notes,
        )

    proposed = _positive_rate(getattr(case, "fx_proposed_rate", None))
    if proposed is not None:
        who = getattr(case, "fx_proposed_by", None) or "the operator"
        why = f"Rate proposed by {who}; no stored rate for the case date"
        book_rate(case, proposed, actor, source=BOOKED_OVERRIDE, reason=why)
        return BookOutcome(rate=proposed, source=BOOKED_OVERRIDE, reason=why, notes=notes)

    return BookOutcome(rate=None, source=None, notes=notes + ["no_rate"])


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
    rate_date: date | None = None,
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
        if source == SOURCE_OPERATOR:
            booked = book_rate(
                case,
                positive,
                actor,
                source=BOOKED_OVERRIDE,
                reason="Rate entered by the operator when backfilling a case with no rate",
            )
        else:
            booked = book_rate(case, positive, actor, source=BOOKED_STORED, rate_date=rate_date)
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
        "fx_booked_source": getattr(case, "fx_booked_source", None),
        "fx_booked_rate_date": (
            case.fx_booked_rate_date.isoformat() if getattr(case, "fx_booked_rate_date", None) else None
        ),
        "fx_override_reason": getattr(case, "fx_override_reason", None),
    }
