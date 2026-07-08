"""BACKLOG-066 repair: soft-partition duplicate-ingestion lineup lines by product_line.

When pre-fan-out imports duplicated the same workbook into multiple active cases (#39 NR, #40 NV),
each case retains only lines whose ``dim_product.product_line`` matches the case BU (product-first).
Wrong-BU lines are soft-superseded via ``row_status='superseded'`` — never deleted; audit trail preserved.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimProduct
from app.services.commercial_planner.lineup_period_canonical import (
    active_lineup_case_filters,
    active_lineup_line_filters,
    canonical_case_line_code,
    quarter_from_period_start,
)
from app.services.commercial_planner.po_management import canonical_product_line_code
from app.services.data_integrity_audit import check_lineup_duplicate_ingestion

PARTITION_DIAGNOSTIC = "duplicate_ingestion_partition"


def _case_target_line(case: CommercialLineupCase) -> str:
    return canonical_product_line_code(case.product_line, case.business_unit)


def _line_product_line(pid: int | None, pline_by_id: dict[int, str | None]) -> str:
    if pid is None:
        return "Unclassified"
    return canonical_product_line_code(pline_by_id.get(int(pid)), None)


def preview_duplicate_partition(
    db: Session,
    *,
    case_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Preview lines that would be soft-superseded per case (read-only)."""
    clusters = _resolve_target_clusters(db, case_ids=case_ids)
    if not clusters:
        return {"clusters": [], "cases": [], "total_lines_to_supersede": 0}

    all_case_ids = sorted({cid for c in clusters for cid in c["case_ids"]})
    cases = {
        int(c.id): c
        for c in db.execute(
            select(CommercialLineupCase).where(CommercialLineupCase.id.in_(all_case_ids))
        ).scalars().all()
    }
    pline_by_id = _product_lines_for_cases(db, all_case_ids)

    case_previews: list[dict[str, Any]] = []
    total_supersede = 0
    for cid in all_case_ids:
        case = cases.get(cid)
        if case is None:
            continue
        target = _case_target_line(case)
        lines = db.execute(
            select(CommercialLineupLine).where(
                CommercialLineupLine.case_id == cid,
                *active_lineup_line_filters(),
            )
        ).scalars().all()
        keep: list[dict[str, Any]] = []
        supersede: list[dict[str, Any]] = []
        for ln in lines:
            pl = _line_product_line(int(ln.product_id) if ln.product_id else None, pline_by_id)
            row = {
                "line_id": int(ln.id),
                "product_id": ln.product_id,
                "product_line": pl,
                "quantity_units": float(ln.quantity_units or 0),
                "source_row_number": ln.source_row_number,
            }
            if pl == target or pl == "Unclassified":
                keep.append(row)
            else:
                supersede.append(row)
        total_supersede += len(supersede)
        case_previews.append(
            {
                "case_id": cid,
                "business_unit": case.business_unit,
                "target_product_line": target,
                "lines_keep": len(keep),
                "lines_supersede": len(supersede),
                "units_keep": sum(r["quantity_units"] for r in keep),
                "units_supersede": sum(r["quantity_units"] for r in supersede),
                "supersede_sample": supersede[:5],
            }
        )

    return {
        "clusters": clusters,
        "cases": case_previews,
        "total_lines_to_supersede": total_supersede,
    }


def apply_duplicate_partition(
    db: Session,
    *,
    case_ids: list[int],
    actor: str = "steward",
) -> dict[str, Any]:
    """Soft-supersede wrong-BU lines for the given active duplicate-ingestion cases."""
    preview = preview_duplicate_partition(db, case_ids=case_ids)
    if preview["total_lines_to_supersede"] == 0:
        return {"applied": False, "message": "No lines to partition", **preview}

    pline_by_id = _product_lines_for_cases(db, case_ids)
    cases = {
        int(c.id): c
        for c in db.execute(
            select(CommercialLineupCase).where(CommercialLineupCase.id.in_(case_ids))
        ).scalars().all()
    }
    applied = 0
    for cid in case_ids:
        case = cases.get(cid)
        if case is None:
            continue
        target = _case_target_line(case)
        lines = db.execute(
            select(CommercialLineupLine).where(
                CommercialLineupLine.case_id == cid,
                *active_lineup_line_filters(),
            )
        ).scalars().all()
        for ln in lines:
            pl = _line_product_line(int(ln.product_id) if ln.product_id else None, pline_by_id)
            if pl != target and pl != "Unclassified":
                ln.row_status = "superseded"
                codes = list(ln.diagnostic_codes or [])
                if PARTITION_DIAGNOSTIC not in codes:
                    codes.append(PARTITION_DIAGNOSTIC)
                ln.diagnostic_codes = codes
                note = f"[{PARTITION_DIAGNOSTIC}] superseded {pl} line — case owns {target} only"
                ln.internal_notes = (
                    f"{ln.internal_notes}\n{note}".strip() if ln.internal_notes else note
                )
                applied += 1
    db.commit()

    dup_after = check_lineup_duplicate_ingestion(db, sample_limit=50)
    return {
        "applied": True,
        "lines_superseded": applied,
        "actor": actor,
        "preview": preview,
        "duplicate_ingestion_clusters_after": dup_after.count,
    }


def list_duplicate_ingestion_clusters(db: Session, *, sample_limit: int = 50) -> dict[str, Any]:
    """Expose ``check_lineup_duplicate_ingestion`` for steward UI."""
    result = check_lineup_duplicate_ingestion(db, sample_limit=sample_limit)
    return {
        "cluster_count": result.count,
        "clusters": result.samples or [],
    }


def _resolve_target_clusters(db: Session, *, case_ids: list[int] | None) -> list[dict[str, Any]]:
    result = check_lineup_duplicate_ingestion(db, sample_limit=500)
    clusters = list(result.samples or [])
    if case_ids:
        want = {int(x) for x in case_ids}
        clusters = [c for c in clusters if want.intersection(c.get("case_ids") or [])]
    return clusters


def _product_lines_for_cases(db: Session, case_ids: list[int]) -> dict[int, str | None]:
    pids = [
        int(r[0])
        for r in db.execute(
            select(CommercialLineupLine.product_id)
            .where(
                CommercialLineupLine.case_id.in_(case_ids),
                CommercialLineupLine.product_id.isnot(None),
                *active_lineup_line_filters(),
            )
            .distinct()
        ).all()
        if r[0] is not None
    ]
    if not pids:
        return {}
    return {
        int(r[0]): r[1]
        for r in db.execute(
            select(DimProduct.id, DimProduct.product_line).where(DimProduct.id.in_(pids))
        ).all()
    }


def planned_units_by_period_bu(
    db: Session,
    *,
    year: int,
    quarter: int,
    business_units: list[str],
) -> dict[str, float]:
    """Sum active lineup line units for cases in a calendar quarter × BU (projection-aligned)."""
    from app.services.commercial_planner.lineup_period_canonical import quarter_from_period_start

    cases = db.execute(
        select(CommercialLineupCase).where(
            *active_lineup_case_filters(),
            CommercialLineupCase.inferred_period_start.isnot(None),
        )
    ).scalars().all()
    bu_set = {b.strip().upper() for b in business_units}
    out: dict[str, float] = {b: 0.0 for b in business_units}
    for case in cases:
        if case.inferred_period_start is None:
            continue
        y, q = quarter_from_period_start(case.inferred_period_start)
        if y != year or q != quarter:
            continue
        bu = (case.business_unit or "").strip().upper()
        if bu not in bu_set:
            continue
        target = canonical_case_line_code(case) or bu
        lines = db.execute(
            select(CommercialLineupLine).where(
                CommercialLineupLine.case_id == case.id,
                *active_lineup_line_filters(),
                CommercialLineupLine.product_id.isnot(None),
            )
        ).scalars().all()
        pline_by_id = _product_lines_for_cases(db, [int(case.id)])
        for ln in lines:
            pl = _line_product_line(int(ln.product_id), pline_by_id)
            if pl == target or pl == "Unclassified":
                out[bu] = out.get(bu, 0.0) + float(ln.quantity_units or 0)
    return out
