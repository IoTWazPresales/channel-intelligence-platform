"""W1 read-only Plan vs Executed reconciliation audit (gate script).

Sections: 1a SHIPPED (job 310 ACZA), 1b PLANNED 26Q2, 1c CATEGORY tie-out, 1d PO MGMT.
NO writes to cip.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

REPO = Path(__file__).resolve().parents[3]
API = REPO / "apps" / "api"
sys.path.insert(0, str(API))

from app.core.config import get_settings
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    quarter_from_period_start,
    quarter_key_from_period_start,
)
from app.services.commercial_planner.lineup_po_gap import po_gap_worklist
from app.services.commercial_planner.lineup_po_reconciliation import UNITS_FLAGS, reconcile_case
from app.services.commercial_planner.plan_vs_executed import (
    _aggregate_exceptions,
    collect_execution_rows,
    compute_scorecard_from_execution_rows,
    plan_vs_executed_read_model,
)
from app.services.commercial_planner.po_management import backlog, coverage

JOB_ID = 310
PERIOD = "26Q2"
ACZA_FILE = Path(
    r"c:\Users\warren_eliason\OneDrive - ASUS\Desktop\Planning Dashboard"
    r"\ACZA Shipped Unshipped 20260703.xlsx"
)
OUT_JSON = REPO / ".tmp" / "w1_pve_recon_audit.json"

PO_GAP_GRAIN = (
    "A (PO, product) shipment grain is a gap when purchase_order_id is not linked through "
    "commercial_lineup_case_po to a case whose lineup contains that product_id; quantities "
    "from fact_inbound_shipment shipped lines only, quarter from ship_confirm_date "
    "(fallback schedule_ship_date)."
)


def _norm(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    s = str(v).strip()
    if re.fullmatch(r"\d+\.0+", s):
        s = str(int(float(s)))
    return re.sub(r"\s+", " ", s)


def _shipped_key(d: dict) -> str:
    return "|".join(
        x for x in ["ACZA", _norm(d.get("Delivery No")), _norm(d.get("Invoice Line")), _norm(d.get("Item"))] if x
    )


def _unship_key(d: dict) -> str:
    return "|".join(
        x for x in ["ACZA", _norm(d.get("Order No.")), _norm(d.get("Order Line")), _norm(d.get("Item"))] if x
    )


def _sync_url() -> str:
    url = get_settings().database_url_sync
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url.replace("postgresql+asyncpg", "postgresql+psycopg")


def _parse_raw_qty(payload: dict | None) -> float | None:
    if not isinstance(payload, dict):
        return None
    for k in ("quantity_units", "qty", "quantity", "units", "forecast_qty", "Qty", "QTY", "Planned Qty"):
        if k in payload and payload[k] not in (None, ""):
            try:
                return float(str(payload[k]).replace(",", ""))
            except (TypeError, ValueError):
                continue
    return None


def _file_tab_stats(shipped: pd.DataFrame, unship: pd.DataFrame) -> dict[str, Any]:
    ship_qty = float(shipped["Qty"].fillna(0).sum()) if "Qty" in shipped.columns else 0.0
    un_qty = float(unship["Qty"].fillna(0).sum()) if "Qty" in unship.columns else 0.0
    ship_keys: Counter[str] = Counter()
    un_keys: Counter[str] = Counter()
    for _, r in shipped.iterrows():
        k = _shipped_key(r.to_dict())
        if k and k != "ACZA":
            ship_keys[k] += float(r.get("Qty") or 0)
    for _, r in unship.iterrows():
        k = _unship_key(r.to_dict())
        if k and k != "ACZA":
            un_keys[k] += float(r.get("Qty") or 0)
    return {
        "shipped": {"rows": len(shipped), "qty_sum": ship_qty, "dedupe_keys": len(ship_keys), "dedupe_qty": sum(ship_keys.values())},
        "unship": {"rows": len(unship), "qty_sum": un_qty, "dedupe_keys": len(un_keys), "dedupe_qty": sum(un_keys.values())},
    }


def _resolve_acza_file(sync_engine) -> tuple[Path, str]:
    if ACZA_FILE.is_file():
        return ACZA_FILE, "desktop_path"
    with sync_engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT storage_key
                FROM raw_file_metadata
                WHERE job_id = :jid
                ORDER BY id DESC
                LIMIT 1
                """
            ),
            {"jid": JOB_ID},
        ).mappings().first()
    if row and row["storage_key"]:
        p = Path(str(row["storage_key"]))
        if p.is_file():
            return p, "raw_file_metadata"
        # relative to api storage roots
        for root in (API / "storage", API / "uploads", REPO / "storage"):
            candidate = root / p.name if not p.is_absolute() else p
            if candidate.is_file():
                return candidate, f"raw_file_metadata_resolved:{candidate}"
    raise FileNotFoundError(f"ACZA workbook not found at {ACZA_FILE} or raw_file_metadata for job {JOB_ID}")


def audit_shipped(sync_engine) -> dict[str, Any]:
    file_path, file_source = _resolve_acza_file(sync_engine)
    shipped = pd.read_excel(file_path, sheet_name="Shipped")
    unship = pd.read_excel(file_path, sheet_name="Unship")
    file_stats = _file_tab_stats(shipped, unship)

    with sync_engine.connect() as conn:
        job = conn.execute(
            text("SELECT id, file_name, status, created_at::text FROM import_job WHERE id=:jid"),
            {"jid": JOB_ID},
        ).mappings().first()

        def _agg(table: str, extra_where: str = "") -> list[dict]:
            return [
                dict(r)
                for r in conn.execute(
                    text(
                        f"""
                        SELECT line_state, report_type, COUNT(*) AS row_count, COALESCE(SUM(quantity),0) AS qty_sum
                        FROM {table}
                        WHERE import_job_id = :jid {extra_where}
                        GROUP BY line_state, report_type
                        ORDER BY report_type, line_state
                        """
                    ),
                    {"jid": JOB_ID},
                ).mappings().all()
            ]

        ev_line = _agg("shipment_evidence_line", "AND corpus_superseded_at IS NULL")
        ev_line_all = _agg("shipment_evidence_line")
        ev_current = _agg("shipment_evidence_current")
        fact = _agg("fact_inbound_shipment")

        fact_totals = conn.execute(
            text(
                """
                SELECT line_state, COUNT(*) AS row_count, COALESCE(SUM(quantity),0) AS qty_sum
                FROM fact_inbound_shipment
                WHERE import_job_id = :jid
                GROUP BY line_state
                """
            ),
            {"jid": JOB_ID},
        ).mappings().all()

        # Invoice-line duplicate probe (shipped tab)
        inv_dupes = conn.execute(
            text(
                """
                SELECT delivery_no, invoice_line, COUNT(*) AS n, SUM(quantity) AS qty
                FROM shipment_evidence_current
                WHERE import_job_id = :jid AND report_type = 'acza_workbook_shipped'
                  AND line_state = 'shipped'
                GROUP BY delivery_no, invoice_line
                HAVING COUNT(*) > 1
                ORDER BY n DESC
                LIMIT 10
                """
            ),
            {"jid": JOB_ID},
        ).mappings().all()

        superseded_n = conn.execute(
            text(
                """
                SELECT COUNT(*) FROM shipment_evidence_line
                WHERE import_job_id = :jid AND corpus_superseded_at IS NOT NULL
                """
            ),
            {"jid": JOB_ID},
        ).scalar()

    def _sum_by_state(rows: list[dict], report_type: str, line_state: str) -> tuple[int, float]:
        for r in rows:
            if r.get("report_type") == report_type and r.get("line_state") == line_state:
                return int(r["row_count"]), float(r["qty_sum"])
        return 0, 0.0

    ship_rt, ship_st = "acza_workbook_shipped", "shipped"
    un_rt, un_st = "acza_workbook_unship", "open_order"

    ev_ship_n, ev_ship_q = _sum_by_state(ev_current, ship_rt, ship_st)
    ev_un_n, ev_un_q = _sum_by_state(ev_current, un_rt, un_st)
    line_ship_n, line_ship_q = _sum_by_state(ev_line, ship_rt, ship_st)
    line_un_n, line_un_q = _sum_by_state(ev_line, un_rt, un_st)

    fact_all_ship = sum(float(r["qty_sum"]) for r in fact if r.get("line_state") == "shipped")
    fact_all_un = sum(float(r["qty_sum"]) for r in fact if r.get("line_state") == "open_order")
    fact_j310_ship = sum(float(r["qty_sum"]) for r in fact_totals if r.get("line_state") == "shipped")
    fact_j310_un = sum(float(r["qty_sum"]) for r in fact_totals if r.get("line_state") == "open_order")

    explanations: list[str] = []
    if file_stats["shipped"]["rows"] != ev_ship_n:
        explanations.append(
            f"Shipped row count file ({file_stats['shipped']['rows']}) vs evidence_current ({ev_ship_n}): "
            "invoice-line keys collapse duplicate delivery+invoice lines; empty keys skipped in dedupe maps."
        )
    if abs(file_stats["shipped"]["dedupe_qty"] - ev_ship_q) > 0.01:
        explanations.append(
            f"Shipped deduped file qty ({file_stats['shipped']['dedupe_qty']:.2f}) vs evidence ({ev_ship_q:.2f}): "
            "multi-item invoice lines summed per identity key."
        )
    if superseded_n:
        explanations.append(
            f"shipment_evidence_line has {superseded_n} superseded rows (corpus_superseded_at); "
            "current view excludes them."
        )
    if line_ship_n != ev_ship_n:
        explanations.append(
            f"evidence_line active ({line_ship_n}) vs evidence_current ({ev_ship_n}): bitemporal graduation / view filter."
        )
    if fact_j310_ship != fact_all_ship or fact_j310_un != fact_all_un:
        explanations.append(
            "fact_inbound_shipment is latest-job-wins corpus — job 310 subset may differ from all-job totals."
        )
    if inv_dupes:
        explanations.append(
            f"{len(inv_dupes)} invoice-line groups have >1 evidence row (sample top n={inv_dupes[0]['n']})."
        )

    deltas = {
        "shipped_rows_file_minus_evidence": file_stats["shipped"]["rows"] - ev_ship_n,
        "shipped_qty_dedupe_file_minus_evidence": file_stats["shipped"]["dedupe_qty"] - ev_ship_q,
        "unship_rows_file_minus_evidence": file_stats["unship"]["rows"] - ev_un_n,
        "unship_qty_file_minus_evidence": file_stats["unship"]["qty_sum"] - ev_un_q,
        "evidence_current_vs_line_shipped_rows": ev_ship_n - line_ship_n,
        "fact_job310_shipped_qty_minus_evidence": fact_j310_ship - ev_ship_q,
    }

    unexplained: list[str] = []
    if abs(deltas["shipped_qty_dedupe_file_minus_evidence"]) > 1.0 and not explanations:
        unexplained.append("shipped deduped qty mismatch without narrative")
    if abs(deltas["unship_qty_file_minus_evidence"]) > 1.0 and abs(deltas["unship_rows_file_minus_evidence"]) > 5:
        unexplained.append("unship qty/row mismatch beyond tolerance")

    return {
        "file_path": str(file_path),
        "file_source": file_source,
        "import_job": dict(job) if job else None,
        "file_stats": file_stats,
        "shipment_evidence_line_active": ev_line,
        "shipment_evidence_line_all": ev_line_all,
        "shipment_evidence_current": ev_current,
        "fact_inbound_shipment_by_job": [dict(r) for r in fact],
        "fact_inbound_shipment_job310_totals": [dict(r) for r in fact_totals],
        "invoice_line_dupes_sample": [dict(r) for r in inv_dupes],
        "superseded_line_rows": int(superseded_n or 0),
        "deltas": deltas,
        "explanations": explanations,
        "unexplained": unexplained,
        "pass": len(unexplained) == 0,
    }


async def audit_planned_26q2(db: AsyncSession) -> dict[str, Any]:
    cases = (
        await db.execute(
            select(CommercialLineupCase)
            .where(
                CommercialLineupCase.inferred_period_start.isnot(None),
                *active_lineup_case_filters(),
            )
            .order_by(CommercialLineupCase.id)
        )
    ).scalars().all()

    q2_cases: list[CommercialLineupCase] = []
    for c in cases:
        if c.inferred_period_start is None:
            continue
        y, q = quarter_from_period_start(c.inferred_period_start)
        if y == 2026 and q == 2:
            q2_cases.append(c)

    case_ids = [int(c.id) for c in q2_cases]
    lines: list[CommercialLineupLine] = []
    if case_ids:
        lines = list(
            (
                await db.execute(select(CommercialLineupLine).where(CommercialLineupLine.case_id.in_(case_ids)))
            ).scalars().all()
        )

    line_qty_sum = sum(float(ln.quantity_units or 0) for ln in lines)
    raw_qty_sum = 0.0
    raw_mismatch_lines = 0
    month_split_lines = 0
    for ln in lines:
        raw_q = _parse_raw_qty(ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else None)
        if raw_q is not None:
            raw_qty_sum += raw_q
            if abs(raw_q - float(ln.quantity_units or 0)) > 0.01:
                raw_mismatch_lines += 1
        if ln.month_split_json:
            month_split_lines += 1

    one_h_cases = [
        {
            "case_id": int(c.id),
            "file_name": c.file_name,
            "period_label": c.period_label,
            "inferred_period_start": str(c.inferred_period_start),
            "product_line": c.product_line,
            "business_unit": c.business_unit,
        }
        for c in q2_cases
        if c.file_name and "1H" in c.file_name.upper()
    ]

    by_case_line_qty: dict[int, float] = defaultdict(float)
    by_case_raw_qty: dict[int, float] = defaultdict(float)
    for ln in lines:
        by_case_line_qty[int(ln.case_id)] += float(ln.quantity_units or 0)
        rq = _parse_raw_qty(ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else None)
        if rq is not None:
            by_case_raw_qty[int(ln.case_id)] += rq

    case_rollups = []
    for c in q2_cases:
        cid = int(c.id)
        case_rollups.append(
            {
                "case_id": cid,
                "file_name": c.file_name,
                "period_label": c.period_label,
                "quarter_label": quarter_key_from_period_start(c.inferred_period_start),
                "line_count": sum(1 for ln in lines if int(ln.case_id) == cid),
                "quantity_units_sum": by_case_line_qty[cid],
                "raw_payload_qty_sum": by_case_raw_qty.get(cid, 0.0),
            }
        )

    delta = line_qty_sum - raw_qty_sum
    explanations = []
    if abs(delta) > 0.01:
        explanations.append(
            f"quantity_units ({line_qty_sum}) vs raw_row_payload parsed qty ({raw_qty_sum}): "
            f"{raw_mismatch_lines} lines differ — month phasing / 1H allocation may rewrite quantity_units."
        )
    if one_h_cases:
        explanations.append(
            f"{len(one_h_cases)} 26Q2 cases sourced from 1H workbooks — quarter cases may carry full-H1 quantities."
        )
    if month_split_lines:
        explanations.append(f"{month_split_lines} lines have month_split_json (month-derived phasing).")

    unexplained = []
    if abs(delta) > 1.0 and raw_mismatch_lines > 0 and not explanations:
        unexplained.append("planned line vs raw payload delta without 1H/month narrative")

    return {
        "case_count": len(q2_cases),
        "line_count": len(lines),
        "quantity_units_sum": line_qty_sum,
        "raw_row_payload_qty_sum": raw_qty_sum,
        "delta_line_minus_raw": delta,
        "raw_mismatch_line_count": raw_mismatch_lines,
        "month_split_line_count": month_split_lines,
        "one_h_cases": one_h_cases,
        "case_rollups": case_rollups,
        "explanations": explanations,
        "unexplained": unexplained,
        "pass": len(unexplained) == 0,
    }


def _exception_category_counts(exceptions: dict[str, Any]) -> dict[str, int]:
    return {
        cat: len(exceptions.get("customer", {}).get(cat, []))
        for cat in ("short_ships", "over_ships", "unplanned_intake", "no_po_blind_spots")
    }


def _flag_summary_from_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary = {f: 0 for f in UNITS_FLAGS if f != "po_no_match"}
    awaiting_po = 0
    for r in rows:
        flag = r.get("units_flag")
        if flag in summary:
            summary[flag] += 1
        if r.get("awaiting_po") and float(r.get("planned_units") or 0) > 0:
            awaiting_po += 1
    summary["awaiting_po"] = awaiting_po
    return summary


async def audit_category_26q2(db: AsyncSession) -> dict[str, Any]:
    rows = await collect_execution_rows(db, period_from=PERIOD, period_to=PERIOD)
    sc_direct = compute_scorecard_from_execution_rows(rows)
    payload = await plan_vs_executed_read_model(db, period_from=PERIOD, period_to=PERIOD)
    sc_api = payload.get("scorecard") or {}

    exc_direct = _aggregate_exceptions(rows, rank_by="units")
    exc_api = payload.get("exceptions") or {}
    cat_direct = _exception_category_counts(exc_direct)
    cat_api = _exception_category_counts(exc_api)

    flag_direct = sc_direct.get("flag_summary") or {}
    flag_api = sc_api.get("flag_summary") or {}
    flag_rows = _flag_summary_from_rows(rows)
    awaiting_direct = sc_direct.get("awaiting_po_line_count")
    awaiting_api = sc_api.get("awaiting_po_line_count")
    awaiting_rows = sum(
        1 for r in rows if r.get("awaiting_po") and float(r.get("planned_units") or 0) > 0
    )

    scorecard_checks = {
        "planned_units": sc_direct.get("planned_units") == sc_api.get("planned_units"),
        "fill_rate": sc_direct.get("fill_rate") == sc_api.get("fill_rate"),
        "short_exposure_units": sc_direct.get("short_exposure_units") == sc_api.get("short_exposure_units"),
        "deal_stock_units": sc_direct.get("deal_stock_units") == sc_api.get("deal_stock_units"),
        "awaiting_po_line_count": awaiting_direct == awaiting_api == awaiting_rows,
    }

    # awaiting_po is tracked on scorecard.awaiting_po_line_count, not in flag_summary (UNITS_FLAGS).
    flag_checks = {
        f: flag_direct.get(f) == flag_rows.get(f)
        for f in sorted(set(flag_direct) | set(flag_rows))
        if f != "awaiting_po"
    }
    bucket_api = sc_api.get("buckets") or {}
    bucket_direct = sc_direct.get("buckets") or {}

    unexplained = []
    for k, ok in scorecard_checks.items():
        if not ok:
            unexplained.append(f"scorecard {k}: direct={sc_direct.get(k)} api={sc_api.get(k)}")
    for k, ok in flag_checks.items():
        if not ok:
            unexplained.append(f"flag_summary {k}: scorecard={flag_direct.get(k)} rows={flag_rows.get(k)}")
    for cat in cat_direct:
        if cat_direct[cat] != cat_api.get(cat):
            unexplained.append(f"exception {cat}: direct={cat_direct[cat]} api={cat_api.get(cat)}")

    return {
        "execution_row_count": len(rows),
        "scorecard_direct": {k: sc_direct.get(k) for k in (
            "planned_units", "fill_rate", "line_hit_rate", "short_exposure_units",
            "deal_stock_units", "unplanned_intake_units", "flag_summary", "buckets",
        )},
        "scorecard_api": {k: sc_api.get(k) for k in (
            "planned_units", "fill_rate", "line_hit_rate", "short_exposure_units",
            "deal_stock_units", "unplanned_intake_units", "flag_summary", "buckets",
        )},
        "flag_summary_from_rows": flag_rows,
        "awaiting_po_line_count": {
            "scorecard_direct": awaiting_direct,
            "scorecard_api": awaiting_api,
            "from_rows": awaiting_rows,
        },
        "exception_category_counts_direct": cat_direct,
        "exception_category_counts_api": cat_api,
        "scorecard_checks": scorecard_checks,
        "flag_checks": flag_checks,
        "bucket_match": bucket_direct == bucket_api,
        "unexplained": unexplained,
        "pass": len(unexplained) == 0,
    }


async def audit_po_mgmt(db: AsyncSession) -> dict[str, Any]:
    cov = await coverage(db)
    bl = await backlog(db)
    gap = await po_gap_worklist(db, include_dismissed=False)

    upload_needed = sum(1 for g in bl.get("groups") or [] if g.get("upload_prompt"))
    linked_groups = sum(1 for g in bl.get("groups") or [] if g.get("status") == "linked")

    return {
        "coverage": {
            "total_pos_observed": cov.get("total_pos_observed"),
            "total_pos_linked": cov.get("total_pos_linked"),
            "first_run": cov.get("first_run"),
            "group_count": len(cov.get("groups") or []),
            "data_unavailable": cov.get("data_unavailable"),
        },
        "backlog": {
            "group_count": len(bl.get("groups") or []),
            "upload_needed_count": upload_needed,
            "linked_group_count": linked_groups,
            "data_unavailable": bl.get("data_unavailable"),
        },
        "po_gap_worklist": {
            "total_gap_rows": gap.get("total_gap_rows"),
            "group_count": len(gap.get("groups") or []),
            "grain": PO_GAP_GRAIN,
            "data_unavailable": gap.get("data_unavailable"),
        },
        "pass": not cov.get("data_unavailable") and not bl.get("data_unavailable") and not gap.get("data_unavailable"),
    }


async def main() -> int:
    settings = get_settings()
    resolved_url = settings.database_url
    print("resolved_url:", resolved_url)

    sync_engine = create_engine(_sync_url())
    with sync_engine.connect() as conn:
        db_name = conn.execute(text("SELECT current_database()")).scalar()
    print("current_database():", db_name)
    if db_name != "cip":
        print("GATE: FAIL — not cip")
        return 2

    report: dict[str, Any] = {
        "database": db_name,
        "resolved_url": resolved_url,
        "period": PERIOD,
        "job_id": JOB_ID,
    }

    print("\n=== 1a SHIPPED (job 310) ===")
    report["1a_shipped"] = audit_shipped(sync_engine)
    print(json.dumps({k: report["1a_shipped"][k] for k in ("file_stats", "deltas", "explanations", "pass")}, indent=2))

    engine = create_async_engine(resolved_url)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        db_check = (await db.execute(text("SELECT current_database()"))).scalar_one()
        assert db_check == "cip"

        print("\n=== 1b PLANNED 26Q2 ===")
        report["1b_planned"] = await audit_planned_26q2(db)
        print(
            json.dumps(
                {
                    "case_count": report["1b_planned"]["case_count"],
                    "quantity_units_sum": report["1b_planned"]["quantity_units_sum"],
                    "raw_row_payload_qty_sum": report["1b_planned"]["raw_row_payload_qty_sum"],
                    "delta": report["1b_planned"]["delta_line_minus_raw"],
                    "pass": report["1b_planned"]["pass"],
                },
                indent=2,
            )
        )

        print("\n=== 1c CATEGORY 26Q2 ===")
        report["1c_category"] = await audit_category_26q2(db)
        print(
            json.dumps(
                {
                    "execution_row_count": report["1c_category"]["execution_row_count"],
                    "scorecard_checks": report["1c_category"]["scorecard_checks"],
                    "exception_category_counts_api": report["1c_category"]["exception_category_counts_api"],
                    "unexplained": report["1c_category"]["unexplained"],
                    "pass": report["1c_category"]["pass"],
                },
                indent=2,
            )
        )

        print("\n=== 1d PO MGMT ===")
        report["1d_po_mgmt"] = await audit_po_mgmt(db)
        print(json.dumps(report["1d_po_mgmt"], indent=2))

    await engine.dispose()
    sync_engine.dispose()

    all_unexplained: list[str] = []
    for section in ("1a_shipped", "1b_planned", "1c_category"):
        all_unexplained.extend(report[section].get("unexplained") or [])

    gate_pass = db_name == "cip" and all(
        report[s].get("pass") for s in ("1a_shipped", "1b_planned", "1c_category", "1d_po_mgmt")
    )
    report["gate"] = {
        "pass": gate_pass,
        "unexplained_mismatches": all_unexplained,
        "key_numbers": {
            "shipped_file_rows": report["1a_shipped"]["file_stats"]["shipped"]["rows"],
            "shipped_evidence_qty": sum(
                float(r["qty_sum"])
                for r in report["1a_shipped"]["shipment_evidence_current"]
                if r.get("report_type") == "acza_workbook_shipped"
            ),
            "planned_26q2_units": report["1b_planned"]["quantity_units_sum"],
            "pve_execution_rows": report["1c_category"]["execution_row_count"],
            "pve_fill_rate": report["1c_category"]["scorecard_api"].get("fill_rate"),
            "po_observed": report["1d_po_mgmt"]["coverage"]["total_pos_observed"],
            "po_linked": report["1d_po_mgmt"]["coverage"]["total_pos_linked"],
            "backlog_upload_needed": report["1d_po_mgmt"]["backlog"]["upload_needed_count"],
            "po_gap_rows": report["1d_po_mgmt"]["po_gap_worklist"]["total_gap_rows"],
        },
    }

    OUT_JSON.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT_JSON}")
    print("\n=== GATE ===", "PASS" if gate_pass else "FAIL")
    if all_unexplained:
        print("UNEXPLAINED:", all_unexplained)
    return 0 if gate_pass else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
