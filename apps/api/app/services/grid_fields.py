"""Grid field registry: one source for a fact grid's optional columns and the row keys behind them (N-0034).

A grid's picker list comes from ``grid_field_items`` and its rows get ``fact_row_dict`` merged
under the endpoint's own dict (existing keys win), so every field the picker offers is in the
payload. ``tests/test_grid_fields.py`` guards that (catalog fields are a subset of serialized keys).

Reference fields (customer / distributor code and name) are joined labels, not mapper columns;
they are always ``default_hidden`` and live in their own group so identity cells stay name-only (D7).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.types import JSON

from app.models.derived import PricingRecommendation
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.fact_demand_forecast import FactDemandForecast
from app.models.facts import (
    FactBuyPlan,
    FactInboundShipment,
    FactInventoryCustomer,
    FactPricing,
    FactProductRoadmap,
    FactSalesSellout,
)

# Never offered and never merged into rows: tenant scoping, raw source payloads, resolver tokens.
_ALWAYS_HIDDEN: frozenset[str] = frozenset({"tenant_id", "raw_source_row"})

CUSTOMER_REFERENCE: tuple[tuple[str, str], ...] = (
    ("customer_name", "Customer"),
    ("customer_code", "Customer code"),
)
DISTRIBUTOR_REFERENCE: tuple[tuple[str, str], ...] = (
    ("distributor_name", "Distributor"),
    ("distributor_code", "Distributor code"),
)
CUSTOMER_CODE_REFERENCE: tuple[tuple[str, str], ...] = (("customer_code", "Customer code"),)
DISTRIBUTOR_CODE_REFERENCE: tuple[tuple[str, str], ...] = (("distributor_code", "Distributor code"),)

# Inbound shipments keep their historical list (every mapper column minus the default grid cells).
INBOUND_GRID_DEFAULT_FACT_KEYS: frozenset[str] = frozenset(
    {
        "line_state",
        "status",
        "eta_date",
        "promise_date",
        "pod_date",
        "sales_model_name",
        "item_code",
        "bill_to_raw",
        "ship_to_raw",
    }
)
INBOUND_OPTIONAL_LABEL_OVERRIDES: dict[str, str] = {
    "customer_dealer_token": "Customer remarks (source)",
}


@dataclass(frozen=True)
class GridFieldSpec:
    """One grid's optional-field contract.

    ``model``: the ORM fact behind the rows (None for computed rows, which declare ``static_keys``).
    ``default_keys``: model keys already shown as default columns (not offered as toggles).
    ``joined_extras``: (field, label) reference fields the endpoint joins in batches.
    ``hidden_internal``: model keys never offered or merged (on top of tenant/raw/token/JSON rules).
    ``auto_hide``: apply the ``*_token`` / JSON-column rules; off only for inbound's legacy list.
    """

    model: type | None
    default_keys: frozenset[str] = frozenset()
    joined_extras: tuple[tuple[str, str], ...] = ()
    hidden_internal: frozenset[str] = frozenset()
    label_overrides: dict[str, str] = field(default_factory=dict)
    static_keys: tuple[tuple[str, str], ...] = ()
    auto_hide: bool = True


GRID_FIELDS: dict[str, GridFieldSpec] = {
    "inbound-shipments": GridFieldSpec(
        model=FactInboundShipment,
        default_keys=INBOUND_GRID_DEFAULT_FACT_KEYS,
        joined_extras=CUSTOMER_CODE_REFERENCE + DISTRIBUTOR_CODE_REFERENCE,
        label_overrides=INBOUND_OPTIONAL_LABEL_OVERRIDES,
        auto_hide=False,
    ),
    "sellout.commercial-lines": GridFieldSpec(
        model=FactSalesSellout,
        default_keys=frozenset({"period_start", "units", "revenue"}),
        joined_extras=CUSTOMER_CODE_REFERENCE + DISTRIBUTOR_CODE_REFERENCE,
    ),
    "inventory.customer": GridFieldSpec(
        model=FactInventoryCustomer,
        default_keys=frozenset({"as_of_date", "on_hand_units", "on_order_units"}),
        joined_extras=CUSTOMER_CODE_REFERENCE,
    ),
    "pricing.facts": GridFieldSpec(
        model=FactPricing,
        default_keys=frozenset({"effective_date", "list_price", "net_price"}),
        joined_extras=CUSTOMER_REFERENCE,
    ),
    "pricing.recommendations": GridFieldSpec(
        model=PricingRecommendation,
        default_keys=frozenset({"suggested_state", "explanation_summary", "confidence"}),
        # reviewed_by names a person (user id / email) — [PII]-like, not a grid column.
        hidden_internal=frozenset({"reviewed_by"}),
    ),
    "buy-plans": GridFieldSpec(
        model=FactBuyPlan,
        default_keys=frozenset(
            {"recommended_qty", "recommended_window_start", "recommended_window_end", "rationale"}
        ),
        joined_extras=DISTRIBUTOR_REFERENCE,
    ),
    "roadmap": GridFieldSpec(
        model=FactProductRoadmap,
        default_keys=frozenset({"lifecycle_phase", "whitespace_flag", "overlap_flag", "launch_target"}),
    ),
    "forecasts": GridFieldSpec(
        model=FactDemandForecast,
        default_keys=frozenset(
            {
                "period_start",
                "forecast_units",
                "method",
                "velocity_basis",
                "seasonal_index",
                "analogue_product_id",
                "analogue_basis",
                "lower_band",
                "upper_band",
                "confidence_level",
                "is_override",
            }
        ),
        joined_extras=CUSTOMER_REFERENCE + DISTRIBUTOR_REFERENCE,
    ),
}


def human_column_label(key: str) -> str:
    return re.sub(r"_+", " ", key).strip().title()


def get_spec(grid_id: str) -> GridFieldSpec | None:
    return GRID_FIELDS.get(grid_id)


def _is_hidden(spec: GridFieldSpec, key: str, col_type: Any) -> bool:
    if spec.auto_hide:
        if key in _ALWAYS_HIDDEN or key.endswith("_token") or isinstance(col_type, JSON):
            return True
    elif key == "tenant_id":
        return True
    return key in spec.hidden_internal


def model_field_keys(spec: GridFieldSpec) -> list[str]:
    """Mapper keys of ``spec.model`` that may appear in rows (default and optional), sorted."""
    if spec.model is None:
        return []
    out: list[str] = []
    for attr in sa_inspect(spec.model).column_attrs:
        col_type = attr.columns[0].type if attr.columns else None
        if not _is_hidden(spec, attr.key, col_type):
            out.append(attr.key)
    return sorted(out)


def grid_field_items(spec: GridFieldSpec) -> list[dict[str, Any]]:
    """Picker list: optional fact fields, then reference fields; all hidden by default."""
    items: list[dict[str, Any]] = []
    fact_keys = [k for k in model_field_keys(spec) if k not in spec.default_keys]
    fact_keys += [k for k, _ in spec.static_keys if k not in spec.default_keys]
    static_labels = dict(spec.static_keys)
    for k in fact_keys:
        label = spec.label_overrides.get(k) or static_labels.get(k) or human_column_label(k)
        items.append({"field": k, "label": label, "group": "fact", "default_hidden": True})
    for k, label in spec.joined_extras:
        items.append({"field": k, "label": label, "group": "reference", "default_hidden": True})
    return items


def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def fact_row_dict(row: Any, grid_id: str, *, exclude: frozenset[str] = frozenset()) -> dict[str, Any]:
    """Every offered mapper column of ``row``; merge UNDER the endpoint's dict (``{**fact_row_dict(...), **own}``).

    ``exclude`` drops keys the endpoint emits on request only (inbound's opt-in ``raw_source_row``).
    """
    spec = GRID_FIELDS[grid_id]
    return {k: _json_safe(getattr(row, k, None)) for k in model_field_keys(spec) if k not in exclude}


async def customer_labels(db: AsyncSession, ids: Iterable[int | None]) -> dict[int, tuple[str, str]]:
    """``{customer_id: (code, name)}`` in one query (no per-row lookups)."""
    wanted = sorted({int(i) for i in ids if i is not None})
    if not wanted:
        return {}
    res = await db.execute(select(DimCustomer.id, DimCustomer.code, DimCustomer.name).where(DimCustomer.id.in_(wanted)))
    return {int(r[0]): (r[1], r[2]) for r in res.all()}


async def distributor_labels(db: AsyncSession, ids: Iterable[int | None]) -> dict[int, tuple[str, str]]:
    """``{distributor_id: (code, name)}`` in one query (no per-row lookups)."""
    wanted = sorted({int(i) for i in ids if i is not None})
    if not wanted:
        return {}
    res = await db.execute(
        select(DimDistributor.id, DimDistributor.code, DimDistributor.name).where(DimDistributor.id.in_(wanted))
    )
    return {int(r[0]): (r[1], r[2]) for r in res.all()}


def reference_fields(
    *,
    customer_id: int | None = None,
    customers: dict[int, tuple[str, str]] | None = None,
    distributor_id: int | None = None,
    distributors: dict[int, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Reference keys for one row from pre-loaded label maps (keys present even when unresolved)."""
    out: dict[str, Any] = {}
    if customers is not None:
        code, name = customers.get(int(customer_id), (None, None)) if customer_id is not None else (None, None)
        out["customer_code"] = code
        out["customer_name"] = name
    if distributors is not None:
        code, name = distributors.get(int(distributor_id), (None, None)) if distributor_id is not None else (None, None)
        out["distributor_code"] = code
        out["distributor_name"] = name
    return out
