"""Read-only PO↔lineup link and shipment fact/evidence integrity audit.

Designed to re-run after any import, link session, or merge — no writes, no unlinking,
no dedup. Invoke:

  cd apps/api && PYTHONPATH=. python scripts/ops/run_data_integrity_audit.py
  cd apps/api && PYTHONPATH=. python scripts/ops/run_data_integrity_audit.py --period 26Q2
  cd apps/api && PYTHONPATH=. python scripts/ops/run_data_integrity_audit.py --json-out audit.json

Requires ``current_database()`` in ``cip`` / ``postgres`` (see ``cip_db_identity``).

Shipment evidence domain contract (audit enforces):
- **Shipped / POD path** (delivery-backed rows): one corpus row per
  ``(delivery_no, item_code, purchase_order_id, invoice_line)``. Re-import within a job
  upserts on ``(import_job_id, source_key)``; date/qty changes override — they must not
  leave a second row for the same invoice line. Cross-job copies of the same invoice line
  are **violations** (they inflate sums and break intelligence).
- **Invoice-line splits** (same delivery+item+PO, different ``invoice_line``) are expected;
  they sum into one shipped fact — never flagged as 5b dupes.
- **Open-order / unship** pipeline rows use order keys — excluded from shipped duplicate
  checks (separate report family).
- **Fact parity (6)** compares ``fact_inbound_shipment`` to **canonical** evidence: latest
  job wins per invoice-line key, then sum across splits. Raw multi-job duplicate inflation
  is reported separately when ``raw_sum > canonical_sum``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupCasePo, CommercialLineupLine
from app.models.dimensions import DimCustomer
from app.models.facts import FactInboundShipment
from app.services.imports.shipment_evidence_read import (
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)
from app.core.feature_flags import shipment_bitemporal_read_enabled
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    parse_period_filter_to_year_quarter,
    quarter_from_period_start,
)
from app.services.commercial_planner.lineup_po_auto_link import (
    classify_customer_alignment,
    classify_match_confidence,
    evidence_date_for_period_match,
    date_in_case_period,
)
from app.services.imports.shipment_evidence_line_identity import stable_shipped_fact_upsert_key_from_fields

CheckName = Literal[
    "link_drift",
    "superseded_link",
    "cross_quarter_po",
    "customer_mismatch",
    "fact_key_dupes",
    "evidence_true_dupes",
    "evidence_fact_parity",
    "cross_job_double_book",
    "lineup_duplicate_ingestion",
]

QTY_EPS = 1e-6

# Shipped/POD extract report types (delivery + invoice line identity).
SHIPPED_EVIDENCE_REPORT_TYPES = frozenset(
    {
        "acza_workbook_shipped",
        "xxomrpt0025_shipment",
    }
)
# Pipeline / delay intelligence — separate identity namespace; not mixed into 5b.
OPEN_ORDER_EVIDENCE_REPORT_TYPES = frozenset(
    {
        "acza_workbook_unship",
        "xxomrpt0027_order",
    }
)


@dataclass
class CheckResult:
    check: CheckName
    count: int
    samples: list[dict[str, Any]] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuditReport:
    database: str
    filters: dict[str, Any]
    checks: list[CheckResult]
    generated_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "database": self.database,
            "filters": self.filters,
            "generated_at": self.generated_at,
            "checks": [
                {
                    "check": c.check,
                    "count": c.count,
                    "samples": c.samples,
                    "meta": c.meta,
                }
                for c in self.checks
            ],
        }


def _norm_seg(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _is_shipped_delivery_evidence(line: Any) -> bool:
    """Shipped POD-path rows: delivery + invoice line + item (excludes open-order pipeline)."""
    if (line.line_state or "").strip().lower() != "shipped":
        return False
    rt = (line.report_type or "").strip().lower()
    if rt in OPEN_ORDER_EVIDENCE_REPORT_TYPES:
        return False
    if rt in SHIPPED_EVIDENCE_REPORT_TYPES:
        return True
    # Legacy rows: shipped line_state with delivery invoice identity.
    return bool(
        _norm_seg(line.delivery_no)
        and _norm_seg(line.invoice_line)
        and _norm_seg(line.item_code)
    )


def _load_shipped_evidence_for_audit(db: Session) -> list[Any]:
    """Active shipped corpus rows: current-state view when Plan D read is on, else non-superseded lines."""
    EV = shipment_evidence_read_model()
    stmt = apply_active_evidence_filter(select(EV), EV)
    rows = list(db.execute(stmt).scalars().all())
    return [ln for ln in rows if _is_shipped_delivery_evidence(ln)]


def _latest_per_invoice_key(lines: list[Any]) -> list[Any]:
    """Canonical evidence view: latest import job wins per invoice-line business key."""
    best: dict[tuple[str, str, str, str], Any] = {}
    for ln in lines:
        key = _evidence_invoice_key(
            delivery_no=ln.delivery_no,
            item_code=ln.item_code,
            purchase_order_id=ln.purchase_order_id,
            invoice_line=ln.invoice_line,
        )
        if key is None:
            continue
        cur = best.get(key)
        if cur is None or (int(ln.import_job_id), int(ln.id)) > (int(cur.import_job_id), int(cur.id)):
            best[key] = ln
    return list(best.values())


def _build_customer_redirect_map(db: Session) -> dict[int, int]:
    """Map each customer id to its merge-chain terminal (follow ``merged_into_customer_id``)."""
    rows = db.execute(select(DimCustomer.id, DimCustomer.merged_into_customer_id)).all()
    parent: dict[int, int | None] = {int(r[0]): int(r[1]) if r[1] is not None else None for r in rows}

    def terminal(cid: int | None) -> int | None:
        if cid is None:
            return None
        seen: set[int] = set()
        cur = int(cid)
        while cur in parent and parent[cur] is not None:
            if cur in seen:
                break
            seen.add(cur)
            cur = int(parent[cur])  # type: ignore[arg-type]
        return cur

    return {cid: int(terminal(cid) or cid) for cid in parent}


def _redirect(cid: int | None, redirect_map: dict[int, int]) -> int | None:
    if cid is None:
        return None
    return redirect_map.get(int(cid), int(cid))


def _shipped_group_key(
    *,
    delivery_no: Any,
    item_code: Any,
    purchase_order_id: Any,
    operating_unit: Any = None,
) -> str | None:
    return stable_shipped_fact_upsert_key_from_fields(
        operating_unit=operating_unit,
        delivery_no=delivery_no,
        item_code=item_code,
        purchase_order_id=purchase_order_id,
    )


def _evidence_invoice_key(
    *,
    delivery_no: Any,
    item_code: Any,
    purchase_order_id: Any,
    invoice_line: Any,
) -> tuple[str, str, str, str] | None:
    d, i, p, inv = (
        _norm_seg(delivery_no),
        _norm_seg(item_code),
        _norm_seg(purchase_order_id),
        _norm_seg(invoice_line),
    )
    if not d or not i or not p or not inv:
        return None
    return d, i, p, inv


def _shipment_in_period_filter(ship: FactInboundShipment, period: str | None) -> bool:
    if not period:
        return True
    filt_year, filt_q = parse_period_filter_to_year_quarter(period)
    if filt_year is None and filt_q is None:
        return True
    ev_date, _ = evidence_date_for_period_match(
        crad_date=ship.crad_date,
        schedule_ship_date=ship.schedule_ship_date,
        ship_confirm_date=ship.ship_confirm_date,
    )
    if ev_date is None:
        return False
    sy, sq = quarter_from_period_start(ev_date)
    if filt_year is not None and sy != filt_year:
        return False
    if filt_q is not None and sq != filt_q:
        return False
    return True


def _case_in_period_filter(case: CommercialLineupCase, period: str | None) -> bool:
    if not period or case.inferred_period_start is None:
        return True
    filt_year, filt_q = parse_period_filter_to_year_quarter(period)
    if filt_year is None and filt_q is None:
        return True
    cy, cq = quarter_from_period_start(case.inferred_period_start)
    if filt_year is not None and cy != filt_year:
        return False
    if filt_q is not None and cq != filt_q:
        return False
    return True


def _fact_key_constraint_status(db: Session) -> dict[str, Any]:
    row = db.execute(
        text(
            """
            SELECT c.conname, c.contype
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            WHERE t.relname = 'fact_inbound_shipment'
              AND c.contype = 'u'
              AND pg_get_constraintdef(c.oid) LIKE '%fact_upsert_key%'
            """
        )
    ).first()
    if row:
        return {"enforced": True, "constraint_name": row[0], "type": row[1]}
    idx = db.execute(
        text(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'fact_inbound_shipment'
              AND indexdef ILIKE '%fact_upsert_key%'
              AND indexdef ILIKE '%unique%'
            LIMIT 1
            """
        )
    ).first()
    if idx:
        return {"enforced": True, "constraint_name": idx[0], "type": "unique_index"}
    return {
        "enforced": False,
        "application_only": True,
        "detail": "No UNIQUE constraint/index on fact_upsert_key — enforcement is application-only",
    }


def _link_still_derives_confidence(
    *,
    case: CommercialLineupCase,
    shipments: list[FactInboundShipment],
    lineup_by_product: dict[int, list[CommercialLineupLine]],
    redirect_map: dict[int, int],
) -> list[str]:
    """Return failing predicates when link no longer re-derives auto-link confidence."""
    if not shipments:
        return ["no_shipment_facts"]

    failures: set[str] = set()
    any_qualifying = False

    for ship in shipments:
        if ship.product_id is None:
            failures.add("shipment_missing_product_id")
            continue
        pid = int(ship.product_id)
        case_lines = lineup_by_product.get(pid, [])
        if not case_lines:
            failures.add("no_product_on_case")
            continue

        ev_date, date_src = evidence_date_for_period_match(
            crad_date=ship.crad_date,
            schedule_ship_date=ship.schedule_ship_date,
            ship_confirm_date=ship.ship_confirm_date,
        )
        in_period = date_in_case_period(ev_date, case.inferred_period_start)
        if not in_period:
            failures.add("not_in_period")
        if date_src == "none":
            failures.add("no_evidence_date")

        ship_cust = _redirect(
            int(ship.resolved_customer_id) if ship.resolved_customer_id is not None else None,
            redirect_map,
        )
        for ln in case_lines:
            lineup_cust = _redirect(
                int(ln.customer_id) if ln.customer_id is not None else None,
                redirect_map,
            )
            align = classify_customer_alignment(ship_cust, lineup_cust)
            if align == "mismatch":
                failures.add("customer_mismatch")
            conf, _reason = classify_match_confidence(
                customer_align=align,
                date_source=date_src,
                in_period=in_period,
            )
            if conf is not None and in_period and date_src != "none":
                any_qualifying = True

    if any_qualifying:
        return []
    return sorted(failures) or ["no_qualifying_match"]


def check_link_drift(
    db: Session,
    *,
    period: str | None,
    distributor_id: int | None,
    sample_limit: int,
    redirect_map: dict[int, int],
) -> CheckResult:
    links = db.execute(select(CommercialLineupCasePo)).scalars().all()
    cases = {int(c.id): c for c in db.execute(select(CommercialLineupCase)).scalars().all()}
    lineup_rows = db.execute(
        select(CommercialLineupLine).where(CommercialLineupLine.product_id.isnot(None))
    ).scalars().all()
    lineup_by_case_product: dict[int, dict[int, list[CommercialLineupLine]]] = {}
    for ln in lineup_rows:
        lineup_by_case_product.setdefault(int(ln.case_id), {}).setdefault(int(ln.product_id), []).append(ln)  # type: ignore[arg-type]

    ship_rows = db.execute(
        select(FactInboundShipment).where(FactInboundShipment.purchase_order_id.isnot(None))
    ).scalars().all()
    ships_by_po: dict[int, list[FactInboundShipment]] = {}
    for s in ship_rows:
        if distributor_id is not None:
            if s.resolved_distributor_id is None or int(s.resolved_distributor_id) != distributor_id:
                continue
        if period and not _shipment_in_period_filter(s, period):
            continue
        ships_by_po.setdefault(int(s.purchase_order_id), []).append(s)  # type: ignore[arg-type]

    findings: list[dict[str, Any]] = []
    for link in links:
        case = cases.get(int(link.case_id))
        if case is None:
            continue
        if period and not _case_in_period_filter(case, period):
            continue
        po_id = int(link.purchase_order_id)
        failures = _link_still_derives_confidence(
            case=case,
            shipments=ships_by_po.get(po_id, []),
            lineup_by_product=lineup_by_case_product.get(int(case.id), {}),
            redirect_map=redirect_map,
        )
        if failures:
            findings.append(
                {
                    "case_id": int(case.id),
                    "purchase_order_id": po_id,
                    "failed_predicates": failures,
                    "case_period_start": case.inferred_period_start.isoformat()
                    if case.inferred_period_start
                    else None,
                }
            )

    return CheckResult(
        check="link_drift",
        count=len(findings),
        samples=findings[:sample_limit],
    )


def check_superseded_link(db: Session, *, period: str | None, sample_limit: int) -> CheckResult:
    rows = db.execute(
        select(
            CommercialLineupCasePo.case_id,
            CommercialLineupCasePo.purchase_order_id,
            CommercialLineupCase.superseded_by_case_id,
            CommercialLineupCase.commercial_status,
        )
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
        .where(
            (CommercialLineupCase.superseded_by_case_id.isnot(None))
            | (CommercialLineupCase.commercial_status == "superseded")
        )
    ).all()
    findings = []
    for case_id, po_id, sup_id, status in rows:
        case = db.get(CommercialLineupCase, int(case_id))
        if period and case and not _case_in_period_filter(case, period):
            continue
        findings.append(
            {
                "case_id": int(case_id),
                "purchase_order_id": int(po_id),
                "superseded_by_case_id": int(sup_id) if sup_id is not None else None,
                "commercial_status": status,
            }
        )
    return CheckResult(check="superseded_link", count=len(findings), samples=findings[:sample_limit])


def check_cross_quarter_po(db: Session, *, period: str | None, sample_limit: int) -> CheckResult:
    rows = db.execute(
        select(
            CommercialLineupCasePo.purchase_order_id,
            CommercialLineupCase.inferred_period_start,
            CommercialLineupCasePo.case_id,
        )
        .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupCasePo.case_id)
        .where(CommercialLineupCase.inferred_period_start.isnot(None))
    ).all()
    by_po: dict[int, dict[tuple[int, int], list[int]]] = {}
    for po_id, ps, case_id in rows:
        if ps is None:
            continue
        y, q = quarter_from_period_start(ps)
        if period:
            fy, fq = parse_period_filter_to_year_quarter(period)
            if fy is not None and y != fy:
                continue
            if fq is not None and q != fq:
                continue
        by_po.setdefault(int(po_id), {}).setdefault((y, q), []).append(int(case_id))

    findings = []
    for po_id, quarters in by_po.items():
        if len(quarters) < 2:
            continue
        findings.append(
            {
                "purchase_order_id": po_id,
                "quarters": [
                    {"year": y, "quarter": q, "case_ids": cids} for (y, q), cids in sorted(quarters.items())
                ],
            }
        )
    return CheckResult(check="cross_quarter_po", count=len(findings), samples=findings[:sample_limit])


def check_customer_mismatch(
    db: Session,
    *,
    period: str | None,
    distributor_id: int | None,
    sample_limit: int,
    redirect_map: dict[int, int],
) -> CheckResult:
    links = db.execute(select(CommercialLineupCasePo)).scalars().all()
    cases = {int(c.id): c for c in db.execute(select(CommercialLineupCase)).scalars().all()}
    lineup_rows = db.execute(select(CommercialLineupLine)).scalars().all()
    lines_by_case: dict[int, list[CommercialLineupLine]] = {}
    for ln in lineup_rows:
        lines_by_case.setdefault(int(ln.case_id), []).append(ln)

    ship_rows = db.execute(
        select(FactInboundShipment).where(FactInboundShipment.purchase_order_id.isnot(None))
    ).scalars().all()
    ships_by_po: dict[int, list[FactInboundShipment]] = {}
    for s in ship_rows:
        if distributor_id is not None:
            if s.resolved_distributor_id is None or int(s.resolved_distributor_id) != distributor_id:
                continue
        if period and not _shipment_in_period_filter(s, period):
            continue
        ships_by_po.setdefault(int(s.purchase_order_id), []).append(s)  # type: ignore[arg-type]

    findings: list[dict[str, Any]] = []
    for link in links:
        case = cases.get(int(link.case_id))
        if case is None:
            continue
        if period and not _case_in_period_filter(case, period):
            continue
        po_id = int(link.purchase_order_id)
        case_lines = lines_by_case.get(int(case.id), [])
        for ship in ships_by_po.get(po_id, []):
            if ship.product_id is None or ship.resolved_customer_id is None:
                continue
            ship_cust = _redirect(int(ship.resolved_customer_id), redirect_map)
            for ln in case_lines:
                if ln.customer_id is None:
                    continue
                if ln.product_id is not None and int(ln.product_id) != int(ship.product_id):
                    continue
                line_cust = _redirect(int(ln.customer_id), redirect_map)
                if ship_cust != line_cust:
                    findings.append(
                        {
                            "case_id": int(case.id),
                            "purchase_order_id": po_id,
                            "shipment_fact_id": int(ship.id),
                            "lineup_line_id": int(ln.id),
                            "resolved_customer_id": int(ship.resolved_customer_id),
                            "lineup_customer_id": int(ln.customer_id),
                            "resolved_after_redirect": ship_cust,
                            "lineup_after_redirect": line_cust,
                        }
                    )
                    break
            else:
                continue
            break

    return CheckResult(check="customer_mismatch", count=len(findings), samples=findings[:sample_limit])


def check_fact_key_dupes(db: Session, *, sample_limit: int) -> CheckResult:
    constraint = _fact_key_constraint_status(db)
    rows = db.execute(
        select(FactInboundShipment.fact_upsert_key, func.count())
        .where(
            func.lower(FactInboundShipment.line_state) == "shipped",
            FactInboundShipment.fact_upsert_key.isnot(None),
        )
        .group_by(FactInboundShipment.fact_upsert_key)
        .having(func.count() > 1)
    ).all()
    samples = [
        {
            "fact_upsert_key": key,
            "row_count": int(cnt),
            "fact_ids": [
                int(x)
                for x in db.scalars(
                    select(FactInboundShipment.id)
                    .where(FactInboundShipment.fact_upsert_key == key)
                    .order_by(FactInboundShipment.id)
                    .limit(5)
                ).all()
            ],
        }
        for key, cnt in rows[:sample_limit]
    ]
    count = len(rows)
    meta = {"fact_upsert_key_unique_constraint": constraint}
    if not constraint.get("enforced"):
        meta["application_only_enforcement"] = True
    return CheckResult(check="fact_key_dupes", count=count, samples=samples, meta=meta)


def collect_evidence_true_dupes(db: Session) -> list[dict[str, Any]]:
    """Corpus duplicate shipped invoice lines — must not exist (one row per business key)."""
    rows = _load_shipped_evidence_for_audit(db)
    buckets: dict[tuple[str, str, str, str], list[Any]] = {}
    for ln in rows:
        if not _is_shipped_delivery_evidence(ln):
            continue
        key = _evidence_invoice_key(
            delivery_no=ln.delivery_no,
            item_code=ln.item_code,
            purchase_order_id=ln.purchase_order_id,
            invoice_line=ln.invoice_line,
        )
        if key is None:
            continue
        buckets.setdefault(key, []).append(ln)

    findings: list[dict[str, Any]] = []
    for k, lines in buckets.items():
        if len(lines) < 2:
            continue
        job_ids = sorted({int(ln.import_job_id) for ln in lines})
        findings.append(
            {
                "delivery_no": k[0],
                "item_code": k[1],
                "purchase_order_id": k[2],
                "invoice_line": k[3],
                "duplicate_row_count": len(lines),
                "import_job_ids": job_ids,
                "cross_job_duplicate": len(job_ids) > 1,
                "evidence_line_ids": [int(ln.id) for ln in lines[:20]],
                "source_keys": sorted({_norm_seg(ln.source_key) for ln in lines})[:10],
                "violation": "corpus_duplicate_shipped_invoice_line",
            }
        )
    return findings


def check_evidence_true_dupes(db: Session, *, sample_limit: int) -> CheckResult:
    findings = collect_evidence_true_dupes(db)
    cross_job = sum(1 for f in findings if f.get("cross_job_duplicate"))
    return CheckResult(
        check="evidence_true_dupes",
        count=len(findings),
        samples=findings[:sample_limit],
        meta={
            "domain_rule": "one shipped invoice line per corpus; within-job upsert only",
            "cross_job_duplicate_groups": cross_job,
            "read_source": "shipment_evidence_current"
            if shipment_bitemporal_read_enabled()
            else "shipment_evidence_line_active",
        },
    )


def collect_evidence_fact_parity(db: Session) -> list[dict[str, Any]]:
    evidence_rows = _load_shipped_evidence_for_audit(db)
    group_evidence: dict[str, list[Any]] = {}
    for ln in evidence_rows:
        gkey = _shipped_group_key(
            operating_unit=ln.operating_unit,
            delivery_no=ln.delivery_no,
            item_code=ln.item_code,
            purchase_order_id=ln.purchase_order_id,
        )
        if not gkey:
            continue
        group_evidence.setdefault(gkey, []).append(ln)

    facts = {
        str(f.fact_upsert_key): f
        for f in db.execute(
            select(FactInboundShipment).where(
                func.lower(FactInboundShipment.line_state) == "shipped",
                FactInboundShipment.fact_upsert_key.isnot(None),
            )
        ).scalars().all()
    }

    findings: list[dict[str, Any]] = []
    for gkey, lines in group_evidence.items():
        if shipment_bitemporal_read_enabled():
            canonical_lines = lines
            raw_sum = sum(float(ln.quantity or 0) for ln in lines)
            canonical_sum = raw_sum
        else:
            canonical_lines = _latest_per_invoice_key(lines)
            raw_sum = sum(float(ln.quantity or 0) for ln in lines)
            canonical_sum = sum(float(ln.quantity or 0) for ln in canonical_lines)
        if canonical_sum <= QTY_EPS and raw_sum <= QTY_EPS:
            continue

        fact = facts.get(gkey)
        inflation = max(0.0, raw_sum - canonical_sum)

        if fact is None:
            findings.append(
                {
                    "fact_upsert_key": gkey,
                    "issue": "missing_fact_row",
                    "canonical_evidence_qty_sum": canonical_sum,
                    "raw_evidence_qty_sum": raw_sum,
                    "duplicate_qty_inflation": inflation,
                    "evidence_line_count_raw": len(lines),
                    "evidence_line_count_canonical": len(canonical_lines),
                    "invoice_lines": sorted({_norm_seg(ln.invoice_line) for ln in canonical_lines}),
                }
            )
            continue

        fact_qty = float(fact.quantity or 0)
        if inflation > QTY_EPS:
            findings.append(
                {
                    "fact_upsert_key": gkey,
                    "fact_id": int(fact.id),
                    "issue": "duplicate_qty_inflation",
                    "fact_qty": fact_qty,
                    "canonical_evidence_qty_sum": canonical_sum,
                    "raw_evidence_qty_sum": raw_sum,
                    "duplicate_qty_inflation": inflation,
                    "evidence_line_count_raw": len(lines),
                    "evidence_line_count_canonical": len(canonical_lines),
                }
            )
        if abs(fact_qty - canonical_sum) > QTY_EPS:
            invoice_lines = sorted({_norm_seg(ln.invoice_line) for ln in canonical_lines})
            single_line_undercount = len(canonical_lines) > 1 and any(
                abs(fact_qty - float(ln.quantity or 0)) <= QTY_EPS for ln in canonical_lines
            )
            findings.append(
                {
                    "fact_upsert_key": gkey,
                    "fact_id": int(fact.id),
                    "issue": "single_line_undercount" if single_line_undercount else "fact_qty_mismatch",
                    "fact_qty": fact_qty,
                    "canonical_evidence_qty_sum": canonical_sum,
                    "raw_evidence_qty_sum": raw_sum,
                    "duplicate_qty_inflation": inflation,
                    "evidence_line_count_raw": len(lines),
                    "evidence_line_count_canonical": len(canonical_lines),
                    "invoice_lines": invoice_lines,
                }
            )
    return findings


def check_evidence_fact_parity(db: Session, *, sample_limit: int) -> CheckResult:
    findings = collect_evidence_fact_parity(db)
    inflation_groups = sum(1 for f in findings if f.get("issue") == "duplicate_qty_inflation")
    return CheckResult(
        check="evidence_fact_parity",
        count=len(findings),
        samples=findings[:sample_limit],
        meta={
            "parity_basis": "shipment_evidence_current_per_line_identity"
            if shipment_bitemporal_read_enabled()
            else "canonical_evidence_latest_job_per_invoice_line",
            "duplicate_qty_inflation_groups": inflation_groups,
        },
    )


def check_cross_job_double_book(db: Session, *, sample_limit: int) -> CheckResult:
    rows = db.execute(
        select(
            FactInboundShipment.fact_upsert_key,
            func.count(func.distinct(FactInboundShipment.import_job_id)),
            func.array_agg(func.distinct(FactInboundShipment.import_job_id)),
        )
        .where(
            func.lower(FactInboundShipment.line_state) == "shipped",
            FactInboundShipment.fact_upsert_key.isnot(None),
            FactInboundShipment.import_job_id.isnot(None),
        )
        .group_by(FactInboundShipment.fact_upsert_key)
        .having(func.count(func.distinct(FactInboundShipment.import_job_id)) > 1)
    ).all()

    findings = [
        {
            "fact_upsert_key": key,
            "import_job_ids": sorted(int(x) for x in (job_ids or []) if x is not None),
            "fact_row_count": int(
                db.scalar(
                    select(func.count()).where(
                        FactInboundShipment.fact_upsert_key == key,
                        func.lower(FactInboundShipment.line_state) == "shipped",
                    )
                )
                or 0
            ),
        }
        for key, _nj, job_ids in rows
    ]
    return CheckResult(
        check="cross_job_double_book",
        count=len(findings),
        samples=findings[:sample_limit],
    )


def _lineup_line_fingerprint(lines: list[CommercialLineupLine]) -> frozenset[tuple[int, int, float]]:
    out: set[tuple[int, int, float]] = set()
    for ln in lines:
        qty = float(ln.quantity_units or 0)
        out.add((int(ln.source_row_number or 0), int(ln.product_id or 0), qty))
    return frozenset(out)


def check_lineup_duplicate_ingestion(db: Session, *, sample_limit: int) -> CheckResult:
    """Active cases sharing file+period with identical line fingerprints → duplicate ingestion."""
    cases = db.execute(
        select(CommercialLineupCase).where(*active_lineup_case_filters()).order_by(CommercialLineupCase.id)
    ).scalars().all()
    if not cases:
        return CheckResult(check="lineup_duplicate_ingestion", count=0)

    case_ids = [int(c.id) for c in cases]
    lines = db.execute(
        select(CommercialLineupLine).where(CommercialLineupLine.case_id.in_(case_ids))
    ).scalars().all()
    lines_by_case: dict[int, list[CommercialLineupLine]] = {}
    for ln in lines:
        lines_by_case.setdefault(int(ln.case_id), []).append(ln)

    by_file_period: dict[tuple[str, date | None], list[CommercialLineupCase]] = {}
    for case in cases:
        key = (str(case.file_name or ""), case.inferred_period_start)
        by_file_period.setdefault(key, []).append(case)

    findings: list[dict[str, Any]] = []
    reported_clusters: set[frozenset[int]] = set()

    for (file_name, period_start), bucket in by_file_period.items():
        if len(bucket) < 2:
            continue
        fp_clusters: dict[tuple[int, frozenset], list[CommercialLineupCase]] = {}
        for case in bucket:
            case_lines = lines_by_case.get(int(case.id), [])
            fp = _lineup_line_fingerprint(case_lines)
            cluster_key = (len(case_lines), fp)
            fp_clusters.setdefault(cluster_key, []).append(case)
        for (line_count, fp), members in fp_clusters.items():
            if len(members) < 2 or line_count == 0:
                continue
            cluster_ids = frozenset(int(c.id) for c in members)
            if cluster_ids in reported_clusters:
                continue
            reported_clusters.add(cluster_ids)
            findings.append(
                {
                    "file_name": file_name,
                    "inferred_period_start": period_start.isoformat() if period_start else None,
                    "line_count": line_count,
                    "case_ids": sorted(cluster_ids),
                    "business_units": sorted({c.business_unit for c in members if c.business_unit}),
                }
            )

    return CheckResult(
        check="lineup_duplicate_ingestion",
        count=len(findings),
        samples=findings[:sample_limit],
    )


def run_data_integrity_audit_sync(
    db: Session,
    *,
    period: str | None = None,
    distributor_id: int | None = None,
    sample_limit: int = 10,
) -> AuditReport:
    from datetime import datetime, timezone

    dbname = str(db.scalar(text("SELECT current_database()")) or "")
    redirect_map = _build_customer_redirect_map(db)
    filters = {
        "period": period,
        "distributor_id": distributor_id,
        "sample_limit": sample_limit,
    }
    checks = [
        check_link_drift(
            db,
            period=period,
            distributor_id=distributor_id,
            sample_limit=sample_limit,
            redirect_map=redirect_map,
        ),
        check_superseded_link(db, period=period, sample_limit=sample_limit),
        check_cross_quarter_po(db, period=period, sample_limit=sample_limit),
        check_customer_mismatch(
            db,
            period=period,
            distributor_id=distributor_id,
            sample_limit=sample_limit,
            redirect_map=redirect_map,
        ),
        check_fact_key_dupes(db, sample_limit=sample_limit),
        check_evidence_true_dupes(db, sample_limit=sample_limit),
        check_evidence_fact_parity(db, sample_limit=sample_limit),
        check_cross_job_double_book(db, sample_limit=sample_limit),
        check_lineup_duplicate_ingestion(db, sample_limit=sample_limit),
    ]
    return AuditReport(
        database=dbname,
        filters=filters,
        checks=checks,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


def format_summary_table(report: AuditReport) -> str:
    lines = [
        f"database: {report.database}",
        f"generated_at: {report.generated_at}",
        "",
        f"{'check':<26} {'count':>8}  sample",
        "-" * 72,
    ]
    for c in report.checks:
        sample_ref = ""
        if c.samples:
            sample_ref = json.dumps(c.samples[0], default=str)[:120]
        lines.append(f"{c.check:<26} {c.count:>8}  {sample_ref}")
        if c.meta:
            lines.append(f"{'':26} {'':>8}  meta: {json.dumps(c.meta, default=str)[:100]}")
    return "\n".join(lines)
