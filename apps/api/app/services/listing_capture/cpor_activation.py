"""Listing price vs CPOR case SRP — activation signal (BACKLOG-130).

Column mapping (locked for this unit)
------------------------------------
- ``listing_price`` ← ``listing_observation.extracted_price`` (storefront, typically ZAR).
- ``case_price`` ← ``cpor_case_line.srp`` (case retail SRP for that product line).
- Period ← observation date within ``cpor_case.window_start`` .. ``window_end``.
- Identity ← ``customer_listing.customer_id`` + ``customer_listing.product_id``
  must match ``cpor_case.customer_id`` + ``cpor_case_line.product_id``.

Rule (Warren 2026-08-10): if a case exists for the period and listing price is
**higher** than case SRP → treat as **not activated**. No case → ``no_case_detected``.
Does not require multi-week observation history.

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

    if listing.product_id is None:
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
    # Filter excluded statuses in Python (status vocabulary may grow).
    cases = [(c, ln) for c, ln in rows if (c.status or "").strip().lower() not in _EXCLUDED_CASE_STATUSES]

    if not cases:
        out["status"] = "no_case_detected"
        out["message"] = (
            f"No CPOR case detected for customer {listing.customer_id} / "
            f"product {listing.product_id} covering {as_of.isoformat()}."
        )
        return out

    # Prefer the newest open case; if multiple lines, take the one with lowest SRP
    # (tightest activation bar for "listing should not be higher").
    case, line = min(cases, key=lambda pair: (float(pair[1].srp), -int(pair[0].id)))
    case_price = float(line.srp)
    out.update(
        {
            "case_id": int(case.id),
            "case_code": case.case_code,
            "case_status": case.status,
            "case_window_start": case.window_start.isoformat(),
            "case_window_end": case.window_end.isoformat(),
            "case_line_id": int(line.id),
            "case_price": case_price,
        }
    )

    if float(listing_price) > case_price + _PRICE_TOLERANCE:
        out["status"] = "not_activated"
        out["message"] = (
            f"Listing price {listing_price} is higher than case SRP {case_price} "
            f"(case {case.case_code}) — promo likely not activated by customer."
        )
    else:
        out["status"] = "price_consistent"
        out["message"] = (
            f"Listing price {listing_price} is at or below case SRP {case_price} "
            f"(case {case.case_code})."
        )
    return out


def as_of_from_fetched_at(fetched_at: datetime | None) -> date:
    if fetched_at is None:
        return date.today()
    if fetched_at.tzinfo is not None:
        return fetched_at.date()
    return fetched_at.date()
