"""Read-only helpers for commercial plan line API payloads (no DB writes)."""

from __future__ import annotations

import math
from typing import Any

from app.models.commercial_planner import CommercialPlanLine

from app.services.commercial_planner.economics_trust import classify_line_economics_trust


def _flatten_specs_json(specs_json: dict[str, Any] | None) -> dict[str, Any]:
    """Merge top-level specs_json with nested import_staging / attribute_candidates dicts (read-only).

    Both nested containers hold raw file columns captured at commit (stage_raw and
    attribute_candidate dispositions). Flattening them up surfaces those columns as
    optional grid columns and planner specs. Top-level keys win over nested ones.
    """
    if not specs_json or not isinstance(specs_json, dict):
        return {}
    out: dict[str, Any] = dict(specs_json)
    for primary, alias in (("import_staging", "importStaging"), ("attribute_candidates", None)):
        nest = specs_json.get(primary) if isinstance(specs_json.get(primary), dict) else None
        if nest is None and alias and isinstance(specs_json.get(alias), dict):
            nest = specs_json[alias]
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
    skip = frozenset({"import_staging", "importStaging", "attribute_candidates"})
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
    sku_fx_plan_currency_per_cost_currency: float | None,
    sku_reserve_total_pct: float | None,
    sku_promo_reserve_split_pct: float | None,
    sku_controlled_cost_amount: float | None,
    sku_controlled_cost_currency_code: str | None,
) -> dict[str, float | str | None]:
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
        float(line.override_fx_plan_currency_per_cost_currency)
        if line.override_fx_plan_currency_per_cost_currency is not None
        else (
            float(sku_fx_plan_currency_per_cost_currency)
            if sku_fx_plan_currency_per_cost_currency is not None
            else None
        )
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
        float(line.override_controlled_cost_amount)
        if line.override_controlled_cost_amount is not None
        else (float(sku_controlled_cost_amount) if sku_controlled_cost_amount is not None else None)
    )
    if line.override_controlled_cost_amount is not None:
        eff_ccy = (line.override_controlled_cost_currency_code or "").strip() or (
            (line.economics_calc_currency_code or "").strip() or "USD"
        )
    else:
        eff_ccy = (sku_controlled_cost_currency_code or "").strip() or (
            (line.economics_calc_currency_code or "").strip() or "USD"
        )
    return {
        "effective_customer_margin_pct": eff_cm,
        "effective_customer_rebate_pct": eff_cr,
        "effective_distributor_margin_pct": eff_dm,
        "effective_vat_rate_pct": eff_vat,
        "effective_fx_plan_currency_per_cost_currency": eff_fx,
        "effective_reserve_total_pct": eff_res,
        "effective_promo_reserve_split_pct": eff_pr_split,
        "effective_controlled_cost_amount": eff_cc,
        "effective_controlled_cost_currency_code": eff_ccy,
    }


def _field_provenance(
    line: CommercialPlanLine,
    *,
    join_customer_term_present: bool,
    join_distributor_term_present: bool,
    join_sku_assumption_present: bool,
) -> dict[str, dict[str, str | bool]]:
    """Source labels for waterfall / trust UI (no new DB fields)."""

    def prov_entry(
        *,
        override_set: bool,
        term_present: bool,
        sku_field: bool,
        placeholder_flag: str | None = None,
    ) -> dict[str, str | bool]:
        if override_set:
            return {"source": "line_override", "trusted": True}
        if sku_field and join_sku_assumption_present:
            return {"source": "sku_economics_input", "trusted": True}
        if not sku_field and term_present:
            return {"source": "planner_default_terms", "trusted": True}
        if sku_field and not join_sku_assumption_present:
            return {
                "source": "placeholder_or_missing",
                "trusted": False,
                "detail": placeholder_flag or "missing_sku_assumption",
            }
        if not sku_field and not term_present:
            return {"source": "missing", "trusted": False}
        return {"source": "unknown", "trusted": False}

    sku_f = join_sku_assumption_present
    return {
        "customer_margin_pct": prov_entry(
            override_set=line.override_customer_margin_pct is not None,
            term_present=join_customer_term_present,
            sku_field=False,
        ),
        "customer_rebate_pct": prov_entry(
            override_set=line.override_customer_rebate_pct is not None,
            term_present=join_customer_term_present,
            sku_field=False,
        ),
        "distributor_margin_pct": prov_entry(
            override_set=line.override_distributor_margin_pct is not None,
            term_present=join_distributor_term_present,
            sku_field=False,
        ),
        "vat_rate_pct": prov_entry(
            override_set=line.override_vat_rate_pct is not None,
            term_present=False,
            sku_field=True,
            placeholder_flag="economics_placeholder_vat_without_sku",
        ),
        "fx_plan_currency_per_cost_currency": prov_entry(
            override_set=line.override_fx_plan_currency_per_cost_currency is not None,
            term_present=False,
            sku_field=True,
            placeholder_flag="economics_placeholder_fx_without_sku",
        ),
        "reserve_total_pct": prov_entry(
            override_set=line.override_reserve_total_pct is not None,
            term_present=False,
            sku_field=True,
            placeholder_flag="economics_placeholder_reserves_without_sku",
        ),
        "promo_reserve_split_pct": prov_entry(
            override_set=line.override_promo_reserve_split_pct is not None,
            term_present=False,
            sku_field=True,
            placeholder_flag="economics_placeholder_reserves_without_sku",
        ),
        "controlled_cost_amount": prov_entry(
            override_set=line.override_controlled_cost_amount is not None,
            term_present=False,
            sku_field=True,
            placeholder_flag="missing_sku_assumption",
        ),
    }


def plan_line_read_model_extensions(
    line: CommercialPlanLine,
    specs_json: dict[str, Any] | None,
    *,
    customer_margin_pct: float | None,
    customer_rebate_pct: float | None,
    distributor_margin_pct: float | None,
    sku_vat_rate_pct: float | None,
    sku_fx_plan_currency_per_cost_currency: float | None,
    sku_reserve_total_pct: float | None,
    sku_promo_reserve_split_pct: float | None,
    sku_controlled_cost_amount: float | None,
    sku_controlled_cost_currency_code: str | None,
    join_customer_term_present: bool = False,
    join_distributor_term_present: bool = False,
    join_sku_assumption_present: bool = False,
    distributor_code: str | None = None,
) -> dict[str, Any]:
    """Specs + effective commercial snapshot + plan-currency local amounts (same FX convention as calculator)."""
    specs = product_specs_from_json(specs_json)
    eff = effective_commercial_fields_flat(
        line,
        customer_margin_pct=customer_margin_pct,
        customer_rebate_pct=customer_rebate_pct,
        distributor_margin_pct=distributor_margin_pct,
        sku_vat_rate_pct=sku_vat_rate_pct,
        sku_fx_plan_currency_per_cost_currency=sku_fx_plan_currency_per_cost_currency,
        sku_reserve_total_pct=sku_reserve_total_pct,
        sku_promo_reserve_split_pct=sku_promo_reserve_split_pct,
        sku_controlled_cost_amount=sku_controlled_cost_amount,
        sku_controlled_cost_currency_code=sku_controlled_cost_currency_code,
    )
    sell_econ = float(line.calc_oem_sell_in_amount) if line.calc_oem_sell_in_amount is not None else None
    buy_econ = float(line.calc_distributor_net_amount) if line.calc_distributor_net_amount is not None else None
    sell_l, buy_l = local_prices_from_economics_amounts(
        sell_econ, buy_econ, eff.get("effective_fx_plan_currency_per_cost_currency")
    )
    flat_specs = specs_json_flat_string_map(specs_json if isinstance(specs_json, dict) else None)
    flags_for_trust = list(line.calc_flags or [])
    if distributor_code and distributor_code.strip().upper() == "UNASSIGNED":
        if "unassigned_distributor_placeholder" not in flags_for_trust:
            flags_for_trust.append("unassigned_distributor_placeholder")
    trust_tier, trust_reasons = classify_line_economics_trust(flags_for_trust)
    provenance = _field_provenance(
        line,
        join_customer_term_present=join_customer_term_present,
        join_distributor_term_present=join_distributor_term_present,
        join_sku_assumption_present=join_sku_assumption_present,
    )
    out: dict[str, Any] = {
        **specs,
        **eff,
        "product_specs_flat": flat_specs,
        "calc_sell_in_price_local": sell_l,
        "calc_distributor_net_local": buy_l,
        "economics_line_trust": trust_tier,
        "economics_line_trust_reasons": trust_reasons,
        "economics_field_provenance": provenance,
    }
    return out


def local_prices_from_economics_amounts(
    sell_in_economics_ccy: float | None,
    distributor_net_economics_ccy: float | None,
    fx_plan_currency_per_cost_currency: float | None,
) -> tuple[float | None, float | None]:
    """Convert economics-currency amounts to plan-currency local using the same FX convention as the calculator.

    Calculator: sell_in_econ = sell_in_local / max(fx_plan_currency_per_cost_currency, eps)
    => sell_in_local = sell_in_econ * fx_plan_currency_per_cost_currency
    (plan currency units per 1 unit of economics / cost currency).
    """
    if fx_plan_currency_per_cost_currency is None or fx_plan_currency_per_cost_currency <= 0:
        return None, None
    sell_l = (
        round(float(sell_in_economics_ccy) * float(fx_plan_currency_per_cost_currency), 4)
        if sell_in_economics_ccy is not None
        else None
    )
    buy_l = (
        round(float(distributor_net_economics_ccy) * float(fx_plan_currency_per_cost_currency), 4)
        if distributor_net_economics_ccy is not None
        else None
    )
    return sell_l, buy_l
