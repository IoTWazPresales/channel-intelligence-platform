"""Distributor sell-out and returns: keep the figures a reload of the same invoice line replaces.

N-0111 repair (D-0110, Warren 2026-10-16). A distributor line is keyed by distributor, customer,
product, transaction date and invoice number (``dsi_fact_source_keys``). A line with a new invoice
number is a new transaction and is added as before. A line with the same key replaces the stored
figures in place; before it does, the stored row and the figures that change are written to
``fact_distributor_line_superseded`` with the line and load that replaced them. A reload with the
same figures replaces nothing and writes nothing, so re-applying a load changes nothing.

Lines of one load that repeat a key replace each other in file order; the earlier line's figures
are kept the same way (``previous_import_job_id`` is then the replacing load itself).
"""

from __future__ import annotations

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
        if old.get(_JOB_COLUMN[table]) == self.job_id and self._replay(table, source_key, int(line_id), old):
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

    def _replay(self, table: str, source_key: str, line_id: int, old: dict[str, Any]) -> bool:
        """Re-applying a load whose lines repeat a key: this line was already replaced by the stored one."""
        return bool(
            self.db.scalar(
                text(
                    "SELECT 1 FROM fact_distributor_line_superseded WHERE fact_table = :t AND source_key = :k "
                    "AND previous_staging_line_id = :line AND superseded_by_staging_line_id = :by LIMIT 1"
                ),
                {"t": table, "k": source_key, "line": line_id, "by": old.get("staging_line_id")},
            )
        )

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


def replaced_within_load(db: Session, job_id: int) -> dict[int, str]:
    """Lines of this load whose figures a later line of the same load replaced -> fact table."""
    rows = db.execute(
        text(
            "SELECT previous_staging_line_id, fact_table FROM fact_distributor_line_superseded "
            "WHERE superseded_by_import_job_id = :j AND previous_import_job_id = :j "
            "AND previous_staging_line_id IS NOT NULL"
        ),
        {"j": int(job_id)},
    ).all()
    return {int(r[0]): str(r[1]) for r in rows}
