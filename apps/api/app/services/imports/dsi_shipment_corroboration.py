"""Read-only shipment_evidence_line corroboration for DSI (signal-only; no auto-resolve)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Date, and_, func, literal, or_, select
from sqlalchemy.orm import Session

from app.models.shipment_evidence import ShipmentEvidenceLine


def _same_calendar_month_as_evidence(evidence_date: date) -> Any:
    co = func.coalesce(
        ShipmentEvidenceLine.ship_confirm_date,
        ShipmentEvidenceLine.schedule_ship_date,
        ShipmentEvidenceLine.promise_date,
    )
    return and_(
        co.isnot(None),
        func.date_trunc("month", co) == func.date_trunc("month", literal(evidence_date, type_=Date())),
    )


def shipment_corroboration_for_product(
    db: Session,
    *,
    distributor_id: int,
    evidence_date: date | None,
    raw_product_token: str | None,
    resolved_product_id: int | None,
) -> dict[str, Any] | None:
    """Return JSON-serializable corroboration dict, or None when lookup is not applicable.

    Includes ``distinct_resolved_product_ids``: distinct ``ShipmentEvidenceLine.product_id`` values
    among matching **resolved_unique** lines in the evidence month (used to break DSI ambiguity).

    For raw-token matching, rows are first limited to the DSI **distributor_id**. If that scope yields
    no distinct product ids, the same token + month match is retried **across all distributors**; when
    that broader set contains exactly one distinct ``product_id``, it is returned and
    ``distinct_ids_scope`` is ``cross_distributor``. Otherwise ``distinct_ids_scope`` is
    ``distributor_specific`` when the distributor-scoped set is non-empty.
    """
    if not distributor_id or evidence_date is None:
        return None
    base_where = (
        ShipmentEvidenceLine.distributor_id == int(distributor_id),
        ShipmentEvidenceLine.product_resolution_status == "resolved_unique",
        ShipmentEvidenceLine.product_id.isnot(None),
        _same_calendar_month_as_evidence(evidence_date),
    )
    base_count = select(func.count()).select_from(ShipmentEvidenceLine).where(*base_where)
    if resolved_product_id is not None:
        n = db.scalar(base_count.where(ShipmentEvidenceLine.product_id == int(resolved_product_id)))
        mode = "resolved_product_id"
        ids_stmt = (
            select(ShipmentEvidenceLine.product_id)
            .where(*base_where, ShipmentEvidenceLine.product_id == int(resolved_product_id))
            .distinct()
        )
        cnt = int(n or 0)
        if cnt <= 0:
            return None
        raw_ids = list(db.scalars(ids_stmt).all())
        distinct_ids = sorted({int(x) for x in raw_ids if x is not None})[:32]
        return {
            "kind": "shipment_evidence_product",
            "match_count": cnt,
            "mode": mode,
            "distributor_id": int(distributor_id),
            "evidence_month": evidence_date.isoformat()[:7],
            "distinct_resolved_product_ids": distinct_ids,
            "distinct_ids_scope": "distributor_specific",
        }

    from app.services.imports.distributor_sales_inventory import _product_token_key

    pk = _product_token_key(raw_product_token)
    if not pk:
        return None
    token_match = or_(
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.item_code, ""))) == literal(pk),
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.ean_code, ""))) == literal(pk),
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.upc_code, ""))) == literal(pk),
        func.lower(func.btrim(func.coalesce(ShipmentEvidenceLine.sales_model_name, ""))) == literal(pk),
    )
    mode = "raw_product_token_tiers"

    n_dist = db.scalar(base_count.where(token_match))
    ids_dist_stmt = select(ShipmentEvidenceLine.product_id).where(*base_where, token_match).distinct()
    distinct_dist: list[int] = []
    if n_dist and int(n_dist) > 0:
        raw_d = list(db.scalars(ids_dist_stmt).all())
        distinct_dist = sorted({int(x) for x in raw_d if x is not None})[:32]

    if distinct_dist:
        return {
            "kind": "shipment_evidence_product",
            "match_count": int(n_dist or 0),
            "mode": mode,
            "distributor_id": int(distributor_id),
            "evidence_month": evidence_date.isoformat()[:7],
            "distinct_resolved_product_ids": distinct_dist,
            "distinct_ids_scope": "distributor_specific",
        }

    cross_where = (
        ShipmentEvidenceLine.product_resolution_status == "resolved_unique",
        ShipmentEvidenceLine.product_id.isnot(None),
        _same_calendar_month_as_evidence(evidence_date),
        token_match,
    )
    cross_count = select(func.count()).select_from(ShipmentEvidenceLine).where(*cross_where)
    n_cross = db.scalar(cross_count)
    if not n_cross or int(n_cross) <= 0:
        return None
    ids_cross_stmt = select(ShipmentEvidenceLine.product_id).where(*cross_where).distinct()
    raw_c = list(db.scalars(ids_cross_stmt).all())
    distinct_cross = sorted({int(x) for x in raw_c if x is not None})[:32]
    if len(distinct_cross) != 1:
        return None
    return {
        "kind": "shipment_evidence_product",
        "match_count": int(n_cross or 0),
        "mode": mode,
        "distributor_id": int(distributor_id),
        "evidence_month": evidence_date.isoformat()[:7],
        "distinct_resolved_product_ids": distinct_cross,
        "distinct_ids_scope": "cross_distributor",
    }


def shipment_corroboration_for_customer(
    db: Session,
    *,
    distributor_id: int,
    evidence_date: date | None,
    customer_primary_raw: str | None,
    dealer_group_raw: str | None,
    resolved_customer_id: int | None,
) -> dict[str, Any] | None:
    if not distributor_id or evidence_date is None:
        return None
    base = (
        select(func.count())
        .select_from(ShipmentEvidenceLine)
        .where(
            ShipmentEvidenceLine.distributor_id == int(distributor_id),
            ShipmentEvidenceLine.customer_id.isnot(None),
            ShipmentEvidenceLine.customer_resolution_status == "resolved_unique",
            _same_calendar_month_as_evidence(evidence_date),
        )
    )
    if resolved_customer_id is not None:
        n = db.scalar(base.where(ShipmentEvidenceLine.customer_id == int(resolved_customer_id)))
        mode = "resolved_customer_id"
    else:
        from app.services.imports.distributor_sales_inventory import _norm_key

        nk = _norm_key(customer_primary_raw or "")
        dg = (dealer_group_raw or "").strip()[:512].lower() if dealer_group_raw else ""
        if not nk and not dg:
            return None
        conds = []
        if nk:
            tok = func.nullif(func.btrim(ShipmentEvidenceLine.customer_dealer_token), "")
            conds.append(func.lower(tok) == literal(nk))
        if dg:
            esc = dg.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pat = f"%{esc}%"
            conds.append(
                or_(
                    ShipmentEvidenceLine.bill_to_raw.ilike(literal(pat), escape="\\"),
                    ShipmentEvidenceLine.ship_to_raw.ilike(literal(pat), escape="\\"),
                )
            )
        if not conds:
            return None
        n = db.scalar(base.where(or_(*conds)))
        mode = "raw_token_fuzzy"
    cnt = int(n or 0)
    if cnt <= 0:
        return None
    return {
        "kind": "shipment_evidence_customer",
        "match_count": cnt,
        "mode": mode,
        "distributor_id": int(distributor_id),
        "evidence_month": evidence_date.isoformat()[:7],
    }
