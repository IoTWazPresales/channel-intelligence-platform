"""CST unit ↔ total measure derivation (generic — any customer / layout).

When a report exposes a *line total* (sell amount, cost amount, SOH value) but not
the per-unit figure — or the reverse — derive the missing side using the matching
quantity:

* sell: ``unit_sell_price`` ↔ ``total_sell_amount`` via ``units_sold``
* cost: ``unit_cost`` ↔ ``total_cost_amount`` via ``units_sold``
* SOH value: ``unit_mac`` (preferred) / ``unit_cost`` ↔ ``total_soh_value`` via ``reported_soh``

Totals are not persisted on staging columns; they are recorded under
``raw_row_payload['_cst_derived']`` for audit. Unit fields remain the stored grain.
"""

from __future__ import annotations

from typing import Any


def _safe_div(total: float, qty: float) -> float | None:
    if qty == 0:
        return None
    try:
        return float(total) / float(qty)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _safe_mul(unit: float, qty: float) -> float | None:
    try:
        return float(unit) * float(qty)
    except (TypeError, ValueError):
        return None


def apply_unit_total_derivation(row: dict[str, Any]) -> dict[str, Any]:
    """Mutate *and* return ``row`` filling missing unit/total sides both ways."""
    derived: dict[str, Any] = {}
    units = row.get("units_sold")
    soh = row.get("reported_soh")

    unit_sell = row.get("unit_sell_price")
    total_sell = row.get("total_sell_amount")
    if unit_sell is None and total_sell is not None and units is not None:
        got = _safe_div(float(total_sell), float(units))
        if got is not None:
            row["unit_sell_price"] = got
            derived["unit_sell_price_from_total"] = True
    elif total_sell is None and unit_sell is not None and units is not None:
        got = _safe_mul(float(unit_sell), float(units))
        if got is not None:
            row["total_sell_amount"] = got
            derived["total_sell_amount_from_unit"] = True

    unit_cost = row.get("unit_cost")
    total_cost = row.get("total_cost_amount")
    if unit_cost is None and total_cost is not None and units is not None:
        got = _safe_div(float(total_cost), float(units))
        if got is not None:
            row["unit_cost"] = got
            derived["unit_cost_from_total"] = True
    elif total_cost is None and unit_cost is not None and units is not None:
        got = _safe_mul(float(unit_cost), float(units))
        if got is not None:
            row["total_cost_amount"] = got
            derived["total_cost_amount_from_unit"] = True

    # SOH value uses stock qty, not sell units. Prefer unit_mac, else unit_cost.
    total_soh = row.get("total_soh_value")
    unit_mac = row.get("unit_mac")
    if total_soh is not None and soh is not None and unit_mac is None:
        got = _safe_div(float(total_soh), float(soh))
        if got is not None:
            row["unit_mac"] = got
            derived["unit_mac_from_total_soh"] = True
            if row.get("unit_cost") is None:
                row["unit_cost"] = got
                derived["unit_cost_from_total_soh"] = True
    if row.get("total_soh_value") is None and soh is not None:
        mac = row.get("unit_mac") if row.get("unit_mac") is not None else row.get("unit_cost")
        if mac is not None:
            got = _safe_mul(float(mac), float(soh))
            if got is not None:
                row["total_soh_value"] = got
                derived["total_soh_value_from_unit"] = True

    if derived:
        payload = row.get("raw_row_payload")
        if not isinstance(payload, dict):
            payload = {}
            row["raw_row_payload"] = payload
        audit = dict(payload.get("_cst_derived") or {})
        audit.update(derived)
        for key in ("total_sell_amount", "total_cost_amount", "total_soh_value"):
            if row.get(key) is not None:
                audit[key] = row.get(key)
        payload["_cst_derived"] = audit

    # Drop ephemeral total keys from the row dict before ORM insert (staging has no cols).
    row.pop("total_sell_amount", None)
    row.pop("total_cost_amount", None)
    row.pop("total_soh_value", None)
    return row


def apply_unit_total_derivation_many(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply_unit_total_derivation(r) for r in rows]
