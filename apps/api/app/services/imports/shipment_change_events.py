"""Derive shipment change events from observation chains (Plan D phase 4, derived-on-read)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.shipment_evidence_observation import ShipmentEvidenceObservation
from app.services.imports.shipment_invoice_graduation import (
    GRADUATION_KIND_INVOICE_MINT,
    is_blank_invoice_shipped_obs,
    is_numbered_invoice_shipped_obs,
    lineage_key_from_obs,
    lineage_thread_key,
)

EventType = Literal["date_slip", "qty_change", "graduated", "pod_reversal"]

_DATE_SLIP_FIELDS: tuple[tuple[str, str], ...] = (
    ("est_pod_date", "est_pod"),
    ("crad_date", "crad"),
    ("erd_date", "erd"),
    ("schedule_ship_date", "schedule_ship"),
    ("promise_date", "promise"),
    ("exwork_date", "exwork"),
)

QTY_EPS = 1e-6


@dataclass
class ShipmentChangeEvent:
    event_type: EventType
    line_identity_key: str
    observation_id: int
    prior_observation_id: int | None
    import_job_id: int
    valid_from: datetime
    operating_unit: str | None
    order_no: str | None
    order_line: str | None
    item_code: str | None
    delivery_no: str | None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "line_identity_key": self.line_identity_key,
            "observation_id": self.observation_id,
            "prior_observation_id": self.prior_observation_id,
            "import_job_id": self.import_job_id,
            "valid_from": self.valid_from.isoformat(),
            "operating_unit": self.operating_unit,
            "order_no": self.order_no,
            "order_line": self.order_line,
            "item_code": self.item_code,
            "delivery_no": self.delivery_no,
            "details": self.details,
        }


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def order_grain_key(
    *,
    operating_unit: str | None,
    order_no: str | None,
    order_line: str | None,
    item_code: str | None,
) -> str | None:
    ou = _norm(operating_unit)
    on = _norm(order_no)
    ol = _norm(order_line)
    ic = _norm(item_code)
    if not ou or not on or not ic:
        return None
    return f"order:{ou}|{on}|{ol}|{ic}"


def _has_pod(obs: ShipmentEvidenceObservation) -> bool:
    return obs.pod_date is not None


def _line_state_norm(obs: ShipmentEvidenceObservation) -> str:
    return (obs.line_state or "").strip().lower()


def _days_delta(before: date | None, after: date | None) -> int | None:
    if before is None or after is None:
        return None
    return (after - before).days


def _diff_consecutive_pair(
    prior: ShipmentEvidenceObservation,
    curr: ShipmentEvidenceObservation,
) -> list[ShipmentChangeEvent]:
    events: list[ShipmentChangeEvent] = []
    base = {
        "line_identity_key": curr.line_identity_key,
        "observation_id": int(curr.id),
        "prior_observation_id": int(prior.id),
        "import_job_id": int(curr.import_job_id),
        "valid_from": curr.valid_from,
        "operating_unit": curr.operating_unit,
        "order_no": curr.order_no,
        "order_line": curr.order_line,
        "item_code": curr.item_code,
        "delivery_no": curr.delivery_no,
    }

    for col, label in _DATE_SLIP_FIELDS:
        prev_d = getattr(prior, col, None)
        curr_d = getattr(curr, col, None)
        if prev_d == curr_d:
            continue
        delta = _days_delta(prev_d, curr_d)
        if delta is None:
            continue
        if delta == 0:
            continue
        events.append(
            ShipmentChangeEvent(
                event_type="date_slip",
                details={
                    "date_field": label,
                    "prior_date": prev_d.isoformat() if prev_d else None,
                    "current_date": curr_d.isoformat() if curr_d else None,
                    "days_moved": delta,
                },
                **base,
            )
        )

    prev_q = float(prior.quantity or 0)
    curr_q = float(curr.quantity or 0)
    if abs(curr_q - prev_q) > QTY_EPS:
        events.append(
            ShipmentChangeEvent(
                event_type="qty_change",
                details={
                    "prior_quantity": prev_q,
                    "current_quantity": curr_q,
                    "delta": curr_q - prev_q,
                },
                **base,
            )
        )

    if _has_pod(prior) and not _has_pod(curr):
        events.append(
            ShipmentChangeEvent(
                event_type="pod_reversal",
                details={
                    "prior_pod_date": prior.pod_date.isoformat() if prior.pod_date else None,
                    "current_pod_date": None,
                    "steward_flag": True,
                    "note": "POD cleared — does not un-graduate shipped state",
                },
                **base,
            )
        )

    return events


def _observation_filters(
  *,
  period: str | None,
  distributor_id: int | None,
  operating_unit: str | None,
) -> list[Any]:
    clauses: list[Any] = []
    if distributor_id is not None:
        clauses.append(ShipmentEvidenceObservation.distributor_id == int(distributor_id))
    if operating_unit:
        clauses.append(
            func.lower(func.btrim(func.coalesce(ShipmentEvidenceObservation.operating_unit, "")))
            == operating_unit.strip().lower()
        )
    if period:
        # period like 26Q2 -> filter by valid_from quarter
        from app.services.commercial_planner.lineup_period_canonical import parse_period_filter_to_year_quarter

        y, q = parse_period_filter_to_year_quarter(period)
        start_month = (q - 1) * 3 + 1
        end_month = start_month + 2
        start = date(y, start_month, 1)
        if end_month == 12:
            end = date(y + 1, 1, 1)
        else:
            end = date(y, end_month + 1, 1)
        clauses.append(ShipmentEvidenceObservation.valid_from >= datetime.combine(start, datetime.min.time()))
        clauses.append(ShipmentEvidenceObservation.valid_from < datetime.combine(end, datetime.min.time()))
    return clauses


def _supplement_invoice_mint_lineage_observations(
    db: Session,
    rows: list[ShipmentEvidenceObservation],
    *,
    base_clauses: list[Any],
) -> list[ShipmentEvidenceObservation]:
    """Load single-version numbered ship observations for lineage threads already in *rows*."""
    seen_ids = {int(o.id) for o in rows}
    lineages: set[tuple[str, str, str, str]] = set()
    for obs in rows:
        lk = lineage_key_from_obs(obs)
        if lk is not None:
            lineages.add(lk)
    if not lineages:
        return rows

    merged = list(rows)
    chunk_size = 80
    lineage_list = sorted(lineages)
    for i in range(0, len(lineage_list), chunk_size):
        chunk = lineage_list[i : i + chunk_size]
        lineage_filters = [
            and_(
                func.coalesce(ShipmentEvidenceObservation.operating_unit, "") == ou,
                ShipmentEvidenceObservation.order_no == on,
                ShipmentEvidenceObservation.order_line == ol,
                ShipmentEvidenceObservation.item_code == ic,
            )
            for ou, on, ol, ic in chunk
        ]
        sup_stmt = select(ShipmentEvidenceObservation).where(
            func.lower(func.coalesce(ShipmentEvidenceObservation.line_state, "")) == "shipped",
            func.coalesce(ShipmentEvidenceObservation.invoice_line, "") != "",
            or_(*lineage_filters),
        )
        if base_clauses:
            sup_stmt = sup_stmt.where(and_(*base_clauses))
        for obs in db.scalars(sup_stmt).all():
            oid = int(obs.id)
            if oid in seen_ids or not is_numbered_invoice_shipped_obs(obs):
                continue
            merged.append(obs)
            seen_ids.add(oid)
    return merged


def derive_change_events(
    db: Session,
    *,
    period: str | None = None,
    distributor_id: int | None = None,
    operating_unit: str | None = None,
    event_types: set[str] | None = None,
    line_identity_key: str | None = None,
    limit: int = 5000,
) -> list[ShipmentChangeEvent]:
    """Diff consecutive observations per line_identity_key (+ order-grain graduated events)."""
    clauses = _observation_filters(
        period=period, distributor_id=distributor_id, operating_unit=operating_unit
    )
    if line_identity_key:
        clauses.append(ShipmentEvidenceObservation.line_identity_key == line_identity_key)

    if line_identity_key:
        stmt = select(ShipmentEvidenceObservation)
        if clauses:
            stmt = stmt.where(and_(*clauses))
    else:
        multi_keys = (
            select(ShipmentEvidenceObservation.line_identity_key)
            .where(and_(*clauses)) if clauses else select(ShipmentEvidenceObservation.line_identity_key)
        )
        multi_keys = multi_keys.group_by(ShipmentEvidenceObservation.line_identity_key).having(
            func.count() > 1
        )
        stmt = select(ShipmentEvidenceObservation).where(
            ShipmentEvidenceObservation.line_identity_key.in_(multi_keys)
        )
        if clauses:
            stmt = stmt.where(and_(*clauses))

    stmt = stmt.order_by(
        ShipmentEvidenceObservation.line_identity_key,
        ShipmentEvidenceObservation.valid_from,
        ShipmentEvidenceObservation.id,
    )
    if limit > 0 and line_identity_key:
        stmt = stmt.limit(limit * 20)

    rows = list(db.scalars(stmt).all())
    if not line_identity_key:
        rows = _supplement_invoice_mint_lineage_observations(db, rows, base_clauses=clauses)
    by_key: dict[str, list[ShipmentEvidenceObservation]] = {}
    for obs in rows:
        by_key.setdefault(obs.line_identity_key, []).append(obs)

    events: list[ShipmentChangeEvent] = []
    order_index: dict[str, list[ShipmentEvidenceObservation]] = {}

    for key, chain in by_key.items():
        chain.sort(key=lambda o: (o.valid_from, o.id))
        for i in range(1, len(chain)):
            pair_events = _diff_consecutive_pair(chain[i - 1], chain[i])
            events.extend(pair_events)

        for obs in chain:
            ogk = order_grain_key(
                operating_unit=obs.operating_unit,
                order_no=obs.order_no,
                order_line=obs.order_line,
                item_code=obs.item_code,
            ) or lineage_thread_key(obs)
            if ogk:
                order_index.setdefault(ogk, []).append(obs)

    graduated_seen: set[tuple[str, int]] = set()
    invoice_mint_seen: set[tuple[str, int]] = set()
    for ogk, chain in order_index.items():
        chain.sort(key=lambda o: (o.valid_from, o.id))
        had_open = False
        open_obs_id: int | None = None
        blank_invoice_shipped_obs_id: int | None = None
        for obs in chain:
            st = _line_state_norm(obs)
            if st in ("open_order", "open", "unship"):
                had_open = True
                open_obs_id = int(obs.id)
            elif st == "shipped" and is_blank_invoice_shipped_obs(obs):
                blank_invoice_shipped_obs_id = int(obs.id)
            elif st == "shipped" and had_open:
                dedupe = (ogk, int(obs.id))
                if dedupe in graduated_seen:
                    continue
                graduated_seen.add(dedupe)
                events.append(
                    ShipmentChangeEvent(
                        event_type="graduated",
                        line_identity_key=obs.line_identity_key,
                        observation_id=int(obs.id),
                        prior_observation_id=open_obs_id,
                        import_job_id=int(obs.import_job_id),
                        valid_from=obs.valid_from,
                        operating_unit=obs.operating_unit,
                        order_no=obs.order_no,
                        order_line=obs.order_line,
                        item_code=obs.item_code,
                        delivery_no=obs.delivery_no,
                        details={
                            "order_grain_key": ogk,
                            "prior_line_state": "open_order",
                            "current_line_state": "shipped",
                            "graduation_kind": "open_to_shipped",
                        },
                    )
                )
                had_open = False
                open_obs_id = None
            elif st == "shipped" and is_numbered_invoice_shipped_obs(obs) and blank_invoice_shipped_obs_id:
                lk = lineage_key_from_obs(obs)
                dedupe_key = f"{lk}|{obs.line_identity_key}"
                dedupe = (dedupe_key, int(obs.id))
                if dedupe in invoice_mint_seen:
                    continue
                invoice_mint_seen.add(dedupe)
                events.append(
                    ShipmentChangeEvent(
                        event_type="graduated",
                        line_identity_key=obs.line_identity_key,
                        observation_id=int(obs.id),
                        prior_observation_id=blank_invoice_shipped_obs_id,
                        import_job_id=int(obs.import_job_id),
                        valid_from=obs.valid_from,
                        operating_unit=obs.operating_unit,
                        order_no=obs.order_no,
                        order_line=obs.order_line,
                        item_code=obs.item_code,
                        delivery_no=obs.delivery_no,
                        details={
                            "order_grain_key": ogk,
                            "graduation_kind": GRADUATION_KIND_INVOICE_MINT,
                            "prior_line_state": "shipped",
                            "current_line_state": "shipped",
                            "prior_identity_grain": "order",
                            "current_identity_grain": "ship",
                        },
                    )
                )
                blank_invoice_shipped_obs_id = None

    if event_types:
        allowed = {t.strip().lower() for t in event_types}
        events = [e for e in events if e.event_type in allowed]

    events.sort(key=lambda e: (e.valid_from, e.observation_id))
    if limit > 0:
        events = events[:limit]
    return events


def summarize_change_events(events: list[ShipmentChangeEvent]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for e in events:
        counts[e.event_type] = counts.get(e.event_type, 0) + 1
    return counts


def group_events_by_line(events: list[ShipmentChangeEvent]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for e in events:
        out.setdefault(e.line_identity_key, []).append(e.to_dict())
    return out
