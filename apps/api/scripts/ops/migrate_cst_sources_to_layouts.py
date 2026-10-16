"""Carry the former sell-through sources over to customer layouts and hide them (N-0111).

Applied jobs on a customer ticked as a reporting customer become saved layouts of that customer
(mapping kept exactly as the job loaded); every source is then hidden, never deleted. A dry run
prints the plan as a table; --apply writes it. Running it twice changes nothing.

Usage (from apps/api):
  python scripts/ops/migrate_cst_sources_to_layouts.py                      # dry run
  python scripts/ops/migrate_cst_sources_to_layouts.py --apply --expect-db cip_n0111l
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

_API_ROOT = Path(__file__).resolve().parents[2]
if str(_API_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.ingestion import SourceDefinition  # noqa: E402
from app.services.imports.cst_layouts import list_layouts  # noqa: E402
from app.services.imports.cst_layout_migration import (  # noqa: E402
    apply_source_migration,
    headers_of,
    plan_source_migration,
)


def table(rows) -> str:
    lines = ["| slug | customer | applied jobs | outcome |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r.slug} | {r.customer_name} | {r.applied_jobs} | {r.outcome} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the layouts and hide the sources (default is a dry run)")
    parser.add_argument("--expect-db", default=None, help="required with --apply; must equal current_database()")
    parser.add_argument("--out", default=None, help="write the before/after tables to this file")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        current = str(db.execute(text("SELECT current_database()")).scalar() or "")
        print(f"current_database()={current}")
        if args.apply and args.expect_db != current:
            print(f"refused: --apply needs --expect-db {current!r} (got {args.expect_db!r})")
            return 2
        rows, cands = plan_source_migration(db)
        out = ["## Before (plan)", "", table(rows), "", "### Layouts to save", ""]
        for c in cands:
            out.append(
                f"- customer {c.customer_id}: **{c.name}** ({c.structure}; {len(headers_of(c))} headers; "
                f"jobs {c.jobs}; {c.note}); mapping {c.field_mapping}"
            )
        if args.apply:
            result = apply_source_migration(db)
            again = apply_source_migration(db)
            out += ["", f"## Applied: {result}", f"Second run (must change nothing): {again}", "", "## After"]
            out += ["", "| slug | customer | applied jobs | source hidden | layouts of the customer |", "|---|---|---|---|---|"]
            for r in rows:
                src = db.get(SourceDefinition, r.source_id)
                names = [
                    f"{lay.name} ({lay.report_structure_type})"
                    for lay in (list_layouts(db, r.customer_id, include_hidden=True) if r.customer_id else [])
                ]
                out.append(
                    f"| {r.slug} | {r.customer_name} | {r.applied_jobs} | {bool(src.is_hidden)} | {'; '.join(names) or '-'} |"
                )
        text_out = "\n".join(out)
    print(text_out)
    if args.out:
        Path(args.out).write_text(text_out + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
