"""What a sell-through or distributor load read, loaded and did not load, by reason (N-0111 repair).

Warren 2026-10-16 (D-0108): a load that drops rows says so. A job with rows not loaded is never a
plain "Completed"; it shows "Completed with rows not loaded (N)" and the reason for each category.

Rows read = rows staged + rows the parser could not stage + rows in files it refused. Each staged
row gets one reason from its staging line, using the same conditions as the apply:

- customer sell-through: applied (or an identical copy counted once) is loaded; otherwise product
  not matched, customer not set, no sale date or period, no figures, or waiting to apply;
- distributor sales & inventory: a line that wrote a sale, return or stock fact is loaded; a line
  whose sale or stock part did not load is partly loaded; a line that repeats an earlier line of
  the same load (same invoice, product, date and customer) is loaded: summed into it when it
  differs, counted once when identical in every source column (D-0091); otherwise not matched, no
  date, no figures, or waiting to apply.

The counts come from the staging tables on every read; nothing is stored beyond what the CST
parser records in ``staged_metadata.cst_load_parse``.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

CST = "customer_sell_through"
DSI = "distributor_inventory"
COMPLETED = ("completed", "completed_with_errors")

LABELS: dict[str, str] = {
    # parser, customer sell-through
    "missing_product_or_units": "Missing product code or units",
    "missing_product_or_on_hand": "Missing product code or on-hand (stock-only file)",
    "no_positive_week_units": "Missing product code, or no units above 0 in any week",
    "year_required": "Week numbers without a confirmed year (tick Year confirmed)",
    "no_on_hand": "Units without on-hand (tick Sales-only file)",
    "no_units": "On-hand without units (tick Stock-only file)",
    # staged lines, both paths
    "product_not_matched": "Product not matched (finish in the steward)",
    "customer_not_set": "Customer not set",
    "no_period": "No sale date or period",
    "no_figures": "No units or stock figures",
    "waiting_to_apply": "Matched, not applied yet",
    # distributor
    "distributor_not_matched": "Distributor not matched (finish in the steward)",
    "customer_not_matched": "Sale with no matched customer",
    "no_date": "No transaction or snapshot date",
    "no_sale_date": "Sale with no transaction date",
    "no_snapshot_date": "Stock with no snapshot date",
    "partly_customer_not_matched": "Stock loaded; the sale did not (no matched customer)",
    "partly_no_sale_date": "Stock loaded; the sale did not (no transaction date)",
    "partly_no_snapshot_date": "Sale loaded; the stock did not (no snapshot date)",
}
PARTLY = frozenset(k for k in LABELS if k.startswith("partly_"))

_CST_SQL = """
SELECT import_job_id, CASE
    WHEN apply_status = 'applied' THEN 'loaded'
    WHEN apply_status = 'duplicate' THEN 'duplicate'
    WHEN resolution_status <> 'resolved' OR resolved_product_id IS NULL THEN 'product_not_matched'
    WHEN resolved_customer_id IS NULL THEN 'customer_not_set'
    WHEN period_start_date IS NULL THEN 'no_period'
    WHEN units_sold IS NULL AND reported_soh IS NULL AND in_transit_units IS NULL AND on_order_units IS NULL
        THEN 'no_figures'
    ELSE 'waiting_to_apply' END AS reason, count(*)
FROM import_customer_sellthrough_staging_line
WHERE import_job_id = ANY(:ids)
GROUP BY 1, 2
"""

_DSI_SQL = """
SELECT s.import_job_id, CASE
    WHEN s.apply_status LIKE 'duplicate%' THEN 'duplicate'
    WHEN s.apply_status <> 'pending' AND coalesce(s.quantity_sold, 0) <> 0
         AND s.apply_status NOT LIKE '%sellout%' AND s.apply_status NOT LIKE '%return%'
        THEN CASE WHEN s.transaction_date IS NULL THEN 'partly_no_sale_date' ELSE 'partly_customer_not_matched' END
    WHEN s.apply_status <> 'pending' AND s.stock_on_hand IS NOT NULL AND s.apply_status NOT LIKE '%inventory%'
        THEN 'partly_no_snapshot_date'
    WHEN s.apply_status <> 'pending' THEN 'loaded'
    WHEN s.resolved_distributor_id IS NULL THEN 'distributor_not_matched'
    WHEN s.resolved_product_id IS NULL THEN 'product_not_matched'
    WHEN coalesce(s.quantity_sold, 0) = 0 AND s.stock_on_hand IS NULL THEN 'no_figures'
    WHEN s.transaction_date IS NULL AND s.snapshot_date IS NULL THEN 'no_date'
    WHEN coalesce(s.quantity_sold, 0) <> 0 AND s.resolved_customer_id IS NULL
         AND (s.snapshot_date IS NULL OR s.stock_on_hand IS NULL) THEN 'customer_not_matched'
    WHEN coalesce(s.quantity_sold, 0) <> 0 AND s.transaction_date IS NULL
         AND (s.snapshot_date IS NULL OR s.stock_on_hand IS NULL) THEN 'no_sale_date'
    WHEN coalesce(s.quantity_sold, 0) = 0 AND s.snapshot_date IS NULL THEN 'no_snapshot_date'
    ELSE 'waiting_to_apply' END AS reason, count(*)
FROM import_distributor_si_staging_line s
WHERE s.import_job_id = ANY(:ids)
GROUP BY 1, 2
"""


def display_status(status: str | None, report: dict[str, Any] | None) -> str:
    """The status a person reads: never a plain "Completed" when rows did not load."""
    st = (status or "").strip().lower()
    if st in COMPLETED and report:
        n = int(report.get("rows_not_loaded") or 0) + int(report.get("rows_partly_loaded") or 0)
        if n:
            return f"Completed with rows not loaded ({n})"
        files = len(report.get("files_not_read") or [])
        if files:
            return f"Completed with files not read ({files})"
    return {
        "completed": "Completed",
        "completed_with_errors": "Completed with errors",
        "failed": "Failed",
        "running": "Running",
        "pending": "Pending",
    }.get(st, status or "")


def build_report(kind: str, reasons: dict[str, int], parse: dict[str, Any] | None = None) -> dict[str, Any]:
    """The load report from per-reason staging counts and the parser's own record."""
    parse = parse if isinstance(parse, dict) else {}
    counts: Counter[str] = Counter({k: int(v) for k, v in reasons.items() if v})
    for key in ("rows_not_staged", "file_rows_refused"):
        for reason, n in (parse.get(key) or {}).items():
            if int(n or 0):
                counts[str(reason)] += int(n)
    loaded = counts.pop("loaded", 0)
    duplicates = counts.pop("duplicate", 0)
    partly = {k: n for k, n in counts.items() if k in PARTLY}
    not_loaded = {k: n for k, n in counts.items() if k not in PARTLY}
    rows_read = loaded + duplicates + sum(partly.values()) + sum(not_loaded.values())

    def _items(d: dict[str, int], *, partial: bool) -> list[dict[str, Any]]:
        return [
            {"reason": k, "label": LABELS.get(k, k.replace("_", " ")), "rows": int(n), "partly_loaded": partial}
            for k, n in sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

    return {
        "kind": kind,
        "rows_read": int(rows_read),
        "rows_loaded": int(loaded + duplicates),
        "rows_partly_loaded": int(sum(partly.values())),
        "rows_not_loaded": int(sum(not_loaded.values())),
        "identical_copies_counted_once": int(duplicates),
        "not_loaded": _items(not_loaded, partial=False) + _items(partly, partial=True),
        "files_not_read": list(parse.get("files_not_read") or []),
        "files_excluded": int(parse.get("files_excluded") or 0),
    }


def _kind(template_slug: str | None) -> str | None:
    slug = (template_slug or "").strip()
    return slug if slug in (CST, DSI) else None


def _group(rows: Iterable[Any]) -> dict[int, dict[str, int]]:
    out: dict[int, dict[str, int]] = {}
    for job_id, reason, n in rows:
        out.setdefault(int(job_id), {})[str(reason)] = int(n)
    return out


def load_report_sync(db: Session, job: Any) -> dict[str, Any] | None:
    """The load report for one CST or DSI job (None for other templates)."""
    kind = _kind(getattr(job, "template_slug", None))
    if kind is None:
        return None
    ids = {"ids": [int(job.id)]}
    if kind == CST:
        rows = db.execute(text(_CST_SQL), ids).all()
    else:
        rows = db.execute(text(_DSI_SQL), ids).all()
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    return build_report(kind, _group(rows).get(int(job.id), {}), meta.get("cst_load_parse"))


async def load_reports_async(db: AsyncSession, jobs: Iterable[tuple[int, str | None]]) -> dict[int, dict[str, Any]]:
    """Load reports for many jobs at once: ``[(job_id, template_slug), ...]`` -> {job_id: report}."""
    by_kind: dict[str, list[int]] = {CST: [], DSI: []}
    for job_id, slug in jobs:
        kind = _kind(slug)
        if kind:
            by_kind[kind].append(int(job_id))
    out: dict[int, dict[str, Any]] = {}
    if by_kind[CST]:
        ids = {"ids": by_kind[CST]}
        grouped = _group((await db.execute(text(_CST_SQL), ids)).all())
        parses = {
            int(r[0]): r[1]
            for r in (
                await db.execute(
                    text("SELECT id, staged_metadata -> 'cst_load_parse' FROM import_job WHERE id = ANY(:ids)"), ids
                )
            ).all()
        }
        for jid in by_kind[CST]:
            out[jid] = build_report(CST, grouped.get(jid, {}), parses.get(jid))
    if by_kind[DSI]:
        grouped = _group((await db.execute(text(_DSI_SQL), {"ids": by_kind[DSI]})).all())
        for jid in by_kind[DSI]:
            out[jid] = build_report(DSI, grouped.get(jid, {}))
    return out
