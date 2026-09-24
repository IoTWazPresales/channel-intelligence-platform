"""N-0047 repair: ``dim_product`` inverted / placeholder launch-retire windows (BACKLOG-034).

Evidence is the committed Product Master files themselves (``import_job`` template
``product_master``, stage ``pm_committed``, oldest first), replayed read-only through the
same column mapping and (fixed) date parser the commit uses. Rules, first match wins:

``rederive_excel_serial``
    a side holds a 1970-01-01-or-earlier placeholder and the newest PM file row for the SKU has
    a bare number in that date column: an Excel day serial the old parser read as nanoseconds
    (every one became 1970-01-01). That side gets its serial date. If the re-derived window is
    itself inverted it is written AND flagged (source-faithful, like every other file window).
``null_placeholder``
    a placeholder side with no serial to re-derive from becomes NULL (unknown), never a guess.
``swap``
    ``retired_date < launch_date`` and a committed PM file had exactly the two values the other
    way round: clearly transposed, swap them.
``flag``
    any other inverted window: left as is and listed for steward review with the vintage
    evidence (same in every file / an earlier file had a valid window / ...). FLAG is not BLOCK.

Only ``launch_date``, ``retired_date`` and ``updated_at`` change. Before-values and the flag
list are written as CSV to ``.eif/audit/PROGRAMME_20260924/n0047/``.

Idempotent: a second ``--apply`` writes 0 rows (flagged rows are never written).

Default is a DRY RUN: SELECTs only, in a READ ONLY transaction; nothing is updated.
``--apply`` updates and commits. ``--expect-db`` must equal ``current_database()``.

Ready-for-cip (Warren runs, from apps/api):
    .venv/Scripts/python.exe scripts/ops/repair_n0047_dim_product_windows.py --expect-db cip
    .venv/Scripts/python.exe scripts/ops/repair_n0047_dim_product_windows.py --expect-db cip --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

from app.services.catalog.product_import_sync import _excel_serial_to_date, _parse_date_val  # noqa: E402

EVIDENCE_DIR = REPO_ROOT / ".eif" / "audit" / "PROGRAMME_20260924" / "n0047"
PLACEHOLDER_MAX = date(1970, 1, 1)

_ROWS_SQL = """
SELECT id, sku, launch_date, retired_date, lifecycle_status, product_line
FROM dim_product
ORDER BY id
"""
_PM_JOBS_SQL = """
SELECT j.id, j.file_name, j.mapping_decisions, r.storage_key
FROM import_job j
JOIN raw_file_metadata r ON r.job_id = j.id
WHERE j.template_slug = 'product_master' AND j.stage = 'pm_committed'
ORDER BY j.id
"""
_UPDATE_SQL = text(
    "UPDATE dim_product SET launch_date = :ld_new, retired_date = :rd_new, updated_at = now() "
    "WHERE id = :id AND launch_date IS NOT DISTINCT FROM :ld_old AND retired_date IS NOT DISTINCT FROM :rd_old"
)

# One vintage of one SKU: (job_id, raw launch cell, raw end-of-life cell).
Vintage = tuple[int, Any, Any]


def _is_placeholder(d: date | None) -> bool:
    return d is not None and d <= PLACEHOLDER_MAX


def _inverted(ld: date | None, rd: date | None) -> bool:
    return ld is not None and rd is not None and rd < ld


def _vintage_flag_reason(ld: date, rd: date, history: list[Vintage]) -> str:
    parsed = [(_parse_date_val(a), _parse_date_val(b)) for _, a, b in history]
    parsed = [(a, b) for a, b in parsed if a is not None and b is not None]
    if not parsed:
        return "no_pm_file_row"
    if all(p == (ld, rd) for p in parsed):
        return "same_in_every_pm_file" if len(parsed) > 1 else "single_pm_file"
    if any(a <= b for a, b in parsed):
        return "earlier_pm_file_valid_window"
    return "earlier_pm_file_other_inverted"


def plan_row(row: dict[str, Any], history: list[Vintage]) -> dict[str, Any] | None:
    """The change (or flag) for one ``dim_product`` row, or None when its window is fine.

    ``history`` is every committed PM file row for the SKU, oldest first.
    """
    ld, rd = row["launch_date"], row["retired_date"]
    out = {
        "id": int(row["id"]),
        "sku": row["sku"],
        "product_line": row.get("product_line"),
        "lifecycle_status": row.get("lifecycle_status"),
        "launch_before": ld,
        "retired_before": rd,
        "launch_after": ld,
        "retired_after": rd,
        "rule": None,
        "flag": None,
        "source_job": history[-1][0] if history else None,
    }
    if _is_placeholder(ld) or _is_placeholder(rd):
        # Each placeholder side: the newest PM file's Excel serial for it, else NULL (unknown).
        latest = history[-1] if history else None
        s_ld = _excel_serial_to_date(latest[1]) if latest and _is_placeholder(ld) else None
        s_rd = _excel_serial_to_date(latest[2]) if latest and _is_placeholder(rd) else None
        new_ld = s_ld if _is_placeholder(ld) else ld
        new_rd = s_rd if _is_placeholder(rd) else rd
        rule = "rederive_excel_serial" if (s_ld is not None or s_rd is not None) else "null_placeholder"
        out.update(rule=rule, launch_after=new_ld, retired_after=new_rd)
        if _inverted(new_ld, new_rd):
            out["flag"] = "rederived_window_inverted_in_source"
        return out
    if not _inverted(ld, rd):
        return None
    for _, a, b in history:
        if (_parse_date_val(a), _parse_date_val(b)) == (rd, ld):
            out.update(rule="swap", launch_after=rd, retired_after=ld)
            return out
    out.update(rule="flag", flag=_vintage_flag_reason(ld, rd, history))
    return out


def plan_repair(rows: list[dict[str, Any]], histories: dict[str, list[Vintage]]) -> list[dict[str, Any]]:
    plans = []
    for r in rows:
        p = plan_row(r, histories.get(r["sku"], []))
        if p is not None:
            plans.append(p)
    return plans


def is_write(p: dict[str, Any]) -> bool:
    return p["rule"] != "flag" and (p["launch_after"], p["retired_after"]) != (p["launch_before"], p["retired_before"])


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "dim_product_rows": len(rows),
        "inverted_retired_lt_launch": sum(1 for r in rows if _inverted(r["launch_date"], r["retired_date"])),
        "launch_eq_retired": sum(
            1 for r in rows if r["launch_date"] is not None and r["launch_date"] == r["retired_date"]
        ),
        "epoch_1970_both": sum(1 for r in rows if r["launch_date"] == r["retired_date"] == PLACEHOLDER_MAX),
        "placeholder_retired": sum(1 for r in rows if _is_placeholder(r["retired_date"])),
        "placeholder_launch": sum(1 for r in rows if _is_placeholder(r["launch_date"])),
    }


def _rows(conn: Connection) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute(text(_ROWS_SQL)).mappings()]


def _storage():
    from app.core.config import get_settings
    from app.storage.local import LocalStorageBackend

    base = Path(get_settings().local_storage_path)
    return LocalStorageBackend(str(base if base.is_absolute() else API_ROOT / base))


def load_histories(conn: Connection, skus: set[str]) -> dict[str, list[Vintage]]:
    """SKU -> committed PM file rows (oldest job first), read with the commit's own mapping."""
    from app.ingestion.infer import read_tabular
    from app.services.imports.pm_dataframe_sanitize import scalar_to_clean_str, strip_leading_descriptor_rows
    from app.services.imports.product_master_workflow import (
        decisions_to_field_mapping,
        display_name_column,
        technical_id_column,
    )

    storage = _storage()
    out: dict[str, list[Vintage]] = {}
    for jid, fname, md, key in conn.execute(text(_PM_JOBS_SQL)).all():
        fm = decisions_to_field_mapping(md or {})
        ld_col = next((h for h, g in fm.items() if g == "launch_date"), None)
        eol_col = next((h for h, g in fm.items() if g == "end_of_life_date"), None)
        if not ld_col and not eol_col:
            continue
        tech = technical_id_column(fm)
        df = read_tabular(fname, storage.read(key))
        df, _ = strip_leading_descriptor_rows(df, tech_col=tech, name_col=display_name_column(fm))
        n = 0
        for _, row in df.iterrows():
            sku = scalar_to_clean_str(row.get(tech))
            if sku in skus:
                out.setdefault(sku, []).append(
                    (int(jid), row.get(ld_col) if ld_col else None, row.get(eol_col) if eol_col else None)
                )
                n += 1
        print(f"  PM job {jid} {fname}: {n} candidate SKU rows")
    return out


def _write_csv(name: str, db: str, plans: list[dict[str, Any]], *, apply: bool, stamp: str) -> Path | None:
    if not plans:
        return None
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE_DIR / f"{name}_{db}_{'apply' if apply else 'dryrun'}_{stamp}.csv"
    cols = list(plans[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for p in plans:
            w.writerow({k: ("" if v is None else v) for k, v in p.items()})
    return path


def apply_changes(conn: Connection, writes: list[dict[str, Any]]) -> int:
    n = 0
    for p in writes:
        res = conn.execute(
            _UPDATE_SQL,
            {
                "id": p["id"],
                "ld_new": p["launch_after"],
                "rd_new": p["retired_after"],
                "ld_old": p["launch_before"],
                "rd_old": p["retired_before"],
            },
        )
        n += res.rowcount
    return n


def run(conn: Connection, *, apply: bool) -> dict[str, Any]:
    """Run inside the caller's transaction. Caller commits or rolls back."""
    db = str(conn.execute(text("SELECT current_database()")).scalar())
    print("current_database() =", db)
    rows = _rows(conn)
    before = counts(rows)
    print("before:", json.dumps(before))
    cand = {
        r["sku"]
        for r in rows
        if _inverted(r["launch_date"], r["retired_date"])
        or _is_placeholder(r["launch_date"])
        or _is_placeholder(r["retired_date"])
    }
    histories = load_histories(conn, cand)
    plans = plan_repair(rows, histories)
    writes = [p for p in plans if is_write(p)]
    flags = [p for p in plans if p["flag"]]
    by_rule = dict(Counter(p["rule"] for p in writes))
    by_flag = dict(Counter(p["flag"] for p in flags))
    print("planned writes by rule:", json.dumps(by_rule))
    print("flags by reason:", json.dumps(by_flag))
    for p in writes[:10]:
        print(
            f"  id={p['id']} {p['sku']} {p['rule']}: "
            f"{p['launch_before']}..{p['retired_before']} -> {p['launch_after']}..{p['retired_after']}"
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name, lst in (("before", writes), ("flags", flags)):
        path = _write_csv(name, db, lst, apply=apply, stamp=stamp)
        if path:
            print(f"{name} CSV written:", path)
    written = 0
    if apply:
        print("current_database() before write =", conn.execute(text("SELECT current_database()")).scalar())
        written = apply_changes(conn, writes)
        after = counts(_rows(conn))
    else:
        # Dry run: no UPDATE runs; "after" is what the plan would leave.
        after_rows = [dict(r) for r in rows]
        by_id = {p["id"]: p for p in writes}
        for r in after_rows:
            p = by_id.get(int(r["id"]))
            if p:
                r["launch_date"], r["retired_date"] = p["launch_after"], p["retired_after"]
        after = counts(after_rows)
    print("rows updated:", written)
    print("after:" if apply else "after (projected, nothing written):", json.dumps(after))
    print("mode:", "APPLY (commit)" if apply else "DRY RUN (read-only, no writes)")
    return {
        "database": db,
        "before": before,
        "after": after,
        "writes_by_rule": by_rule,
        "flags_by_reason": by_flag,
        "written": written,
    }


def _rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--expect-db", required=True, help="must equal current_database()")
    ap.add_argument("--db", default=None, help="database name to connect to (default: settings DB)")
    ap.add_argument("--apply", action="store_true", help="update and commit (default: read-only dry run)")
    args = ap.parse_args()

    from app.core.config import get_settings
    from app.db.sync_url import sqlalchemy_sync_engine_url

    sync = get_settings().database_url_sync
    if args.db:
        sync = _rewrite_dbname(sync, args.db)
    engine = create_engine(sqlalchemy_sync_engine_url(sync))
    with engine.connect() as conn:
        if not args.apply:
            # First statement of the transaction: the server refuses any write from here on.
            conn.execute(text("SET TRANSACTION READ ONLY"))
            print("transaction_read_only =", conn.execute(text("SHOW transaction_read_only")).scalar())
        db = conn.execute(text("SELECT current_database()")).scalar()
        print("current_database() =", db)
        if db != args.expect_db:
            print(f"STOP: current_database() is {db}, expected {args.expect_db}")
            conn.rollback()
            return 2
        run(conn, apply=args.apply)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
