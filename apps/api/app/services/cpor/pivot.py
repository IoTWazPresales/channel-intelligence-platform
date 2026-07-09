"""Shared CPOR USD pivot aggregation (POD quarter × product_line → Ttl Support USD).

Used by GET /cpor/cases/{id}/pivot and the XLSX pivot sheet (U4).
Prefers stored ``ttl_support_usd`` (recompute-owned, full-precision path).
Falls back to ``support_usd * estimate_qty`` for pre-0068 rows.
Voided / zero-estimate lines are excluded.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimProduct


def is_voided_line(line: CporCaseLine) -> bool:
    remark = line.remark or ""
    if "[voided]" in remark or "[split into layers]" in remark:
        return True
    try:
        return float(line.estimate_qty or 0) == 0.0 and ("[voided]" in remark or "[split" in remark)
    except (TypeError, ValueError):
        return False


def _line_ttl_support_usd(line: CporCaseLine) -> float | None:
    stored = getattr(line, "ttl_support_usd", None)
    if stored is not None:
        return float(stored)
    if line.support_usd is None or line.estimate_qty is None:
        return None
    if float(line.estimate_qty) == 0.0:
        return None
    return float(line.support_usd) * float(line.estimate_qty)


def build_case_pivot(
    session: Session,
    case: CporCase,
    lines: list[CporCaseLine],
    products: dict[int, DimProduct],
) -> dict[str, Any]:
    cells: dict[str, dict[str, float]] = {}
    row_totals: dict[str, float] = {}
    col_totals: dict[str, float] = {}
    grand = 0.0
    for line in lines:
        if is_voided_line(line):
            continue
        if float(line.estimate_qty or 0) == 0.0:
            continue
        usd = _line_ttl_support_usd(line)
        if usd is None:
            continue
        pq = line.pod_quarter or "(none)"
        prod = products.get(int(line.product_id))
        pl = (prod.product_line if prod and prod.product_line else None) or "(unknown)"
        cells.setdefault(pq, {})
        cells[pq][pl] = cells[pq].get(pl, 0.0) + usd
        row_totals[pq] = row_totals.get(pq, 0.0) + usd
        col_totals[pl] = col_totals.get(pl, 0.0) + usd
        grand += usd
    return {
        "case_id": case.id,
        "case_code": case.case_code,
        "roe_snapshot": float(case.roe_snapshot) if case.roe_snapshot is not None else None,
        "missing_roe": case.roe_snapshot is None,
        "cells": cells,
        "row_totals": row_totals,
        "col_totals": col_totals,
        "grand_total_usd": grand,
    }
