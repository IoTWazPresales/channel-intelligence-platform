"""N-0116 S14: three starter dashboards, defined in code and created on demand (spec s.7).

Nothing is seeded: ``POST /dashboards/from-template {key}`` creates a personal dashboard for the
caller with ``template_key`` set, the starter's ``filters_json`` and its widgets. Every widget's
``definition_v2`` is checked with the v2 planner before anything is written. Only measures and
breakdowns in the v2 catalog are used. What is left out names the catalog's own pending reasons.
Layouts are x, y, w, h on the 12-column grid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.query.model.loader import DataModel, default_model


@dataclass(frozen=True)
class TemplateWidget:
    title: str
    visual: str
    measures: tuple[str, ...]
    breakdowns: tuple[str, ...] = ()
    grain: str | None = None
    layout: tuple[int, int, int, int] = (0, 0, 6, 8)
    display: dict[str, Any] = field(default_factory=dict)
    sort: tuple[str, str] | None = None

    def definition(self) -> dict[str, Any]:
        query: dict[str, Any] = {"measures": list(self.measures), "breakdowns": list(self.breakdowns)}
        if self.grain:
            query["period"] = {"grain": self.grain}
        if self.sort:
            query["sort"] = {"by": self.sort[0], "dir": self.sort[1]}
        out: dict[str, Any] = {"v": 1, "query": query}
        if self.display:
            out["display"] = dict(self.display)
        return out

    def layout_json(self) -> dict[str, int]:
        x, y, w, h = self.layout
        return {"x": x, "y": y, "w": w, "h": h}


@dataclass(frozen=True)
class LeftOut:
    what: str
    reason: str | None = None  # fixed text; or
    pending: str | None = None  # a catalog pending id whose reason is shown


@dataclass(frozen=True)
class Template:
    key: str
    title: str
    description: str
    filters_json: dict[str, Any]
    widgets: tuple[TemplateWidget, ...]
    left_out: tuple[LeftOut, ...]


_KPI_SPARK = {"kpi": {"compare": True, "sparkline": True}}
_KPI_COMPARE = {"kpi": {"compare": True, "sparkline": False}}
_KPI_PLAIN = {"kpi": {"compare": False, "sparkline": False}}
_TOP15 = {"top_n": 15}

_EMPTY_VALUES = {"customer": [], "distributor": [], "product": [], "bu": [], "channel": [], "region": []}

CST = "cst_sellthrough"

TEMPLATES: tuple[Template, ...] = (
    Template(
        key="account_overview",
        title="Account overview",
        description=(
            "One retailer's own sell-through: what it sold, its weekly rate, its latest reported stock, "
            "which products and stores sell, and stock beside rate for each product. Pick a customer above."
        ),
        filters_json={
            "date": {"preset": "last_52_weeks", "from": None, "to": None},
            "compare": "previous_period",
            **_EMPTY_VALUES,
            "required": ["customer"],
        },
        widgets=(
            TemplateWidget("Sell-through units", "kpi", (f"{CST}.units",), layout=(0, 0, 3, 5), display=_KPI_SPARK),
            TemplateWidget("Units per week", "kpi", (f"{CST}.units_per_week",), layout=(3, 0, 3, 5), display=_KPI_COMPARE),
            TemplateWidget(
                "Reported stock on hand (latest report)", "kpi", (f"{CST}.reported_soh",), layout=(6, 0, 3, 5),
                display={**_KPI_PLAIN, "caption": "as of latest report on or before {to}"},
            ),
            TemplateWidget("Stores / sites reporting", "kpi", (f"{CST}.stores_reporting",), layout=(9, 0, 3, 5), display=_KPI_PLAIN),
            TemplateWidget("Sell-through units by week", "line", (f"{CST}.units",), ("period",), "week", (0, 5, 8, 8)),
            TemplateWidget("Top products", "hbar", (f"{CST}.units",), ("product",), layout=(8, 5, 4, 8), display=_TOP15),
            TemplateWidget(
                "Stock beside sell-through, by product", "table",
                (f"{CST}.units", f"{CST}.units_per_week", f"{CST}.reported_soh"), ("product",),
                layout=(0, 13, 12, 10), sort=(f"{CST}.units", "desc"),
            ),
            TemplateWidget("Sell-through by store / site", "hbar", (f"{CST}.units",), ("site_label",), layout=(0, 23, 12, 8), display=_TOP15),
        ),
        left_out=(
            LeftOut("Stock cover", pending=f"{CST}.stock_cover"),
            LeftOut("Restock flags", pending=f"{CST}.restock_flag"),
            LeftOut("Sales value", pending=f"{CST}.value"),
            LeftOut(
                "DSI sell-out to this customer as a dealer",
                reason="A distributor's dealer is a different customer role from a retailer reporting its own sales; add a DSI widget by hand.",
            ),
            LeftOut("Colour rules on the stock table", reason="No agreed threshold, so no colour rule is set."),
        ),
    ),
    Template(
        key="sellthrough_stock",
        title="Sell-through & stock across customers",  # D4 (proposed): no cover figure exists yet
        description=(
            "Sell-through and latest reported stock for each retailer, side by side, and the monthly trend."
        ),
        filters_json={
            "date": {"preset": "last_52_weeks", "from": None, "to": None},
            "compare": "previous_period",
            **_EMPTY_VALUES,
            "required": [],
        },
        widgets=(
            TemplateWidget("Sell-through units", "kpi", (f"{CST}.units",), layout=(0, 0, 4, 5), display=_KPI_SPARK),
            TemplateWidget("Units per week", "kpi", (f"{CST}.units_per_week",), layout=(4, 0, 4, 5), display=_KPI_COMPARE),
            TemplateWidget(
                "Reported stock on hand (latest report)", "kpi", (f"{CST}.reported_soh",), layout=(8, 0, 4, 5),
                display={**_KPI_PLAIN, "caption": "as of latest report on or before {to}"},
            ),
            TemplateWidget("Sell-through by customer", "hbar", (f"{CST}.units",), ("customer",), layout=(0, 5, 6, 8), display=_TOP15),
            TemplateWidget(
                "Sell-through by customer, monthly", "line", (f"{CST}.units",), ("customer", "period"), "month", (6, 5, 6, 8),
            ),
            TemplateWidget(
                "Stock beside sell-through, by customer", "table",
                (f"{CST}.units", f"{CST}.units_per_week", f"{CST}.reported_soh", f"{CST}.stores_reporting"), ("customer",),
                layout=(0, 13, 12, 8), sort=(f"{CST}.units", "desc"),
            ),
        ),
        left_out=(
            LeftOut("Stock cover in weeks", pending=f"{CST}.stock_cover"),
            LeftOut("Restock flags", pending=f"{CST}.restock_flag"),
            LeftOut("Sales value", pending=f"{CST}.value"),
        ),
    ),
    Template(
        key="cpor_cases",
        title="CPOR cases",
        description=(
            "How many promotion cases there are, what support they carry, how well they delivered, and how they "
            "split by status, quarter and account. CPOR dates are the case window start."
        ),
        filters_json={
            "date": {"preset": "all_time", "from": None, "to": None},
            "compare": "none",
            **_EMPTY_VALUES,
            "required": [],
        },
        widgets=(
            TemplateWidget("Promotion cases", "kpi", ("cpor.cases",), layout=(0, 0, 3, 5), display=_KPI_PLAIN),
            TemplateWidget("Support USD", "kpi", ("cpor.support_usd",), layout=(3, 0, 3, 5), display=_KPI_PLAIN),
            TemplateWidget("Support ZAR", "kpi", ("cpor.support_zar",), layout=(6, 0, 3, 5), display=_KPI_PLAIN),
            TemplateWidget("Delivery rate", "kpi", ("cpor.delivery_rate",), layout=(9, 0, 3, 5), display=_KPI_PLAIN),
            TemplateWidget("Cases by status", "hbar", ("cpor.cases",), ("status",), layout=(0, 5, 4, 8)),
            TemplateWidget(
                "Promotion cases and outcomes", "table",
                ("cpor.cases", "cpor.support_usd", "cpor.support_zar", "cpor.estimate_units", "cpor.result_units", "cpor.delivery_rate"),
                ("case", "status", "workflow_status"), layout=(4, 5, 8, 8),
            ),
            TemplateWidget("Support USD by quarter (window start)", "bar", ("cpor.support_usd",), ("period",), "quarter", (0, 13, 6, 8)),
            TemplateWidget("Support USD by customer", "hbar", ("cpor.support_usd",), ("customer",), layout=(6, 13, 6, 8), display=_TOP15),
        ),
        left_out=(
            LeftOut("Open cases", pending="cpor.open_cases"),
            LeftOut("Case value", pending="cpor.value"),
            LeftOut("Cases as a pie", reason="Cases is a distinct count, so its parts do not add up to a whole; bars are used."),
        ),
    ),
)

TEMPLATE_BY_KEY = {t.key: t for t in TEMPLATES}


def left_out_payload(t: Template, dm: DataModel | None = None) -> list[dict[str, Any]]:
    dm = dm or default_model()
    pending = {str(p.get("id")): str(p.get("reason") or "") for p in dm.pending}
    out = []
    for lo in t.left_out:
        reason = lo.reason if lo.reason is not None else pending.get(lo.pending or "", "")
        out.append({"what": lo.what, "reason": reason, "pending_id": lo.pending})
    return out


def template_list(dm: DataModel | None = None) -> list[dict[str, Any]]:
    dm = dm or default_model()
    return [
        {
            "key": t.key,
            "title": t.title,
            "description": t.description,
            "widget_count": len(t.widgets),
            "required_filters": list(t.filters_json.get("required") or []),
            "filters_json": t.filters_json,
            "left_out": left_out_payload(t, dm),
        }
        for t in TEMPLATES
    ]
