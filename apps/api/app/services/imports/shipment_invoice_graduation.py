"""Invoice-line mint graduation: supersede blank-invoice order-grain shipped observations.

When a shipped line gains a numbered ``invoice_line``, the ``line_identity_key`` moves from
``order:…`` to ``ship:…``. Without supersession both identities stay current in
``shipment_evidence_current`` and double-count. This module quantity-gates graduation and
soft-supersedes via ``shipment_evidence_observation.superseded_by_id`` (no deletes).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.models.shipment_evidence_observation import ShipmentEvidenceObservation

logger = logging.getLogger(__name__)

QTY_EPS = 1e-6
STEWARD_FLAG_PARTIAL = "invoice_partial_graduation"
GRADUATION_KIND_INVOICE_MINT = "invoice_mint"

_CURRENT_VIEW_SQL = """
CREATE OR REPLACE VIEW shipment_evidence_current AS
SELECT DISTINCT ON (o.line_identity_key)
    o.id,
    o.line_identity_key,
    o.import_job_id,
    o.source_key,
    o.source_row_hash,
    o.evidence_line_id,
    o.valid_from,
    o.observed_at,
    o.superseded_by_id,
    o.source_sheet,
    o.source_row_number,
    o.report_type,
    o.line_state,
    o.raw_source_row,
    o.operating_unit,
    o.bill_to_raw,
    o.ship_to_raw,
    o.order_no,
    o.customer_po,
    COALESCE(sel.purchase_order_id, o.purchase_order_id) AS purchase_order_id,
    o.order_line,
    o.delivery_no,
    o.invoice_line,
    o.item_code,
    o.sales_model_name,
    o.customer_item,
    o.ean_code,
    o.upc_code,
    o.mpor_item_no,
    o.quantity,
    o.unit_price,
    o.amount,
    o.currency_code,
    o.ship_confirm_date,
    o.schedule_ship_date,
    o.promise_date,
    o.exwork_date,
    o.erd_date,
    o.est_pod_date,
    o.pod_date,
    COALESCE(sel.product_id, o.product_id) AS product_id,
    COALESCE(sel.product_resolution_status, o.product_resolution_status) AS product_resolution_status,
    COALESCE(sel.product_resolution_token, o.product_resolution_token) AS product_resolution_token,
    COALESCE(sel.product_resolution_detail, o.product_resolution_detail) AS product_resolution_detail,
    COALESCE(sel.distributor_id, o.distributor_id) AS distributor_id,
    COALESCE(sel.distributor_resolution_status, o.distributor_resolution_status) AS distributor_resolution_status,
    COALESCE(sel.distributor_resolution_token, o.distributor_resolution_token) AS distributor_resolution_token,
    o.customer_dealer_token,
    COALESCE(sel.resolved_customer_id, sel.customer_id, o.customer_id) AS customer_id,
    COALESCE(sel.customer_resolution_status, o.customer_resolution_status) AS customer_resolution_status,
    sel.resolved_customer_id,
    sel.resolved_distributor_id,
    sel.crad_date,
    o.created_at,
    o.updated_at
FROM shipment_evidence_observation o
LEFT JOIN shipment_evidence_line sel ON sel.id = o.evidence_line_id
WHERE o.superseded_by_id IS NULL
ORDER BY o.line_identity_key, o.valid_from DESC NULLS LAST, o.id DESC
"""

LineageKey = tuple[str, str, str, str]


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def lineage_key_from_obs(obs: ShipmentEvidenceObservation) -> LineageKey | None:
    on = _norm(obs.order_no)
    ic = _norm(obs.item_code)
    if not on or not ic:
        return None
    return (_norm(obs.operating_unit), on, _norm(obs.order_line), ic)


def lineage_thread_key(obs: ShipmentEvidenceObservation) -> str | None:
    """Stable lineage thread for change events and graduation (OU optional)."""
    lk = lineage_key_from_obs(obs)
    if lk is None:
        return None
    return "|".join(lk)


def _line_state_norm(obs: ShipmentEvidenceObservation) -> str:
    return (obs.line_state or "").strip().lower()


def is_blank_invoice_shipped_obs(obs: ShipmentEvidenceObservation) -> bool:
    if _line_state_norm(obs) != "shipped":
        return False
    if _norm(obs.invoice_line):
        return False
    key = (obs.line_identity_key or "").strip()
    return key.startswith("order:")


def is_numbered_invoice_shipped_obs(obs: ShipmentEvidenceObservation) -> bool:
    if _line_state_norm(obs) != "shipped":
        return False
    if not _norm(obs.invoice_line):
        return False
    key = (obs.line_identity_key or "").strip()
    return key.startswith("ship:")


def steward_flags(obs: ShipmentEvidenceObservation) -> list[str]:
    raw = obs.raw_source_row if isinstance(obs.raw_source_row, dict) else {}
    flags = raw.get("_steward_flags")
    if not isinstance(flags, list):
        return []
    return [str(f) for f in flags]


def has_partial_graduation_flag(obs: ShipmentEvidenceObservation) -> bool:
    return STEWARD_FLAG_PARTIAL in steward_flags(obs)


def _set_steward_flag(obs: ShipmentEvidenceObservation, flag: str) -> bool:
    raw = dict(obs.raw_source_row) if isinstance(obs.raw_source_row, dict) else {}
    flags = [str(f) for f in (raw.get("_steward_flags") or []) if f]
    if flag in flags:
        return False
    flags.append(flag)
    raw["_steward_flags"] = flags
    obs.raw_source_row = raw
    return True


def refresh_shipment_evidence_current_view(db: Session, *, admin_engine=None) -> None:
    """Replace view so superseded observations are excluded from current-state reads."""
    sql_drop = "DROP VIEW IF EXISTS shipment_evidence_current"
    sql_create = _CURRENT_VIEW_SQL.replace("CREATE OR REPLACE VIEW", "CREATE VIEW", 1)
    sql_grant = "GRANT SELECT ON shipment_evidence_current TO cip"
    try:
        db.execute(text(sql_drop))
        db.execute(text(sql_create))
        db.execute(text(sql_grant))
        db.flush()
    except Exception:
        if admin_engine is None:
            raise
        with admin_engine.connect() as conn:
            conn.execute(text(sql_drop))
            conn.execute(text(sql_create))
            conn.execute(text(sql_grant))
            conn.commit()


def load_unsuperseded_current_observations(db: Session) -> list[ShipmentEvidenceObservation]:
    """Latest observation per ``line_identity_key`` among non-superseded rows."""
    rows = db.execute(
        text(
            """
            SELECT DISTINCT ON (line_identity_key) id
            FROM shipment_evidence_observation
            WHERE superseded_by_id IS NULL
            ORDER BY line_identity_key, valid_from DESC NULLS LAST, id DESC
            """
        )
    ).all()
    if not rows:
        return []
    ids = [int(r[0]) for r in rows]
    by_id = {
        int(o.id): o
        for o in db.scalars(select(ShipmentEvidenceObservation).where(ShipmentEvidenceObservation.id.in_(ids))).all()
    }
    return [by_id[i] for i in ids if i in by_id]


def group_current_by_lineage(
    observations: list[ShipmentEvidenceObservation],
) -> dict[LineageKey, dict[str, list[ShipmentEvidenceObservation]]]:
    out: dict[LineageKey, dict[str, list[ShipmentEvidenceObservation]]] = defaultdict(
        lambda: {"blank": [], "numbered": []}
    )
    for obs in observations:
        lk = lineage_key_from_obs(obs)
        if lk is None:
            continue
        if is_blank_invoice_shipped_obs(obs):
            out[lk]["blank"].append(obs)
        elif is_numbered_invoice_shipped_obs(obs):
            out[lk]["numbered"].append(obs)
    return dict(out)


@dataclass
class LineageGraduationVerdict:
    lineage: LineageKey
    blank_keys: list[str] = field(default_factory=list)
    numbered_keys: list[str] = field(default_factory=list)
    blank_qty: float = 0.0
    numbered_qty: float = 0.0
    outcome: Literal["none", "full", "partial", "already_done"] = "none"
    anchor_observation_id: int | None = None


def evaluate_lineage_graduation(
    blank: list[ShipmentEvidenceObservation],
    numbered: list[ShipmentEvidenceObservation],
) -> LineageGraduationVerdict:
    lk: LineageKey = ("", "", "", "")
    if blank:
        lk = lineage_key_from_obs(blank[0]) or lk
    elif numbered:
        lk = lineage_key_from_obs(numbered[0]) or lk

    active_blank = [o for o in blank if o.superseded_by_id is None and not has_partial_graduation_flag(o)]
    if not active_blank or not numbered:
        return LineageGraduationVerdict(lineage=lk, outcome="none")

    if all(o.superseded_by_id is not None for o in blank):
        return LineageGraduationVerdict(lineage=lk, outcome="already_done")

    blank_qty = sum(float(o.quantity or 0) for o in active_blank)
    numbered_qty = sum(float(o.quantity or 0) for o in numbered)
    numbered_sorted = sorted(numbered, key=lambda o: (o.valid_from, o.id), reverse=True)
    anchor = numbered_sorted[0]

    verdict = LineageGraduationVerdict(
        lineage=lk,
        blank_keys=sorted({o.line_identity_key for o in active_blank}),
        numbered_keys=sorted({o.line_identity_key for o in numbered}),
        blank_qty=blank_qty,
        numbered_qty=numbered_qty,
        anchor_observation_id=int(anchor.id),
    )
    if abs(blank_qty - numbered_qty) <= QTY_EPS:
        verdict.outcome = "full"
    else:
        verdict.outcome = "partial"
    return verdict


def load_unsuperseded_observations_for_keys(
    db: Session,
    line_identity_keys: list[str],
) -> list[ShipmentEvidenceObservation]:
    """All non-superseded observation versions for the given identity keys."""
    keys = sorted({k for k in line_identity_keys if k})
    if not keys:
        return []
    return list(
        db.scalars(
            select(ShipmentEvidenceObservation).where(
                ShipmentEvidenceObservation.line_identity_key.in_(keys),
                ShipmentEvidenceObservation.superseded_by_id.is_(None),
            )
        ).all()
    )


def _mark_evidence_lines_superseded(
    db: Session,
    observations: list[ShipmentEvidenceObservation],
    *,
    now: datetime,
) -> int:
    line_ids = sorted({int(o.evidence_line_id) for o in observations if o.evidence_line_id is not None})
    if not line_ids:
        return 0
    lines = list(db.scalars(select(ShipmentEvidenceLine).where(ShipmentEvidenceLine.id.in_(line_ids))).all())
    touched = 0
    for line in lines:
        if line.corpus_superseded_at is None:
            line.corpus_superseded_at = now
            touched += 1
    return touched


def apply_lineage_graduation(
    db: Session,
    verdict: LineageGraduationVerdict,
    blank: list[ShipmentEvidenceObservation],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply full supersession or partial steward flag for one lineage."""
    if verdict.outcome in ("none", "already_done"):
        return {"outcome": verdict.outcome, "lineage": verdict.lineage}

    now = datetime.now(timezone.utc)
    current = load_unsuperseded_current_observations(db)
    lineage = verdict.lineage
    active_blank = [
        o
        for o in current
        if lineage_key_from_obs(o) == lineage
        and is_blank_invoice_shipped_obs(o)
        and o.superseded_by_id is None
        and not has_partial_graduation_flag(o)
    ]

    if verdict.outcome == "partial":
        flagged = 0
        if not dry_run:
            for obs in active_blank:
                if _set_steward_flag(obs, STEWARD_FLAG_PARTIAL):
                    flagged += 1
            db.flush()
        return {
            "outcome": "partial",
            "lineage": verdict.lineage,
            "blank_qty": verdict.blank_qty,
            "numbered_qty": verdict.numbered_qty,
            "flags_set": flagged if not dry_run else len(active_blank),
        }

    if verdict.outcome != "full" or not active_blank:
        return {"outcome": "none", "lineage": verdict.lineage}

    numbered_current = [
        o
        for o in current
        if lineage_key_from_obs(o) == lineage and is_numbered_invoice_shipped_obs(o)
    ]
    anchor_id = verdict.anchor_observation_id
    if anchor_id is None and numbered_current:
        anchor_id = int(sorted(numbered_current, key=lambda o: (o.valid_from, o.id), reverse=True)[0].id)
    if anchor_id is None:
        return {"outcome": "none", "lineage": verdict.lineage}

    blank_keys = sorted({o.line_identity_key for o in active_blank if o.line_identity_key})
    if not blank_keys:
        blank_keys = list(verdict.blank_keys)

    if dry_run:
        to_supersede = active_blank
    else:
        to_supersede = load_unsuperseded_observations_for_keys(db, blank_keys)

    superseded = 0
    if not dry_run:
        for obs in to_supersede:
            if obs.superseded_by_id is not None:
                continue
            obs.superseded_by_id = int(anchor_id)
            superseded += 1
        _mark_evidence_lines_superseded(db, to_supersede, now=now)
        db.flush()

    return {
        "outcome": "full",
        "lineage": verdict.lineage,
        "blank_qty": verdict.blank_qty,
        "numbered_qty": verdict.numbered_qty,
        "superseded_observations": superseded if not dry_run else len(to_supersede),
        "blank_identity_keys": blank_keys,
        "anchor_observation_id": anchor_id,
        "numbered_keys": verdict.numbered_keys,
    }


def process_lineages_for_graduation(
    db: Session,
    lineages: set[LineageKey],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    if not lineages:
        return []
    current = load_unsuperseded_current_observations(db)
    grouped = group_current_by_lineage(current)
    results: list[dict[str, Any]] = []
    for lk in lineages:
        bucket = grouped.get(lk, {"blank": [], "numbered": []})
        verdict = evaluate_lineage_graduation(bucket["blank"], bucket["numbered"])
        if verdict.outcome == "none":
            continue
        results.append(apply_lineage_graduation(db, verdict, bucket["blank"], dry_run=dry_run))
    return results


def process_invoice_graduation_after_job(db: Session, job: ImportJob) -> dict[str, Any]:
    """Run quantity-gated graduation for lineages touched by new numbered-invoice rows."""
    job_id = int(job.id)
    numbered = list(
        db.scalars(
            select(ShipmentEvidenceObservation).where(
                ShipmentEvidenceObservation.import_job_id == job_id,
            )
        ).all()
    )
    numbered = [o for o in numbered if is_numbered_invoice_shipped_obs(o)]
    lineages = {lk for o in numbered if (lk := lineage_key_from_obs(o)) is not None}
    if not lineages:
        return {"job_id": job_id, "lineages_touched": 0, "actions": []}

    actions = process_lineages_for_graduation(db, lineages, dry_run=False)
    return {"job_id": job_id, "lineages_touched": len(lineages), "actions": actions}


def discover_invoice_graduation_lineages(db: Session) -> list[LineageGraduationVerdict]:
    """All current lineages with both blank-invoice order-grain and numbered ship-grain shipped obs."""
    current = load_unsuperseded_current_observations(db)
    grouped = group_current_by_lineage(current)
    verdicts: list[LineageGraduationVerdict] = []
    for lk, bucket in grouped.items():
        if not bucket["blank"] or not bucket["numbered"]:
            continue
        verdicts.append(evaluate_lineage_graduation(bucket["blank"], bucket["numbered"]))
    return verdicts


def repair_all_invoice_graduations(db: Session, *, dry_run: bool = False, admin_engine=None) -> dict[str, Any]:
    """One-time repair: graduate or flag all eligible lineages; refresh current view when applying."""
    verdicts = discover_invoice_graduation_lineages(db)
    current = load_unsuperseded_current_observations(db)
    grouped = group_current_by_lineage(current)

    before_view_count = int(db.scalar(text("SELECT count(*) FROM shipment_evidence_current")) or 0)

    actions: list[dict[str, Any]] = []
    for v in verdicts:
        bucket = grouped.get(v.lineage, {"blank": [], "numbered": []})
        if v.outcome in ("full", "partial"):
            actions.append(apply_lineage_graduation(db, v, bucket["blank"], dry_run=dry_run))

    if not dry_run:
        refresh_shipment_evidence_current_view(db, admin_engine=admin_engine)
        db.flush()

    after_view_count = (
        int(db.scalar(text("SELECT count(*) FROM shipment_evidence_current")) or 0) if not dry_run else before_view_count
    )

    full = sum(1 for a in actions if a.get("outcome") == "full")
    partial = sum(1 for a in actions if a.get("outcome") == "partial")
    graduated_keys = len(
        {
            k
            for a in actions
            if a.get("outcome") == "full"
            for k in (a.get("blank_identity_keys") or [])
        }
    )
    superseded_obs = sum(int(a.get("superseded_observations") or 0) for a in actions if a.get("outcome") == "full")

    return {
        "dry_run": dry_run,
        "lineages_scanned": len(verdicts),
        "full_graduation": full,
        "partial_flagged": partial,
        "actions": actions,
        "view_rows_before": before_view_count,
        "view_rows_after": after_view_count,
        "view_row_drop": before_view_count - after_view_count if not dry_run else None,
        "expected_view_drop": graduated_keys,
        "superseded_observation_rows": superseded_obs,
    }


def preview_invoice_line_graduation(db: Session) -> dict[str, Any]:
    """Read-only report: parity split, per-lineage detail, double-count by period × customer."""
    from app.models.dimensions import DimCustomer
    from app.services.commercial_planner.lineup_period_canonical import quarter_key_from_period_start

    verdicts = discover_invoice_graduation_lineages(db)
    current = load_unsuperseded_current_observations(db)
    grouped = group_current_by_lineage(current)

    full = [v for v in verdicts if v.outcome == "full"]
    partial = [v for v in verdicts if v.outcome == "partial"]
    already = [v for v in verdicts if v.outcome == "already_done"]

    details: list[dict[str, Any]] = []
    period_customer_units: dict[tuple[str, int | None], float] = defaultdict(float)

    for v in verdicts:
        bucket = grouped.get(v.lineage, {"blank": [], "numbered": []})
        blank_obs = bucket.get("blank") or []
        sample = blank_obs[0] if blank_obs else (bucket.get("numbered") or [None])[0]
        cust_id = int(sample.customer_id) if sample and sample.customer_id is not None else None
        period_label = None
        if sample and sample.erd_date:
            period_label = quarter_key_from_period_start(sample.erd_date.replace(day=1))
        elif sample:
            period_label = quarter_key_from_period_start(sample.valid_from.date())

        double_units = max(0.0, v.blank_qty) if v.outcome in ("full", "partial") else 0.0
        if period_label and double_units > 0:
            period_customer_units[(period_label, cust_id)] += double_units

        ou, on, ol, ic = v.lineage
        details.append(
            {
                "lineage": {"operating_unit": ou or None, "order_no": on, "order_line": ol, "item_code": ic},
                "blank_identity_keys": v.blank_keys,
                "numbered_identity_keys": v.numbered_keys,
                "blank_qty": v.blank_qty,
                "numbered_qty": v.numbered_qty,
                "verdict": v.outcome,
                "customer_id": cust_id,
                "period_label": period_label,
                "double_count_units": double_units,
            }
        )

    cust_ids = sorted({cid for (_p, cid) in period_customer_units if cid is not None})
    cust_names: dict[int, str] = {}
    if cust_ids:
        for cid, name in db.execute(
            select(DimCustomer.id, DimCustomer.name).where(DimCustomer.id.in_(cust_ids))
        ).all():
            cust_names[int(cid)] = str(name)

    recon_impact = [
        {
            "period_label": p,
            "customer_id": cid,
            "customer_name": cust_names.get(int(cid)) if cid is not None else None,
            "double_count_units": round(units, 4),
        }
        for (p, cid), units in sorted(period_customer_units.items(), key=lambda x: -x[1])
    ]

    return {
        "lineages_total": len(verdicts),
        "full_graduation": len(full),
        "partial_graduation": len(partial),
        "already_superseded": len(already),
        "lineage_details": details,
        "reconciliation_double_count_by_period_customer": recon_impact,
        "total_double_count_units": round(sum(period_customer_units.values()), 4),
    }


def count_ungraduated_invoice_lineage_gaps(db: Session) -> tuple[int, int]:
    """Return (pending full-graduation lineages, partial steward worklist count)."""
    verdicts = discover_invoice_graduation_lineages(db)
    gaps = sum(1 for v in verdicts if v.outcome == "full")
    partials = sum(1 for v in verdicts if v.outcome == "partial")
    return gaps, partials
