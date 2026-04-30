"""CSV bulk import for commercial_sku_assumption (controlled cost / PM bottom inputs).

Deterministic product matching, preview/apply split, no DAP/evidence columns.
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commercial_planner import CommercialSkuAssumption
from app.models.dimensions import DimProduct

# Template columns (exact header row order for download).
TEMPLATE_HEADERS: list[str] = [
    "sku",
    "part_number",
    "sales_model",
    "model_name",
    "controlled_cost_amount",
    "controlled_cost_currency_code",
    "fx_plan_currency_per_cost_currency",
    "vat_rate_pct",
    "reserve_total_pct",
    "campaign_support_reserve_split_pct",
]

# Optional CSV columns (ignored for persistence; no DB fields required).
_IGNORED_OPTIONAL_HEADERS = frozenset({"notes", "source_reference", "valid_from", "valid_to"})


def _forbidden_import_column(h: str) -> str | None:
    """Reject evidence / DAP-style columns that must not feed controlled cost."""
    hl = (h or "").strip().lower()
    if hl in _IGNORED_OPTIONAL_HEADERS:
        return None
    needles = (
        "dap_local",
        "local_dap",
        "rand_landed",
        "disti_cost",
        "landed_cost",
        "sell_in_price",
        "oem_buy",
        "import_evidence",
        "evidence_currency",
    )
    for n in needles:
        if n in hl:
            return n
    if hl == "dap" or hl.startswith("dap_") or hl.endswith("_dap"):
        return "dap"
    return None


def build_template_csv() -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(TEMPLATE_HEADERS)
    w.writerow(
        [
            "EXAMPLE-SKU",
            "EX-PN-001",
            "Example sales model",
            "Example model",
            "100.00",
            "USD",
            "18.5",
            "0.15",
            "0.10",
            "0.50",
        ]
    )
    return buf.getvalue()


def _norm_header(s: str) -> str:
    return re.sub(r"[\s\-]+", "_", (s or "").strip().lower())


def _clean_cell(v: Any) -> str:
    if v is None:
        return ""
    t = str(v).strip()
    if t.lower() in ("", "nan", "none", "null"):
        return ""
    return t


def _parse_money(s: str) -> float | None:
    t = _clean_cell(s).replace(",", "")
    if not t:
        return None
    try:
        return float(Decimal(t))
    except (InvalidOperation, ValueError):
        return None


def _normalize_rate_field(name: str, raw: str) -> tuple[float | None, str | None]:
    """Interpret 0–1 decimal or plain percent (1–100) for VAT / reserve fields."""
    t = _clean_cell(raw)
    if not t:
        return None, f"{name} is required"
    try:
        v = float(Decimal(t.replace(",", "")))
    except (InvalidOperation, ValueError):
        return None, f"{name} is not a valid number"
    if v < 0:
        return None, f"{name} must be non-negative"
    # Convention: values > 1 and <= 100 are treated as percent points (15 -> 0.15).
    if v > 1.0:
        if v > 100.0:
            return None, f"{name} must be between 0 and 1 (decimal) or 1–100 (percent points)"
        v = v / 100.0
    if v > 1.0:
        return None, f"{name} must be <= 1 after normalization"
    return v, None


def _validate_currency(code: str) -> tuple[str | None, str | None]:
    c = (code or "").strip().upper()
    if len(c) < 3 or len(c) > 8:
        return None, "controlled_cost_currency_code must be 3–8 letters (ISO-style)"
    if not re.fullmatch(r"[A-Z]{3,8}", c):
        return None, "controlled_cost_currency_code must be letters only (A–Z)"
    return c, None


def decode_csv_rows(content: bytes) -> tuple[list[dict[str, str]], list[str]]:
    """Return list of row dicts (canonical keys) and fatal parse errors."""
    errs: list[str] = []
    if not content or not content.strip():
        return [], ["File is empty"]
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["File must be UTF-8 encoded"]

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return [], ["CSV has no header row"]

    for orig in reader.fieldnames:
        if orig is None:
            continue
        h = _norm_header(orig)
        bad = _forbidden_import_column(h)
        if bad:
            errs.append(
                f"Column '{orig.strip()}' is not allowed on SKU economics import "
                f"(DAP / evidence must not be mapped to controlled cost; remove {bad!r}-style columns)."
            )
    if errs:
        return [], errs

    # Map each file header to canonical template header when obvious.
    alias = {
        "promo_reserve_split_pct": "campaign_support_reserve_split_pct",
        "sales_model_name": "sales_model",
    }
    header_map: dict[str, str] = {}
    for orig in reader.fieldnames:
        if orig is None:
            continue
        k = _norm_header(orig)
        k = alias.get(k, k)
        header_map[orig] = k

    rows_out: list[dict[str, str]] = []
    for i, row in enumerate(reader, start=2):  # 1-based header; first data row is line 2
        canon: dict[str, str] = {}
        for ok, ov in row.items():
            if ok is None:
                continue
            ck = header_map.get(ok, _norm_header(ok))
            if ck in _IGNORED_OPTIONAL_HEADERS:
                continue
            canon[ck] = _clean_cell(ov)
        rows_out.append(canon)
    return rows_out, []


@dataclass
class ProductIndex:
    by_sku_lower: dict[str, int]
    by_part_lower: dict[str, int]
    pair_to_ids: dict[tuple[str, str], list[int]]


def build_product_index(products: list[DimProduct]) -> ProductIndex:
    by_sku: dict[str, int] = {}
    by_part: dict[str, int] = {}
    pair_map: dict[tuple[str, str], list[int]] = defaultdict(list)
    for p in products:
        if p.sku and str(p.sku).strip():
            by_sku[str(p.sku).strip().lower()] = p.id
        if p.part_number and str(p.part_number).strip():
            by_part[str(p.part_number).strip().lower()] = p.id
        if p.sales_model_name and str(p.sales_model_name).strip() and p.model_name and str(p.model_name).strip():
            key = (str(p.sales_model_name).strip().lower(), str(p.model_name).strip().lower())
            pair_map[key].append(p.id)
    return ProductIndex(by_sku_lower=by_sku, by_part_lower=by_part, pair_to_ids={k: v for k, v in pair_map.items()})


def resolve_product_id(row: dict[str, str], idx: ProductIndex) -> tuple[int | None, str | None, str | None]:
    """Return (product_id, match_method, error_message)."""
    sku = row.get("sku", "").strip().lower()
    pn = row.get("part_number", "").strip().lower()
    sm = row.get("sales_model", "").strip().lower()
    mn = row.get("model_name", "").strip().lower()

    if sku:
        pid = idx.by_sku_lower.get(sku)
        if pid is None:
            return None, None, f"No product with sku={row.get('sku', '').strip()!r}"
        return pid, "sku", None

    if pn:
        pid = idx.by_part_lower.get(pn)
        if pid is None:
            return None, None, f"No product with part_number={row.get('part_number', '').strip()!r}"
        return pid, "part_number", None

    if sm and mn:
        ids = idx.pair_to_ids.get((sm, mn), [])
        if len(ids) == 0:
            return None, None, "No product matched sales_model + model_name"
        if len(ids) > 1:
            return None, None, "Multiple products match sales_model + model_name — disambiguate with sku or part_number"
        return ids[0], "sales_model_model_name", None

    return None, None, "Provide sku, or part_number, or both sales_model and model_name"


async def preview_sku_economics_import(db: AsyncSession, content: bytes) -> dict[str, Any]:
    rows_raw, parse_errs = decode_csv_rows(content)
    if parse_errs:
        return {"parse_errors": parse_errs, "rows": [], "summary": _empty_summary(), "can_apply": False}

    products = (await db.execute(select(DimProduct))).scalars().all()
    idx = build_product_index(list(products))
    assumptions = (await db.execute(select(CommercialSkuAssumption))).scalars().all()
    by_product: dict[int, CommercialSkuAssumption] = {a.product_id: a for a in assumptions}

    preview_rows: list[dict[str, Any]] = []
    seen_product: dict[int, int] = {}
    summary = _empty_summary()

    for i, row in enumerate(rows_raw, start=2):
        msgs: list[str] = []
        blocking = False

        pid, method, err = resolve_product_id(row, idx)
        if err:
            blocking = True
            msgs.append(err)
            preview_rows.append(_row_shell(i, row, None, None, "error", msgs, blocking, None, None))
            summary["errors"] += 1
            summary["blocking_errors"] += 1
            continue

        assert pid is not None
        if pid in seen_product:
            blocking = True
            msgs.append(f"Duplicate row for same product (also on CSV row {seen_product[pid]})")
            preview_rows.append(_row_shell(i, row, pid, method, "error", msgs, blocking, None, None))
            summary["errors"] += 1
            summary["blocking_errors"] += 1
            continue
        seen_product[pid] = i

        amt = _parse_money(row.get("controlled_cost_amount", ""))
        if amt is None or amt <= 0:
            blocking = True
            msgs.append("controlled_cost_amount must be a number > 0")

        ccy, ccy_err = _validate_currency(row.get("controlled_cost_currency_code", ""))
        if ccy_err:
            blocking = True
            msgs.append(ccy_err)

        fx = _parse_money(row.get("fx_plan_currency_per_cost_currency", ""))
        if fx is None or fx <= 0:
            blocking = True
            msgs.append("fx_plan_currency_per_cost_currency must be a number > 0")

        vat, vat_e = _normalize_rate_field("vat_rate_pct", row.get("vat_rate_pct", ""))
        if vat_e:
            blocking = True
            msgs.append(vat_e)

        rt, rt_e = _normalize_rate_field("reserve_total_pct", row.get("reserve_total_pct", ""))
        if rt_e:
            blocking = True
            msgs.append(rt_e)

        ps, ps_e = _normalize_rate_field(
            "campaign_support_reserve_split_pct", row.get("campaign_support_reserve_split_pct", "")
        )
        if ps_e:
            blocking = True
            msgs.append(ps_e)

        current = None
        if pid in by_product:
            a = by_product[pid]
            current = {
                "assumption_id": a.id,
                "controlled_cost_amount": float(a.controlled_cost_amount),
                "controlled_cost_currency_code": str(a.controlled_cost_currency_code or "").strip(),
                "fx_plan_currency_per_cost_currency": float(a.fx_plan_currency_per_cost_currency),
                "vat_rate_pct": float(a.vat_rate_pct),
                "reserve_total_pct": float(a.reserve_total_pct),
                "promo_reserve_split_pct": float(a.promo_reserve_split_pct),
            }

        proposed = None
        if not blocking and amt is not None and ccy and fx is not None and vat is not None and rt is not None and ps is not None:
            proposed = {
                "controlled_cost_amount": amt,
                "controlled_cost_currency_code": ccy,
                "fx_plan_currency_per_cost_currency": fx,
                "vat_rate_pct": vat,
                "reserve_total_pct": rt,
                "promo_reserve_split_pct": ps,
            }

        action = "error" if blocking else ("update" if current else "create")
        if blocking:
            summary["errors"] += 1
            summary["blocking_errors"] += 1
        elif action == "update":
            summary["updates"] += 1
        else:
            summary["creates"] += 1

        prod = next((p for p in products if p.id == pid), None)
        preview_rows.append(
            _row_shell(
                i,
                row,
                pid,
                method,
                action,
                msgs,
                blocking,
                current,
                proposed,
                prod.sku if prod else None,
                prod.name if prod else None,
            )
        )

    can_apply = summary["blocking_errors"] == 0 and (summary["creates"] + summary["updates"]) > 0
    return {"parse_errors": [], "rows": preview_rows, "summary": summary, "can_apply": can_apply}


def _empty_summary() -> dict[str, int]:
    return {"creates": 0, "updates": 0, "errors": 0, "blocking_errors": 0}


def _row_shell(
    source_row: int,
    row: dict[str, str],
    product_id: int | None,
    match_method: str | None,
    action: str,
    messages: list[str],
    blocking: bool,
    current: dict | None,
    proposed: dict | None,
    product_sku: str | None = None,
    product_name: str | None = None,
) -> dict[str, Any]:
    return {
        "source_row": source_row,
        "sku": row.get("sku"),
        "part_number": row.get("part_number"),
        "sales_model": row.get("sales_model"),
        "model_name": row.get("model_name"),
        "product_id": product_id,
        "product_sku": product_sku,
        "product_name": product_name,
        "match_method": match_method,
        "action": action,
        "messages": messages,
        "blocking": blocking,
        "current": current,
        "proposed": proposed,
    }


async def apply_sku_economics_import(db: AsyncSession, content: bytes) -> dict[str, Any]:
    """Re-parse and persist creates/updates. Caller must enforce confirm gate."""
    preview = await preview_sku_economics_import(db, content)
    if preview.get("parse_errors"):
        raise ValueError("; ".join(preview["parse_errors"]))
    if not preview.get("can_apply"):
        raise ValueError("Cannot apply: fix blocking errors or add at least one valid row")

    applied_creates = 0
    applied_updates = 0
    try:
        for pr in preview["rows"]:
            if pr["blocking"] or pr["action"] == "error" or not pr.get("proposed"):
                continue
            pid = pr["product_id"]
            assert pid is not None
            p = pr["proposed"]
            existing_id = pr["current"]["assumption_id"] if pr["current"] else None

            if existing_id is None:
                row = CommercialSkuAssumption(
                    product_id=pid,
                    controlled_cost_amount=p["controlled_cost_amount"],
                    controlled_cost_currency_code=p["controlled_cost_currency_code"],
                    vat_rate_pct=p["vat_rate_pct"],
                    fx_plan_currency_per_cost_currency=p["fx_plan_currency_per_cost_currency"],
                    reserve_total_pct=p["reserve_total_pct"],
                    promo_reserve_split_pct=p["promo_reserve_split_pct"],
                )
                db.add(row)
                applied_creates += 1
            else:
                row = await db.get(CommercialSkuAssumption, existing_id)
                if not row:
                    raise RuntimeError(f"Missing assumption id={existing_id} during apply")
                row.controlled_cost_amount = p["controlled_cost_amount"]
                row.controlled_cost_currency_code = p["controlled_cost_currency_code"]
                row.vat_rate_pct = p["vat_rate_pct"]
                row.fx_plan_currency_per_cost_currency = p["fx_plan_currency_per_cost_currency"]
                row.reserve_total_pct = p["reserve_total_pct"]
                row.promo_reserve_split_pct = p["promo_reserve_split_pct"]
                applied_updates += 1

        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise

    return {
        "applied_creates": applied_creates,
        "applied_updates": applied_updates,
        "summary": preview["summary"],
    }
