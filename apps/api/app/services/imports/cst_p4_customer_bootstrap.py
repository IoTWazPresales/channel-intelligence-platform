"""Placeholder customer report configs for customers awaiting a sample file.

The steward chooses the customers (``customer_ids`` is an input: request body or script
argument). Nothing here is keyed to a named or fixed customer.

The bootstrap only ever creates or refreshes placeholder "awaiting sample file" rows.
A customer whose config has graduated past that stage (a real ``report_structure_type``
or ``feed_profile_json.vat_basis``; see ``_has_richer_config``) is reported as skipped
and never overwritten, whoever is in the list.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.services.imports.tenant_mapping_scope import effective_tenant_id

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


def _unique_ids(customer_ids: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for raw in customer_ids:
        cid = int(raw)
        if cid not in seen:
            seen.add(cid)
            out.append(cid)
    return out


def bootstrap_p4_customer_configs(
    session: Session,
    customer_ids: Iterable[int],
    *,
    tenant_id: str | None = None,
) -> dict[str, Any]:
    """Upsert placeholder `customer_report_config` rows for the steward-selected customers.

    Idempotent — safe to re-run. Ids that are not a dim_customer of ``tenant_id`` (default
    tenant when None) are reported in ``missing_customer`` and never written. Rows guarded by
    `_has_richer_config` are reported in ``skipped``, never overwritten (FLAG != BLOCK).
    """
    tid = effective_tenant_id(tenant_id)
    created: list[dict[str, Any]] = []
    updated: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    missing_customer: list[int] = []

    for customer_id in _unique_ids(customer_ids):
        customer = session.get(DimCustomer, customer_id)
        if customer is None or effective_tenant_id(getattr(customer, "tenant_id", None)) != tid:
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

        record = {"customer_id": customer_id, "name": customer.name}
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
