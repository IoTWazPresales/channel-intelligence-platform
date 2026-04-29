"""Read-only helpers for commercial plan line API payloads (no DB writes)."""

from __future__ import annotations

import math
from typing import Any

from app.models.commercial_planner import CommercialPlanLine


def _flatten_specs_json(specs_json: dict[str, Any] | None) -> dict[str, Any]:
    """Merge top-level specs_json with import_staging nested dict when present (read-only)."""
    if not specs_json or not isinstance(specs_json, dict):
        return {}
    out: dict[str, Any] = dict(specs_json)
    nest = specs_json.get("import_staging") if isinstance(specs_json.get("import_staging"), dict) else None
    if nest is None and isinstance(specs_json.get("importStaging"), dict):
        nest = specs_json["importStaging"]
    if isinstance(nest, dict):
        for k, v in nest.items():
            ks = str(k)
            if ks not in out:
                out[ks] = v
    return out


def _pick_spec_value(flat: dict[str, Any], candidate_keys: tuple[str, ...]) -> str | None:
    """Return first non-empty string/number value for any candidate key (case-insensitive on flat keys)."""
    if not flat:
        return None
    lower_index: dict[str, Any] = {}
    for k, v in flat.items():
        lower_index[str(k).strip().lower()] = v
    for cand in candidate_keys:
        key = cand.strip().lower()
        if key not in lower_index:
            continue
        v = lower_index[key]
        if v is None:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v)):
            s = str(v).strip()
            if s:
                return s[:512]
        if isinstance(v, str):
            s = v.strip()
            if s:
                return s[:512]
    return None


def specs_json_flat_string_map(specs_json: dict[str, Any] | None, *, max_keys: int = 220) -> dict[str, str]:
    """Flatten specs_json to string values for optional grid columns (no nested objects)."""
    flat = _flatten_specs_json(specs_json)
    out: dict[str, str] = {}
    skip = frozenset({"import_staging", "importStaging"})
    for raw_k, v in flat.items():
        if len(out) >= max_keys:
            break
        k = str(raw_k).strip()
        if not k or k in skip:
            continue
        if isinstance(v, (dict, list)):
            continue
        if v is None:
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            if isinstance(v, float) and math.isnan(v):
                continue
            s = str(v).strip()
        elif isinstance(v, str):
            s = v.strip()
        else:
            continue
        if not s:
            continue
        out[k] = s[:512]
    return out


def product_specs_from_json(specs_json: dict[str, Any] | None) -> dict[str, str | None]:
    """Extract notebook-style specs only from structured specs_json keys (no inference)."""
    flat = _flatten_specs_json(specs_json)
    processor_detail = _pick_spec_value(
        flat,
        (
            "processor",
            "Processor",
            "processor model",
            "Processor Model",
            "processor type",
            "Processor Type",
            "processormodel",
            "processortype",
        ),
    )
    cpu_slot = _pick_spec_value(
        flat,
        (
            "cpu",
            "CPU",
            "proc",
            "chipset",
        ),
    )
    return {
        "product_spec_processor": processor_detail,
        "product_spec_cpu": cpu_slot,
        "product_spec_ram": _pick_spec_value(
            flat,
            ("ram", "RAM", "memory", "Memory", "system_memory", "systemMemory"),
        ),
        "product_spec_storage": _pick_spec_value(
            flat,
            ("storage", "Storage", "ssd", "SSD", "hdd", "HDD", "disk", "hard_drive", "hardDrive"),
        ),
        "product_spec_gpu": _pick_spec_value(
            flat,
            ("gpu", "GPU", "graphics", "Graphics", "video_card", "videoCard", "graphic"),
        ),
        "product_spec_display": _pick_spec_value(
            flat,
            ("display", "Display", "screen", "Screen", "panel", "lcd", "monitor_size", "monitorSize"),
        ),
        "product_spec_warranty": _pick_spec_value(
            flat,
            ("warranty", "Warranty", "warranty_months", "warrantyMonths"),
        ),
        "product_spec_os": _pick_spec_value(flat, ("os", "OS", "operating_system", "operatingSystem")),
        "product_spec_colour": _pick_spec_value(
            flat,
            ("colour", "color", "Colour", "Color", "finish", "Finish"),
        ),
    }


def effective_commercial_fields_flat(
    line: CommercialPlanLine,
    *,
    customer_margin_pct: float | None,
    customer_rebate_pct: float | None,
    distributor_margin_pct: float | None,
    sku_vat_rate_pct: float | None,
    sku_fx_rate_to_usd: float | None,
    sku_reserve_total_pct: float | None,
    sku_promo_reserve_split_pct: float | None,
    sku_landed_cost_usd: float | None,
) -> dict[str, float | None]:
    """Resolved inputs matching _resolve_terms_and_calc (null when no DB source and no line override)."""
    eff_cm = (
        float(line.override_customer_margin_pct)
        if line.override_customer_margin_pct is not None
        else (float(customer_margin_pct) if customer_margin_pct is not None else None)
    )
    eff_cr = (
        float(line.override_customer_rebate_pct)
        if line.override_customer_rebate_pct is not None
        else (float(customer_rebate_pct) if customer_rebate_pct is not None else None)
    )
    eff_dm = (
        float(line.override_distributor_margin_pct)
        if line.override_distributor_margin_pct is not None
        else (float(distributor_margin_pct) if distributor_margin_pct is not None else None)
    )
    eff_vat = (
        float(line.override_vat_rate_pct)
        if line.override_vat_rate_pct is not None
        else (float(sku_vat_rate_pct) if sku_vat_rate_pct is not None else None)
    )
    eff_fx = (
        float(line.override_fx_rate_to_usd)
        if line.override_fx_rate_to_usd is not None
        else (float(sku_fx_rate_to_usd) if sku_fx_rate_to_usd is not None else None)
    )
    eff_res = (
        float(line.override_reserve_total_pct)
        if line.override_reserve_total_pct is not None
        else (float(sku_reserve_total_pct) if sku_reserve_total_pct is not None else None)
    )
    eff_pr_split = (
        float(line.override_promo_reserve_split_pct)
        if line.override_promo_reserve_split_pct is not None
        else (float(sku_promo_reserve_split_pct) if sku_promo_reserve_split_pct is not None else None)
    )
    eff_cc = (
        float(line.override_landed_cost_usd)
        if line.override_landed_cost_usd is not None
        else (float(sku_landed_cost_usd) if sku_landed_cost_usd is not None else None)
    )
    return {
        "effective_customer_margin_pct": eff_cm,
        "effective_customer_rebate_pct": eff_cr,
        "effective_distributor_margin_pct": eff_dm,
        "effective_vat_rate_pct": eff_vat,
        "effective_fx_rate_to_usd": eff_fx,
        "effective_reserve_total_pct": eff_res,
        "effective_promo_reserve_split_pct": eff_pr_split,
        "effective_controlled_cost_usd_per_unit": eff_cc,
    }


def plan_line_read_model_extensions(
    line: CommercialPlanLine,
    specs_json: dict[str, Any] | None,
    *,
    customer_margin_pct: float | None,
    customer_rebate_pct: float | None,
    distributor_margin_pct: float | None,
    sku_vat_rate_pct: float | None,
    sku_fx_rate_to_usd: float | None,
    sku_reserve_total_pct: float | None,
    sku_promo_reserve_split_pct: float | None,
    sku_landed_cost_usd: float | None,
) -> dict[str, Any]:
    """Specs + effective commercial snapshot + local USD-derived prices (same FX convention as calculator)."""
    specs = product_specs_from_json(specs_json)
    eff = effective_commercial_fields_flat(
        line,
        customer_margin_pct=customer_margin_pct,
        customer_rebate_pct=customer_rebate_pct,
        distributor_margin_pct=distributor_margin_pct,
        sku_vat_rate_pct=sku_vat_rate_pct,
        sku_fx_rate_to_usd=sku_fx_rate_to_usd,
        sku_reserve_total_pct=sku_reserve_total_pct,
        sku_promo_reserve_split_pct=sku_promo_reserve_split_pct,
        sku_landed_cost_usd=sku_landed_cost_usd,
    )
    sell_usd = float(line.calc_sell_in_price_usd) if line.calc_sell_in_price_usd is not None else None
    buy_usd = float(line.calc_buy_price_usd) if line.calc_buy_price_usd is not None else None
    sell_l, buy_l = local_prices_from_usd(sell_usd, buy_usd, eff.get("effective_fx_rate_to_usd"))
    flat_specs = specs_json_flat_string_map(specs_json if isinstance(specs_json, dict) else None)
    out: dict[str, Any] = {
        **specs,
        **eff,
        "product_specs_flat": flat_specs,
        "calc_sell_in_price_local": sell_l,
        "calc_distributor_net_local": buy_l,
    }
    return out


def local_prices_from_usd(
    sell_in_usd: float | None,
    distributor_net_usd: float | None,
    fx_rate_to_usd: float | None,
) -> tuple[float | None, float | None]:
    """Convert USD model outputs to plan-currency local using the same FX convention as the calculator.

    Calculator: sell_in_usd = sell_in_local / max(fx_rate_to_usd, eps)
    => sell_in_local = sell_in_usd * fx_rate_to_usd (local monetary units per 1 USD).
    Same for distributor net USD.
    """
    if fx_rate_to_usd is None or fx_rate_to_usd <= 0:
        return None, None
    sell_l = round(float(sell_in_usd) * float(fx_rate_to_usd), 4) if sell_in_usd is not None else None
    buy_l = round(float(distributor_net_usd) * float(fx_rate_to_usd), 4) if distributor_net_usd is not None else None
    return sell_l, buy_l
