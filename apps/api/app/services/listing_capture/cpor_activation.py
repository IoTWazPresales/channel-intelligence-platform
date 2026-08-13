"""Listing price vs CPOR case SRP — activation signal (BACKLOG-130).

Column mapping (locked for this unit)
------------------------------------
- ``listing_price`` ← ``listing_observation.extracted_price`` (storefront, typically ZAR).
- ``case_price`` ← covering **line** SRP (not a collapsed case-header window).
- Period ← observation date within the **line** window (staging Start From / End on
  for historical import; case window for native cases).
- Identity ← ``customer_listing.customer_id`` + ``customer_listing.product_id``
  must match ``cpor_case.customer_id`` + product.

Rule (Warren 2026-08-10): listing higher than the applicable SRP → ``not_activated``.
No covering bar → ``no_case_detected``. Not gated on multi-week history.

Rule (Warren 2026-08-13): **Sell-Through PP** (promo / customer retail) is the bar
when a promo **line** covers the date. **Sell out PP** is Disti sell-in — use it
**only when no covering promo line** exists for that SKU/day. Do not apply an
FNB-Day (or other dated) SRP outside its line window; do not let sell-out win
while a promo line covers.

Results are persisted on the observation row in ``parse_flags.cpor_activation``
(and related keys) — no separate migration.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.listing_capture import CustomerListing

# ZAR tolerance for float/cent noise on scraped vs case SRP.
_PRICE_TOLERANCE = 1.0

_EXCLUDED_CASE_STATUSES = frozenset({"cancelled", "rejected", "superseded"})
_EXCLUDED_LINE_LIFECYCLES = frozenset({"cancelled", "rejected", "superseded"})

_KIND_PROMO = "promo"
_KIND_SELL_OUT = "sell_out"


def _band_kind(promotion_type: str | None) -> str:
    """Sell out PP = Disti sell-in. Everything else is a customer-facing promo bar."""
    s = (promotion_type or "").strip().lower().replace("_", " ").replace("-", " ")
    s = " ".join(s.split())
    if "sell out" in s or s.startswith("sellout"):
        return _KIND_SELL_OUT
    return _KIND_PROMO


def _covers(start: date | None, end: date | None, as_of: date) -> bool:
    return bool(start and end and start <= as_of <= end)


def evaluate_cpor_activation(
    session: Session,
    listing: CustomerListing,
    *,
    listing_price: float | None,
    as_of: date | None = None,
) -> dict[str, Any]:
    """Return explainable activation dict for persistence on observation.parse_flags."""
    as_of = as_of or date.today()
    out: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "listing_price": float(listing_price) if listing_price is not None else None,
        "case_price_field": "cpor_case_line.srp",
    }

    if getattr(listing, "product_id", None) is None:
        out["status"] = "no_product_link"
        out["message"] = "Listing has no product_id — cannot match a CPOR case line."
        return out

    if listing_price is None:
        out["status"] = "no_price"
        out["message"] = "No extracted listing price to compare."
        return out

    rows = list(
        session.execute(
            select(CporCase, CporCaseLine)
            .join(CporCaseLine, CporCaseLine.case_id == CporCase.id)
            .where(
                CporCase.customer_id == int(listing.customer_id),
                CporCaseLine.product_id == int(listing.product_id),
                CporCase.window_start <= as_of,
                CporCase.window_end >= as_of,
                CporCase.superseded_by_case_id.is_(None),
            )
            .order_by(CporCase.id.desc())
        ).all()
    )
    cases = [(c, ln) for c, ln in rows if (c.status or "").strip().lower() not in _EXCLUDED_CASE_STATUSES]

    bars = _resolve_covering_bars(session, cases, product_id=int(listing.product_id), as_of=as_of)
    promo_bars = [b for b in bars if b["kind"] == _KIND_PROMO]
    sell_out_bars = [b for b in bars if b["kind"] == _KIND_SELL_OUT]
    chosen = promo_bars or sell_out_bars

    if not chosen:
        out["status"] = "no_case_detected"
        out["message"] = (
            f"No CPOR case detected for customer {listing.customer_id} / "
            f"product {listing.product_id} covering {as_of.isoformat()}."
        )
        return out

    bar = min(chosen, key=lambda b: (float(b["srp"]), -int(b["case"].id)))
    case = bar["case"]
    line = bar["line"]
    case_price = float(bar["srp"])
    kind = bar["kind"]
    out.update(
        {
            "case_id": int(case.id),
            "case_code": case.case_code,
            "case_status": case.status,
            "case_window_start": case.window_start.isoformat(),
            "case_window_end": case.window_end.isoformat(),
            "case_line_id": int(line.id) if line is not None else None,
            "case_price": case_price,
            "price_basis": kind,
            "promotion_type": getattr(case, "promotion_type", None),
            "line_window_start": bar["line_window_start"].isoformat() if bar["line_window_start"] else None,
            "line_window_end": bar["line_window_end"].isoformat() if bar["line_window_end"] else None,
            "bar_source": bar["source"],
        }
    )

    if float(listing_price) > case_price + _PRICE_TOLERANCE:
        out["status"] = "not_activated"
        if kind == _KIND_SELL_OUT:
            out["message"] = (
                f"Listing price {listing_price} is higher than sell-out SRP {case_price} "
                f"(case {case.case_code}) — no covering promo; Disti sell-in bar missed."
            )
        else:
            out["message"] = (
                f"Listing price {listing_price} is higher than case SRP {case_price} "
                f"(case {case.case_code}) — promo likely not activated by customer."
            )
    else:
        out["status"] = "price_consistent"
        if kind == _KIND_SELL_OUT:
            out["message"] = (
                f"Listing price {listing_price} is at or below sell-out SRP {case_price} "
                f"(case {case.case_code}); no covering promo line."
            )
        else:
            out["message"] = (
                f"Listing price {listing_price} is at or below case SRP {case_price} "
                f"(case {case.case_code})."
            )
    return out


def _resolve_covering_bars(
    session: Session,
    cases: list[tuple[CporCase, CporCaseLine]],
    *,
    product_id: int,
    as_of: date,
) -> list[dict[str, Any]]:
    """One bar per covering SRP. Historical dated bands come from staging, not collapsed apply."""
    if not cases:
        return []

    hist_codes = {
        c.case_code
        for c, _ in cases
        if (getattr(c, "origin", None) or "native") == "historical_import"
    }
    staging_cover: dict[str, list[Any]] = {}
    staging_present: set[str] = set()
    if hist_codes:
        staging_cover, staging_present = _staging_lines_by_case(
            session, case_codes=hist_codes, product_id=product_id, as_of=as_of
        )

    bars: list[dict[str, Any]] = []
    seen_case_ids: set[int] = set()
    for case, line in cases:
        if int(case.id) in seen_case_ids:
            continue
        seen_case_ids.add(int(case.id))
        origin = getattr(case, "origin", None) or "native"
        stg_rows = staging_cover.get(case.case_code or "") if origin == "historical_import" else None
        if stg_rows:
            for stg in stg_rows:
                srp = stg.srp
                if srp is None:
                    continue
                kind = _band_kind(stg.promotion_type or case.promotion_type)
                bars.append(
                    {
                        "case": case,
                        "line": line,
                        "srp": float(srp),
                        "kind": kind,
                        "line_window_start": stg.window_start,
                        "line_window_end": stg.window_end,
                        "source": "historical_staging_line",
                    }
                )
            continue
        if origin == "historical_import" and (case.case_code or "") in staging_present:
            # Dated bands exist but none cover as_of — do not use collapsed applied SRP.
            continue
        if not _covers(case.window_start, case.window_end, as_of):
            continue
        bars.append(
            {
                "case": case,
                "line": line,
                "srp": float(line.srp),
                "kind": _band_kind(getattr(case, "promotion_type", None)),
                "line_window_start": case.window_start,
                "line_window_end": case.window_end,
                "source": "applied_line",
            }
        )
    return bars


def _staging_lines_by_case(
    session: Session,
    *,
    case_codes: set[str],
    product_id: int,
    as_of: date,
) -> tuple[dict[str, list[Any]], set[str]]:
    """Latest-job staging per case_code. Covering windows vs any-rows-present."""
    from app.models.cpor_historical import ImportCporHistoricalStagingLine

    rows = list(
        session.scalars(
            select(ImportCporHistoricalStagingLine).where(
                ImportCporHistoricalStagingLine.case_code.in_(sorted(case_codes)),
                ImportCporHistoricalStagingLine.resolved_product_id == product_id,
                ImportCporHistoricalStagingLine.srp.is_not(None),
            )
        ).all()
    )
    latest_job: dict[str, int] = {}
    for row in rows:
        code = (row.case_code or "").strip()
        job = int(row.import_job_id)
        if code not in latest_job or job > latest_job[code]:
            latest_job[code] = job

    covering: dict[str, list[Any]] = {}
    present: set[str] = set()
    for row in rows:
        code = (row.case_code or "").strip()
        if int(row.import_job_id) != latest_job.get(code):
            continue
        life = (row.lifecycle_status or "").strip().lower()
        if life in _EXCLUDED_LINE_LIFECYCLES:
            continue
        present.add(code)
        if _covers(row.window_start, row.window_end, as_of):
            covering.setdefault(code, []).append(row)
    return covering, present


def as_of_from_fetched_at(fetched_at: datetime | None) -> date:
    if fetched_at is None:
        return date.today()
    if fetched_at.tzinfo is not None:
        return fetched_at.date()
    return fetched_at.date()
