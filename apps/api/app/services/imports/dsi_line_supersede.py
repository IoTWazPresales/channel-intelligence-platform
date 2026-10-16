"""Distributor sell-out and returns: keep the figures a reload of the same invoice line replaces.

N-0111 repair (D-0110, Warren 2026-10-16). A distributor line is keyed by distributor, customer,
product, transaction date and invoice number (``dsi_fact_source_keys``). A line with a new invoice
number is a new transaction and is added as before. A line with the same key replaces the stored
figures in place; before it does, the stored row and the figures that change are written to
``fact_distributor_line_superseded`` with the line and load that replaced them. A reload with the
same figures replaces nothing and writes nothing, so re-applying a load changes nothing.

Lines of one load that repeat a key follow D-0091 (``RepeatedLines``): lines that differ are
summed into the one stored row, and a line identical in every source column counts once and is
marked ``duplicate``. They do not replace each other.
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.json_safe import to_jsonable

logger = logging.getLogger(__name__)

SELLOUT = "fact_sales_sellout"
RETURNS = "fact_returns"
FIGURES: dict[str, tuple[str, ...]] = {
    SELLOUT: (
        "units",
        "revenue",
        "unit_sellout_price_ex_tax_amount",
        "reported_revenue_amount",
        "computed_revenue_amount",
        "currency_code",
    ),
    RETURNS: ("return_quantity", "unit_price"),
}
_JOB_COLUMN = {SELLOUT: "source_import_job_id", RETURNS: "import_job_id"}
_CHUNK = 1000


def _same(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float, Decimal)) and isinstance(b, (int, float, Decimal)):
        return round(float(a), 4) == round(float(b), 4)
    return str(a) == str(b)


def changed_figures(table: str, old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The figures ``new`` replaces in ``old``, as ``{name: {"old": .., "new": ..}}``."""
    return {
        name: {"old": to_jsonable(old.get(name)), "new": to_jsonable(new.get(name))}
        for name in FIGURES[table]
        if name in new and not _same(old.get(name), new.get(name))
    }


class LineSupersede:
    """Stored rows for one apply, read once per key, and the replaced-figure records it writes."""

    def __init__(self, db: Session, *, job_id: int, tenant_id: str) -> None:
        self.db = db
        self.job_id = int(job_id)
        self.tenant_id = tenant_id
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}
        self.recorded = 0

    def prefetch(self, table: str, keys: Iterable[str]) -> None:
        wanted = sorted({k for k in keys if k})
        for start in range(0, len(wanted), _CHUNK):
            chunk = wanted[start : start + _CHUNK]
            for row in self.db.execute(
                text(f"SELECT * FROM {table} WHERE source_key = ANY(:keys)"), {"keys": chunk}
            ).mappings():
                self.rows[(table, str(row["source_key"]))] = dict(row)

    def before_write(self, table: str, source_key: str, new: dict[str, Any], *, line_id: int) -> bool:
        """Keep the figures this line replaces. True when a record was written."""
        old = self.rows.get((table, source_key))
        if old is None:
            return False
        if "product_id" not in old:
            # Written earlier in this load: read the whole stored row once.
            row = self.db.execute(
                text(f"SELECT * FROM {table} WHERE source_key = :k"), {"k": source_key}
            ).mappings().first()
            if row is None:
                return False
            old = self.rows[(table, source_key)] = dict(row)
        figures = changed_figures(table, old, new)
        if not figures:
            return False
        result = self.db.execute(
            text(
                """
                INSERT INTO fact_distributor_line_superseded (
                    tenant_id, fact_table, fact_id, source_key, distributor_id, customer_id, product_id,
                    transaction_date, invoice_no, previous_staging_line_id, previous_import_job_id,
                    superseded_by_staging_line_id, superseded_by_import_job_id, figures, row_json
                ) VALUES (
                    :tenant_id, :fact_table, :fact_id, :source_key, :distributor_id, :customer_id, :product_id,
                    :transaction_date, :invoice_no, :prev_line, :prev_job, :line_id, :job_id,
                    CAST(:figures AS jsonb), CAST(:row_json AS jsonb)
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "tenant_id": self.tenant_id,
                "fact_table": table,
                "fact_id": int(old["id"]),
                "source_key": source_key,
                "distributor_id": old.get("distributor_id"),
                "customer_id": old.get("customer_id"),
                "product_id": int(old["product_id"]),
                "transaction_date": old.get("transaction_date"),
                "invoice_no": old.get("invoice_no"),
                "prev_line": old.get("staging_line_id"),
                "prev_job": old.get(_JOB_COLUMN[table]),
                "line_id": int(line_id),
                "job_id": self.job_id,
                "figures": _json(figures),
                "row_json": _json(to_jsonable(old)),
            },
        )
        written = bool(result.rowcount)
        self.recorded += int(written)
        return written

    def after_write(self, table: str, source_key: str, new: dict[str, Any], *, fact_id: int | None, line_id: int) -> None:
        row = dict(self.rows.get((table, source_key)) or {})
        row.update(new)
        row.update({"source_key": source_key, "staging_line_id": int(line_id), _JOB_COLUMN[table]: self.job_id})
        if fact_id is not None:
            row["id"] = int(fact_id)
        self.rows[(table, source_key)] = row


def _json(value: Any) -> str:
    import json

    return json.dumps(value, default=str)


_SUMMED = {
    SELLOUT: ("units", "revenue", "reported_revenue_amount", "computed_revenue_amount"),
    RETURNS: ("return_quantity",),
}
# Not additive: the later line's value wins, as for customer sell-through prices.
_LATER = {SELLOUT: ("unit_sellout_price_ex_tax_amount", "currency_code"), RETURNS: ("unit_price",)}
_IDENTITY_COLUMNS = (
    "raw_distributor_token",
    "raw_customer_dealer_token",
    "raw_dealer_group_token",
    "raw_product_token",
    "transaction_date",
    "invoice_no",
    "snapshot_date",
    "quantity_sold",
    "stock_on_hand",
    "unit_sellout_price_ex_tax_amount",
    "reported_revenue_amount",
    "computed_revenue_amount",
    "currency_code",
)

LEAD = "lead"
SUMMED = "summed"
DUPLICATE = "duplicate"


def source_identity(line: Any) -> str:
    """Every source column of a staged line (``_`` keys are CIP's own notes) and what was parsed from it."""
    payload = line.raw_row_payload if isinstance(line.raw_row_payload, dict) else {}
    source = {k: v for k, v in payload.items() if not str(k).startswith("_")}
    parsed = [getattr(line, k, None) for k in _IDENTITY_COLUMNS]
    return hashlib.sha256(json.dumps([source, parsed], sort_keys=True, default=str).encode("utf-8")).hexdigest()


class RepeatedLines:
    """Lines of one load that share a fact key (D-0091, applied to distributor files).

    Lines that differ in any source column are separate lines and their figures are summed into the
    one stored row; a line identical in every source column to one already counted is kept once and
    is marked ``duplicate``. The first line of a key writes the row (``lead``); later differing lines
    are ``summed`` into it and write nothing of their own.
    """

    def __init__(self) -> None:
        self._groups: dict[tuple[str, str], dict[str, Any]] = {}
        self._roles: dict[int, str] = {}
        self.duplicate_lines = 0
        self.summed_lines = 0

    def add(self, table: str, source_key: str, line: Any, figures: dict[str, Any]) -> None:
        ident = source_identity(line)
        group = self._groups.get((table, source_key))
        if group is None:
            self._groups[(table, source_key)] = {"figures": dict(figures), "idents": {ident}, "fact_id": None}
            self._roles[int(line.id)] = LEAD
            return
        if ident in group["idents"]:
            self._roles[int(line.id)] = DUPLICATE
            self.duplicate_lines += 1
            return
        group["idents"].add(ident)
        merged = group["figures"]
        for name in _SUMMED[table]:
            if figures.get(name) is not None:
                merged[name] = float(merged.get(name) or 0.0) + float(figures[name])
        for name in _LATER[table]:
            if figures.get(name) is not None:
                merged[name] = figures[name]
        self._roles[int(line.id)] = SUMMED
        self.summed_lines += 1

    def role(self, line_id: int) -> str:
        return self._roles.get(int(line_id), LEAD)

    def figures(self, table: str, source_key: str, default: dict[str, Any]) -> dict[str, Any]:
        group = self._groups.get((table, source_key))
        return group["figures"] if group else default

    def set_fact_id(self, table: str, source_key: str, fact_id: int | None) -> None:
        group = self._groups.get((table, source_key))
        if group is not None:
            group["fact_id"] = fact_id

    def fact_id(self, table: str, source_key: str) -> int | None:
        group = self._groups.get((table, source_key))
        return group["fact_id"] if group else None
