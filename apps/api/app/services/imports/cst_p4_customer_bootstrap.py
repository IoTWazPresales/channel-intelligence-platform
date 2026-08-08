"""P4 remaining customer report configs — placeholder cadence for pilots awaiting a sample file.

Canonical customer_ids fixed by Warren (Q-004): Evetech, Computer Mania, Incredible
Connection, Amazon, Hifi, Makro, Game. Verified against `cip` on 2026-08-08 —
`dim_customer.name` for each id matches this roster exactly (see task discovery).

Never touches Takealot (`customer_id=20`) — that customer already has a
hand-verified, richer config (`report_structure_type='flat'`,
`feed_profile_json.vat_basis` set — see `.tmp/apply_takealot_cst_config_db.py`)
and must not be clobbered by this bulk placeholder bootstrap. The same guard also
protects any *other* customer that already carries a real structure/vat_basis —
this bootstrap only ever creates or refreshes placeholder "awaiting sample file"
rows, never overwrites a config that has graduated past that stage.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer

TAKEALOT_CUSTOMER_ID = 20

P4_CUSTOMER_IDS: dict[int, str] = {
    52: "Evetech",
    18: "Computer Mania",
    12: "Incredible Connection",
    26: "Amazon",
    11: "Hifi",
    15: "Makro",
    57: "Game",
}

P4_EXPECTED_CADENCE = "weekly"
P4_NOTES = "P4 awaiting sample WEEK file (Q-004)"
P4_FEED_PROFILE: dict[str, Any] = {"status": "awaiting_sample_file", "pilot": "p4"}


def _has_richer_config(cfg: CustomerReportConfig) -> bool:
    """True when an existing config already carries real structure — never overwrite (FLAG != BLOCK)."""
    if cfg.report_structure_type:
        return True
    feed = cfg.feed_profile_json or {}
    if isinstance(feed, dict) and "vat_basis" in feed:
        return True
    return False


def bootstrap_p4_customer_configs(session: Session) -> dict[str, Any]:
    """Upsert placeholder `customer_report_config` rows for the P4 pilot roster.

    Idempotent — safe to re-run. Unknown customer_ids and rows guarded by
    `_has_richer_config` are reported in the result, never raised (FLAG != BLOCK).
    """
    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    missing_customer: list[int] = []

    for customer_id, expected_name in P4_CUSTOMER_IDS.items():
        if customer_id == TAKEALOT_CUSTOMER_ID:
            # Defensive — Takealot is never in P4_CUSTOMER_IDS, but this guard stays
            # even if the roster changes later.
            skipped.append({"customer_id": customer_id, "reason": "takealot_never_touched"})
            continue

        customer = session.get(DimCustomer, customer_id)
        if customer is None:
            missing_customer.append(customer_id)
            continue

        cfg = session.scalar(
            select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id)
        )
        if cfg is not None and _has_richer_config(cfg):
            skipped.append(
                {
                    "customer_id": customer_id,
                    "name": customer.name,
                    "reason": "richer_config_present",
                }
            )
            continue

        is_new = cfg is None
        if cfg is None:
            cfg = CustomerReportConfig(customer_id=customer_id)
            session.add(cfg)

        cfg.reports_expected = True
        cfg.expected_cadence = P4_EXPECTED_CADENCE
        cfg.report_structure_type = None
        cfg.notes = P4_NOTES
        cfg.feed_profile_json = dict(P4_FEED_PROFILE)
        session.add(cfg)

        record = {"customer_id": customer_id, "name": customer.name, "expected_name": expected_name}
        (created if is_new else updated).append(record)

    session.flush()
    return {
        "ok": True,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "missing_customer": missing_customer,
        "created_count": len(created),
        "updated_count": len(updated),
        "skipped_count": len(skipped),
    }
