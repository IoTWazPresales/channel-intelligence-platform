"""Shared observation LAG for shipping ETA shifts and newly-landed (SH-04).

One window mechanism: LAG any observation date column over ``line_identity_key``
ordered by ``valid_from``. Callers supply identity scope; they must not copy this SQL.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Iterable, Mapping

from sqlalchemy import Select, Subquery, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql import ColumnElement

from app.models.dimensions import DimCustomer, DimDistributor
from app.models.facts import FactInboundShipment
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.shipping_commercial_kpis import predicate_current_incoming
from app.services.shipping_distributor_display import resolve_distributor_display

PUBLIC_ETA_SHIFT_SAMPLE_CAP = 50
PUBLIC_ETA_SHIFT_SAMPLE_KEYS: frozenset[str] = frozenset(
    {
        "source_key",
        "direction",
        "previous_effective",
        "current_effective",
        "delta_days",
        "current_est_pod",
        "current_promise",
    }
)

LINE_COLUMN_KEYS: frozenset[str] = frozenset(
    {"distributor", "customer", "date", "sales_model", "qty"}
)


def observation_field_lag(field: ColumnElement[Any] | InstrumentedAttribute[Any]) -> ColumnElement[Any]:
    """LAG ``field`` over identity ordered by ``valid_from``."""
    return func.lag(field).over(
        partition_by=ShipmentEvidenceObservation.line_identity_key,
        order_by=ShipmentEvidenceObservation.valid_from.asc(),
    )


def fact_evidence_scope_stmt(
    *,
    today: date,
    require_current_incoming: bool = True,
    scoped_ids: list[int] | None = None,
) -> Select[Any]:
    stmt = select(
        FactInboundShipment.id,
        FactInboundShipment.shipment_evidence_line_id,
    ).select_from(FactInboundShipment)
    if require_current_incoming:
        stmt = stmt.where(predicate_current_incoming(today))
    if scoped_ids is not None:
        stmt = stmt.where(FactInboundShipment.id.in_(scoped_ids))
    return stmt.where(FactInboundShipment.shipment_evidence_line_id.is_not(None))


def identity_scope_from_fact_subquery(fact_scope: Subquery) -> tuple[Select[Any], Select[Any]]:
    evid_ids = select(fact_scope.c.shipment_evidence_line_id).distinct()
    identity_keys = (
        select(ShipmentEvidenceObservation.line_identity_key)
        .where(ShipmentEvidenceObservation.evidence_line_id.in_(evid_ids))
        .distinct()
    )
    return evid_ids, identity_keys


def identity_scope_for_job(import_job_id: int) -> tuple[Select[Any], Select[Any]]:
    evid_ids = (
        select(ShipmentEvidenceObservation.evidence_line_id)
        .where(
            ShipmentEvidenceObservation.import_job_id == int(import_job_id),
            ShipmentEvidenceObservation.evidence_line_id.is_not(None),
        )
        .distinct()
    )
    identity_keys = (
        select(ShipmentEvidenceObservation.line_identity_key)
        .where(ShipmentEvidenceObservation.import_job_id == int(import_job_id))
        .distinct()
    )
    return evid_ids, identity_keys


def observation_lag_window(
    identity_keys: Select[Any],
    fields: Mapping[str, ColumnElement[Any] | InstrumentedAttribute[Any]],
    *,
    exclude_import_job_ids: Iterable[int] | None = None,
) -> Subquery:
    """Windowed subquery: current ``fields`` plus ``prev_<name>`` LAG columns."""
    current_cols = [col.label(name) for name, col in fields.items()]
    prev_cols = [observation_field_lag(col).label(f"prev_{name}") for name, col in fields.items()]
    stmt = select(
        ShipmentEvidenceObservation.id,
        ShipmentEvidenceObservation.line_identity_key,
        ShipmentEvidenceObservation.source_key,
        ShipmentEvidenceObservation.import_job_id,
        ShipmentEvidenceObservation.evidence_line_id,
        ShipmentEvidenceObservation.sales_model_name,
        ShipmentEvidenceObservation.quantity,
        ShipmentEvidenceObservation.bill_to_raw,
        ShipmentEvidenceObservation.customer_dealer_token,
        observation_field_lag(ShipmentEvidenceObservation.id).label("prev_id"),
        *current_cols,
        *prev_cols,
    ).where(ShipmentEvidenceObservation.line_identity_key.in_(identity_keys))
    skip = sorted({int(x) for x in (exclude_import_job_ids or [])})
    if skip:
        stmt = stmt.where(ShipmentEvidenceObservation.import_job_id.notin_(skip))
    return stmt.subquery()


def empty_eta_shift_result(*, require_current_incoming: bool) -> dict[str, Any]:
    return {
        "slipped_count": 0,
        "improved_count": 0,
        "net_direction": "neutral",
        "samples": [],
        "cohort_definition": "current_incoming" if require_current_incoming else "lifetime",
    }


def customer_display_label(
    *,
    customer_name: str | None,
    customer_code: str | None,
    customer_dealer_token: str | None,
) -> str:
    cn = (customer_name or "").strip()
    if cn:
        return cn[:240]
    tok = (customer_dealer_token or "").strip()
    if tok:
        return tok[:200]
    cc = (customer_code or "").strip()
    if cc:
        return cc[:240]
    return "—"


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _delta_days(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "days"):
        return int(value.days)
    return int(value)


def _qty(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


async def attach_fact_line_columns(
    db: AsyncSession,
    source_keys: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Map ``source_key`` → distributor / customer / sales_model / qty (no date)."""
    keys = [k for k in dict.fromkeys(source_keys) if k]
    if not keys:
        return {}
    stmt = (
        select(
            FactInboundShipment.source_key,
            FactInboundShipment.sales_model_name,
            FactInboundShipment.quantity,
            FactInboundShipment.bill_to_raw,
            FactInboundShipment.ship_to_raw,
            FactInboundShipment.customer_dealer_token,
            FactInboundShipment.distributor_resolution_token,
            DimDistributor.name.label("dist_name"),
            DimDistributor.code.label("dist_code"),
            DimCustomer.name.label("cust_name"),
            DimCustomer.code.label("cust_code"),
        )
        .select_from(FactInboundShipment)
        .outerjoin(DimDistributor, FactInboundShipment.distributor_id == DimDistributor.id)
        .outerjoin(DimCustomer, FactInboundShipment.customer_id == DimCustomer.id)
        .where(FactInboundShipment.source_key.in_(keys))
    )
    out: dict[str, dict[str, Any]] = {}
    for row in (await db.execute(stmt)).mappings().all():
        sk = str(row["source_key"])
        dist_label, _ = resolve_distributor_display(
            distributor_name=row.get("dist_name"),
            distributor_code=row.get("dist_code"),
            bill_to_raw=row.get("bill_to_raw"),
            ship_to_raw=row.get("ship_to_raw"),
            distributor_resolution_token=row.get("distributor_resolution_token"),
        )
        out[sk] = {
            "distributor": dist_label,
            "customer": customer_display_label(
                customer_name=row.get("cust_name"),
                customer_code=row.get("cust_code"),
                customer_dealer_token=row.get("customer_dealer_token"),
            ),
            "sales_model": (row.get("sales_model_name") or None),
            "qty": _qty(row.get("quantity")),
        }
    return out


def _merge_line_columns(
    sample: dict[str, Any],
    *,
    fact_cols: dict[str, dict[str, Any]],
    source_key: str | None,
    date_value: Any,
    fallback_sales_model: Any = None,
    fallback_qty: Any = None,
    fallback_customer_token: str | None = None,
    fallback_bill_to: str | None = None,
) -> dict[str, Any]:
    attached = fact_cols.get(source_key or "") if source_key else None
    if attached:
        sample["distributor"] = attached["distributor"]
        sample["customer"] = attached["customer"]
        sample["sales_model"] = attached["sales_model"]
        sample["qty"] = attached["qty"]
    else:
        dist_label, _ = resolve_distributor_display(
            distributor_name=None,
            distributor_code=None,
            bill_to_raw=fallback_bill_to,
        )
        sample["distributor"] = dist_label
        sample["customer"] = customer_display_label(
            customer_name=None,
            customer_code=None,
            customer_dealer_token=fallback_customer_token,
        )
        sample["sales_model"] = (str(fallback_sales_model) if fallback_sales_model else None)
        sample["qty"] = _qty(fallback_qty)
    sample["date"] = _iso(date_value)
    return sample


async def compute_eta_shifts(
    db: AsyncSession,
    *,
    evid_ids: Select[Any],
    identity_keys: Select[Any],
    sample_limit: int,
    require_current_incoming: bool,
    cap_samples: bool = True,
    include_line_columns: bool = False,
    exclude_import_job_ids: Iterable[int] | None = None,
    open_only: bool = False,
) -> dict[str, Any]:
    line_win = observation_lag_window(
        identity_keys,
        {
            "est_pod": ShipmentEvidenceObservation.est_pod_date,
            "promise": ShipmentEvidenceObservation.promise_date,
            "pod_date": ShipmentEvidenceObservation.pod_date,
        },
        exclude_import_job_ids=exclude_import_job_ids,
    )
    cur_eff = func.coalesce(line_win.c.est_pod, line_win.c.promise)
    prev_eff = func.coalesce(line_win.c.prev_est_pod, line_win.c.prev_promise)
    delta_days = cur_eff - prev_eff
    where_clauses = [
        prev_eff.is_not(None),
        cur_eff.is_not(None),
        line_win.c.evidence_line_id.in_(evid_ids),
    ]
    if open_only:
        where_clauses.append(line_win.c.pod_date.is_(None))
    base = (
        select(
            line_win.c.source_key,
            line_win.c.sales_model_name,
            line_win.c.quantity,
            line_win.c.bill_to_raw,
            line_win.c.customer_dealer_token,
            cur_eff.label("current_effective"),
            prev_eff.label("previous_effective"),
            line_win.c.est_pod.label("current_est_pod"),
            line_win.c.promise.label("current_promise"),
            line_win.c.prev_est_pod.label("previous_est_pod"),
            line_win.c.prev_promise.label("previous_promise"),
            delta_days.label("delta_days"),
        )
        .select_from(line_win)
        .where(*where_clauses)
    )
    slipped_sub = base.where(cur_eff > prev_eff).subquery()
    improved_sub = base.where(cur_eff < prev_eff).subquery()
    slipped_count = int((await db.scalar(select(func.count()).select_from(slipped_sub))) or 0)
    improved_count = int((await db.scalar(select(func.count()).select_from(improved_sub))) or 0)

    samples: list[dict[str, Any]] = []
    if cap_samples:
        lim: int | None = max(0, min(int(sample_limit), PUBLIC_ETA_SHIFT_SAMPLE_CAP))
        fetch_samples = lim > 0
    else:
        lim = None if int(sample_limit) <= 0 else int(sample_limit)
        fetch_samples = True
    if fetch_samples:
        slip_stmt = select(slipped_sub).order_by(slipped_sub.c.delta_days.desc())
        imp_stmt = select(improved_sub).order_by(improved_sub.c.delta_days.asc())
        if lim is not None:
            slip_stmt = slip_stmt.limit(lim)
            imp_stmt = imp_stmt.limit(lim)
        slip_rows = (await db.execute(slip_stmt)).mappings().all()
        imp_rows = (await db.execute(imp_stmt)).mappings().all()

        def _row_to_sample(row: Mapping[str, Any], direction: str) -> dict[str, Any]:
            return {
                "source_key": row.get("source_key"),
                "direction": direction,
                "previous_effective": _iso(row.get("previous_effective")),
                "current_effective": _iso(row.get("current_effective")),
                "delta_days": _delta_days(row.get("delta_days")),
                "current_est_pod": _iso(row.get("current_est_pod")),
                "current_promise": _iso(row.get("current_promise")),
            }

        raw_samples = [_row_to_sample(dict(r), "slipped") for r in slip_rows] + [
            _row_to_sample(dict(r), "improved") for r in imp_rows
        ]
        if include_line_columns:
            fact_cols = await attach_fact_line_columns(
                db, [str(s["source_key"]) for s in raw_samples if s.get("source_key")]
            )
            row_by_key = {str(dict(r).get("source_key")): dict(r) for r in list(slip_rows) + list(imp_rows)}
            for s in raw_samples:
                raw = row_by_key.get(str(s.get("source_key")) or "")
                _merge_line_columns(
                    s,
                    fact_cols=fact_cols,
                    source_key=s.get("source_key"),
                    date_value=s.get("current_effective"),
                    fallback_sales_model=(raw or {}).get("sales_model_name"),
                    fallback_qty=(raw or {}).get("quantity"),
                    fallback_customer_token=(raw or {}).get("customer_dealer_token"),
                    fallback_bill_to=(raw or {}).get("bill_to_raw"),
                )
                s["date"] = s.get("current_effective")
        samples = raw_samples

    net = "neutral"
    if slipped_count > improved_count:
        net = "slipped"
    elif improved_count > slipped_count:
        net = "improved"
    return {
        "slipped_count": slipped_count,
        "improved_count": improved_count,
        "net_direction": net,
        "samples": samples,
        "cohort_definition": "current_incoming" if require_current_incoming else "lifetime",
    }


