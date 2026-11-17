"""Write a promotion plan in a stored mapping profile's column layout.

The frozen 32-column workbook stays in ``export_xlsx``. This module reads the
profile the historical import already stores and writes those headers back.
It does not parse or apply a historical workbook.
"""

from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.cpor import CporCase, CporCaseLine
from app.models.cpor_historical import CporHistoricalMappingProfile
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.services.cpor.pivot import is_voided_line
from app.services.export_literal_guard import force_text_cells


COLUMN_ORDER_KEY = "column_order"
# Older stored profiles have aliases but no explicit order. Use a generic,
# stable layout rather than JSONB object order (which PostgreSQL may change).
GENERIC_COLUMN_ORDER = (
    "case_code", "case_name", "customer_token", "promotion_type",
    "window_start", "window_end", "status", "sales_model_token",
    "distributor_token", "pod_quarter", "product_line", "soh_snapshot",
    "estimate_qty", "result_qty", "srp", "vat_rate", "dealer_margin_pct",
    "dealer_price", "cost_basis", "support_unit", "ttl_support",
    "roe_snapshot", "support_usd", "ttl_support_usd", "ttl_result",
    "ttl_result_usd", "remark",
)


def sheet_role_for_channel(channel: str | None) -> str:
    """Case channel selects the sheet role. A distributor case is never a reseller sheet."""
    text = str(channel or "reseller").strip().lower()
    if text in {"disti", "distributor"}:
        return "disti"
    return "reseller"


def column_order_from_map(column_map: Any) -> list[str]:
    """Workbook column order stored as a list.

    PostgreSQL JSONB does not keep object key order. An array does.
    """
    if isinstance(column_map, list):
        order: list[str] = []
        for item in column_map:
            if isinstance(item, str):
                order.append(item)
            elif isinstance(item, dict):
                name = item.get("canonical") or item.get("field")
                if name:
                    order.append(str(name))
            elif isinstance(item, (list, tuple)) and item:
                order.append(str(item[0]))
        return [name for name in order if name != COLUMN_ORDER_KEY]
    if isinstance(column_map, dict):
        raw = column_map.get(COLUMN_ORDER_KEY)
        if isinstance(raw, list):
            return [str(item) for item in raw if str(item) != COLUMN_ORDER_KEY]
    return []


def _alias_map(column_map: Any) -> dict[str, list[Any]]:
    if isinstance(column_map, list):
        out: dict[str, list[Any]] = {}
        for item in column_map:
            canonical = None
            aliases: Any = []
            if isinstance(item, dict):
                canonical = item.get("canonical") or item.get("field")
                aliases = item.get("aliases") or item.get("headers") or []
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                canonical, aliases = item[0], item[1]
            if canonical and str(canonical) != COLUMN_ORDER_KEY:
                out[str(canonical)] = list(aliases or [])
        return out
    if isinstance(column_map, dict):
        return {
            str(key): list(value or [])
            for key, value in column_map.items()
            if str(key) != COLUMN_ORDER_KEY and isinstance(value, list)
        }
    return {}


def layout_columns(
    column_map: Any,
    column_order: list[Any] | None = None,
) -> list[tuple[str, str]]:
    """First unused header alias in explicit order, or generic order for older maps."""
    aliases = _alias_map(column_map)
    order = [str(item) for item in (column_order or []) if str(item) != COLUMN_ORDER_KEY]
    if not order:
        order = column_order_from_map(column_map)
    if not order:
        order = [name for name in GENERIC_COLUMN_ORDER if name in aliases]
        order.extend(sorted(set(aliases) - set(order)))
    columns: list[tuple[str, str]] = []
    used: set[str] = set()
    for canonical in order:
        header = None
        for alias in aliases.get(canonical) or []:
            text = str(alias).replace("\xa0", " ").strip()
            if text and text not in used:
                header = text
                break
        if header is None:
            continue
        used.add(header)
        columns.append((canonical, header))
    return columns


def export_sheet(sheet_roles: dict[str, Any] | None, channel: str | None = None) -> tuple[str, str]:
    """The sheet whose role is this case's channel. No cross-channel fallback."""
    wanted = sheet_role_for_channel(channel)
    for name, role in dict(sheet_roles or {}).items():
        if str(role).strip().lower() == wanted:
            return str(name), wanted
    raise ValueError("no_export_sheet")


def render_profile_workbook(profile: dict[str, Any], rows: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    """Return xlsx bytes and a small description. Raises ValueError on an unusable profile."""
    columns = layout_columns(profile.get("column_map_json"), profile.get("column_order"))
    if not columns:
        raise ValueError("empty_column_map")
    if not any(canonical == "case_code" for canonical, _header in columns):
        raise ValueError("missing_case_code_column")
    sheet_name, role = export_sheet(profile.get("sheet_roles_json"), profile.get("channel"))
    if len(sheet_name) > 31:
        raise ValueError("sheet_name_too_long")
    header_row_index = int(profile.get("header_row_index") or 0)
    if header_row_index < 0:
        raise ValueError("bad_header_row_index")

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name
    for _blank in range(header_row_index):
        ws.append([None])
    ws.append([header for _canonical, header in columns])
    for row in rows:
        ws.append([_cell(row.get(canonical)) for canonical, _header in columns])

    force_text_cells(wb)
    buf = BytesIO()
    wb.save(buf)
    data = buf.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    return data, {
        "profile_code": profile.get("profile_code"),
        "display_name": profile.get("display_name"),
        "sheet": sheet_name,
        "role": role,
        "headers": [header for _canonical, header in columns],
        "line_count": len(rows),
        "checksum_sha256": digest,
        "layout": "mapping_profile",
    }


def _cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def profile_as_dict(row: CporHistoricalMappingProfile) -> dict[str, Any]:
    raw_map = row.column_map_json or {}
    return {
        "profile_code": row.profile_code,
        "display_name": row.display_name,
        "header_row_index": int(row.header_row_index or 0),
        "sheet_roles_json": dict(row.sheet_roles_json or {}),
        "column_map_json": _alias_map(raw_map),
        "column_order": column_order_from_map(raw_map),
    }


def load_mapping_profile(
    session: Session,
    profile_code: str | None = None,
) -> CporHistoricalMappingProfile | None:
    if profile_code:
        return session.scalar(
            select(CporHistoricalMappingProfile).where(
                CporHistoricalMappingProfile.profile_code == profile_code
            )
        )
    default = session.scalar(
        select(CporHistoricalMappingProfile)
        .where(CporHistoricalMappingProfile.is_default.is_(True))
        .order_by(CporHistoricalMappingProfile.id.asc())
        .limit(1)
    )
    if default is not None:
        return default
    return session.scalar(
        select(CporHistoricalMappingProfile).order_by(CporHistoricalMappingProfile.id.asc()).limit(1)
    )


def _label(name: str | None, code: str | None, fallback: str) -> str:
    text = (name or "").strip() or (code or "").strip()
    return text or fallback


def canonical_rows_for_case(session: Session, case_id: int) -> list[dict[str, Any]]:
    case = session.get(CporCase, int(case_id))
    if case is None:
        raise ValueError("case_not_found")
    customer = session.get(DimCustomer, case.customer_id)
    lines = list(
        session.scalars(
            select(CporCaseLine).where(CporCaseLine.case_id == case.id).order_by(CporCaseLine.id.asc())
        ).all()
    )
    exportable = [line for line in lines if not is_voided_line(line) and float(line.estimate_qty or 0) != 0.0]
    if not exportable:
        raise ValueError("no_exportable_lines")
    products = {
        int(row.id): row
        for row in session.scalars(
            select(DimProduct).where(DimProduct.id.in_([int(line.product_id) for line in exportable]))
        ).all()
    }
    dist_ids = [int(line.distributor_id) for line in exportable if line.distributor_id is not None]
    distributors = (
        {
            int(row.id): row
            for row in session.scalars(select(DimDistributor).where(DimDistributor.id.in_(dist_ids))).all()
        }
        if dist_ids
        else {}
    )
    customer_token = _label(
        getattr(customer, "name", None),
        getattr(customer, "code", None),
        str(case.customer_id),
    )
    rows: list[dict[str, Any]] = []
    for line in exportable:
        product = products.get(int(line.product_id))
        distributor = distributors.get(int(line.distributor_id)) if line.distributor_id is not None else None
        sales_model = None
        product_line = None
        if product is not None:
            sales_model = (product.sales_model_name or "").strip() or (product.sku or "").strip() or None
            product_line = product.product_line
        dist_token = None
        if distributor is not None:
            dist_token = _label(getattr(distributor, "name", None), getattr(distributor, "code", None), "")
        rows.append(
            {
                "case_code": case.case_code,
                "case_name": case.case_name,
                "customer_token": customer_token,
                "promotion_type": case.promotion_type,
                "window_start": case.window_start.isoformat() if case.window_start else None,
                "window_end": case.window_end.isoformat() if case.window_end else None,
                "status": case.status,
                "sales_model_token": sales_model,
                "distributor_token": dist_token,
                "pod_quarter": line.pod_quarter,
                "product_line": product_line,
                "srp": _number(line.srp),
                "estimate_qty": _number(line.estimate_qty),
                "result_qty": _number(line.result_qty),
                "cost_basis": _number(line.cost_basis),
                "support_unit": _number(line.support_unit),
                "ttl_support": _number(line.ttl_support),
                "dealer_margin_pct": _number(line.dealer_margin_pct),
                "dealer_price": _number(line.dealer_price),
                "soh_snapshot": _number(line.soh_snapshot),
                "vat_rate": _number(line.vat_rate),
                "roe_snapshot": _number(case.roe_snapshot),
                "support_usd": _number(line.support_usd),
                "ttl_support_usd": _number(line.ttl_support_usd),
                "ttl_result": _number(line.ttl_result),
                "ttl_result_usd": _number(line.ttl_result_usd),
                "remark": line.remark,
            }
        )
    return rows


def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def build_case_profile_workbook(
    session: Session,
    case_id: int,
    *,
    profile_code: str | None = None,
) -> tuple[bytes, dict[str, Any]]:
    profile = load_mapping_profile(session, profile_code)
    if profile is None:
        raise ValueError("no_mapping_profile")
    case = session.get(CporCase, int(case_id))
    if case is None:
        raise ValueError("case_not_found")
    payload = profile_as_dict(profile)
    payload["channel"] = case.channel
    rows = canonical_rows_for_case(session, case_id)
    return render_profile_workbook(payload, rows)
