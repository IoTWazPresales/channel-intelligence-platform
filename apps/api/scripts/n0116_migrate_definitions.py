"""N-0116 S2: give stored dashboard widgets and saved reports their v2 definition (spec s.2.4).

  python scripts/n0116_migrate_definitions.py --db cip_test --dry-run
  python scripts/n0116_migrate_definitions.py --db cip_test --apply
  python scripts/n0116_migrate_definitions.py --db cip_test --prove
  python scripts/n0116_migrate_definitions.py --db cip_n0115 --owner --apply     # pg_dump clone

- Only rows with ``definition_v2 IS NULL`` are written, so a second --apply writes 0.
- The v1 query columns (metric_key, grains, filters, period_grain) are never changed. ``visual`` is
  changed only where the saved visual does not fit its breakdown and the app already draws the
  fallback (widgetModel.ts effectiveVisual; W5 line -> hbar); the saved one is kept in
  ``migrated_from.visual``.
- Every definition is planner-checked and must be v1-equivalent with the same v1 columns; any row
  that is not is left alone and reported as unmapped (exit 1).
- Counts of dashboard, dashboard_widget, saved_report, report_schedule before = after, or exit 1.
- --prove: v1 ``execute_query`` and v2 ``run_v2`` for every row with a migrated definition, in one
  READ ONLY transaction that is rolled back; total and every row compared (rounded to 6 dp; rows
  matched on ids + bucket_key). Any mismatch exits 1.

Refuses the database name ``cip`` (``clone_url``). Prints no connection string. As the owner, row
security is bypassed (same caveat as N-0115).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date
from pathlib import Path
from typing import Any

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

TABLES = ("dashboard", "dashboard_widget", "saved_report", "report_schedule")


async def _counts(db) -> dict[str, int]:
    from sqlalchemy import text

    out = {}
    for t in TABLES:
        out[t] = int((await db.execute(text(f"select count(*) from {t}"))).scalar_one())
    return out


def _print_counts(label: str, c: dict[str, int]) -> None:
    print(f"counts {label}: " + ", ".join(f"{t}={c[t]}" for t in TABLES))


async def _rows(db, *, only_null: bool) -> list[tuple[str, Any]]:
    from sqlalchemy import select

    from app.models.saved_reports import DashboardWidget, SavedReport

    out: list[tuple[str, Any]] = []
    for label, model in (("W", DashboardWidget), ("R", SavedReport)):
        q = select(model).order_by(model.id)
        if only_null:
            q = q.where(model.definition_v2.is_(None))
        out.extend((label, r) for r in (await db.execute(q)).scalars().all())
    return out


async def _map_and_write(db, *, apply: bool) -> int:
    from app.services.dashboard_definitions import Unmapped, definition_from_v1

    today = date.today().isoformat()
    rows = await _rows(db, only_null=True)
    print()
    print("| row | v1 metric | grains | period_grain | visual before | kind | v2 measures | v2 breakdowns | grain | visual after | v1_equivalent | result |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    unmapped = 0
    written = 0
    for label, r in rows:
        tag = f"{label}{r.id}"
        try:
            checked, visual_after = definition_from_v1(
                metric_key=r.metric_key,
                grains=list(r.grains or []),
                filters=dict(r.filters or {}),
                period_grain=r.period_grain,
                visual=r.visual,
                tenant_id=r.tenant_id,
                at=today,
            )
        except Unmapped as exc:
            unmapped += 1
            print(f"| {tag} | {r.metric_key} | {','.join(r.grains or []) or '-'} | {r.period_grain or '-'} | {r.visual} | - | - | - | - | - | - | UNMAPPED: {exc} |")
            continue
        d = checked.definition
        q = d["query"]
        result = "would write" if not apply else "written"
        if apply:
            r.definition_v2 = d
            if visual_after != r.visual:
                r.visual = visual_after
            written += 1
        print(
            f"| {tag} | {r.metric_key} | {','.join(r.grains or []) or '-'} | {r.period_grain or '-'} | "
            f"{d['migrated_from']['visual']} | {d['kind']} | {','.join(q['measures'])} | {','.join(q['breakdowns']) or '-'} | "
            f"{(q.get('period') or {}).get('grain') or '-'} | {visual_after} | {d['v1_equivalent']} | {result} |"
        )
    print()
    print(f"rows with definition_v2 IS NULL: {len(rows)}; {'written' if apply else 'would write'}: {written if apply else len(rows) - unmapped}; unmapped: {unmapped}")
    return unmapped


def _key(row: dict[str, Any], grains: list[str]) -> tuple:
    out = []
    for g in sorted(grains):
        if g == "period":
            out.append(row.get("bucket_key"))
        elif g in ("customer", "product", "distributor"):
            out.append(row.get(f"{g}_id"))
        else:
            v = row.get(g)
            out.append("Unassigned" if v is None else v)
    return tuple(out)


def _num(v: Any) -> float | None:
    return None if v is None else round(float(v), 6)


async def _prove(db, tenant_default: str) -> int:
    from app.query.engine import execute_query
    from app.query.model.compiler import bucket_key, compile_plan
    from app.query.model.execute import run_v2
    from app.query.model.graph import MAX_LIMIT, _governed_handler, plan_request
    from app.query.model.loader import default_model
    from app.query.calendar_grain import as_date
    from app.query.cache import clear_query_cache
    from app.semantics.registry import catalog_for_tenant_cached
    from app.services.dashboard_definitions import request_from_definition

    dm = default_model()
    rows = [(lab, r) for lab, r in await _rows(db, only_null=False) if r.definition_v2 and r.definition_v2.get("migrated_from")]
    print()
    print("| row | measure | v1 total | v2 total | rows v1 | rows v2 | v2 path | mismatches |")
    print("|---|---|---|---|---|---|---|---|")
    total_mism = 0
    for label, r in rows:
        tag = f"{label}{r.id}"
        d = r.definition_v2
        tid = r.tenant_id or tenant_default
        v1_catalog = catalog_for_tenant_cached(tid)
        req = request_from_definition(d)
        mid = req.measures[0]
        grains = list(req.breakdowns)
        if d.get("kind") == "governed":
            metric = v1_catalog.metric_by_key(mid)
            if _governed_handler(metric, v1_catalog) == "a2_cpor":
                # a2 reads through the app's own sync session (its default database), not this one.
                print(f"| {tag} | {mid} | - | - | - | - | - | SKIPPED: a2 handler uses the app's default database |")
                continue
        clear_query_cache()
        v1 = await execute_query(
            db, metric=r.metric_key, grains=list(r.grains or []), filters=dict(r.filters or {}),
            tenant_id=tid, skip_cache=True, period_grain=r.period_grain,
        )
        req.limit = MAX_LIMIT
        v2 = await run_v2(db, req, tenant_id=tid, skip_cache=True, dm=dm)
        path = "run_v2"
        v2_rows = list(v2.get("rows") or [])
        v2_total = (v2.get("totals") or {}).get(mid)
        if v2.get("ok") and v2.get("truncated") and d.get("kind") == "model":
            # More than 5,000 rows: compare every row through the same compiled SQL, unlimited.
            plan = plan_request(dm, req, v1_catalog=v1_catalog)
            plan.limit = 10_000_000
            compiled = compile_plan(dm, plan, tenant_id=tid)
            lab = compiled.measure_labels[mid]
            v2_rows = []
            for rr in (await db.execute(compiled.rows)).all():
                m = rr._mapping
                row = {mid: m[lab]}
                for g in grains:
                    if g == "period":
                        row["bucket_key"] = bucket_key(as_date(m["bucket_start"]), plan.period_grain)
                    elif g in ("customer", "product", "distributor"):
                        row[f"{g}_id"] = m[f"{g}_id"]
                    else:
                        row[g] = m[g]
                v2_rows.append(row)
            path = "run_v2 total + compiled rows (over 5,000)"
        if not v1.ok or not v2.get("ok"):
            reason = v1.message if not v1.ok else (v2.get("refusals") or [{}])[0].get("reason")
            same = (not v1.ok) and (not v2.get("ok"))
            mism = 0 if same else 1
            total_mism += mism
            print(f"| {tag} | {mid} | {'refused' if not v1.ok else v1.value} | {'refused' if not v2.get('ok') else v2_total} | - | - | {path} | {mism} ({reason}) |")
            continue
        o = {_key(x, grains): _num(x.get("value")) for x in (v1.rows or []) if isinstance(x, dict)}
        n = {_key(x, grains): _num(x.get(mid)) for x in v2_rows}
        keys = set(o) | set(n)
        mism = sum(1 for k in keys if o.get(k) != n.get(k))
        if _num(v1.value) != _num(v2_total):
            mism += 1
        total_mism += mism
        print(
            f"| {tag} | {mid} | {_fmt(v1.value)} | {_fmt(v2_total)} | {len(v1.rows or [])} | {len(v2_rows)} | {path} | {mism} |"
        )
    print()
    print(f"proved rows: {len(rows)}; total mismatches: {total_mism}")
    return total_mism


def _fmt(v: Any) -> str:
    if v is None:
        return "null"
    try:
        return f"{float(v):,.4f}"
    except (TypeError, ValueError):
        return str(v)


async def _main(db_name: str, owner: bool, mode: str, tenant: str) -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from scripts.db_on import clone_url

    url = clone_url(db_name, owner=owner)  # raises SystemExit on 'cip'
    engine = create_async_engine(url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as db:
            if mode == "prove":
                await db.execute(text("SET TRANSACTION READ ONLY"))
            who = (await db.execute(text("select current_database(), current_user"))).one()
            if str(who[0]).lower() == "cip":
                raise SystemExit("ABORT: connected to cip")
            print(f"database={who[0]} user={who[1]} mode={mode}{' read_only=yes' if mode == 'prove' else ''}")
            before = await _counts(db)
            _print_counts("before", before)
            if mode == "prove":
                mism = await _prove(db, tenant)
                await db.rollback()
                return 1 if mism else 0
            unmapped = await _map_and_write(db, apply=(mode == "apply"))
            after = await _counts(db)
            _print_counts("after ", after)
            if after != before:
                await db.rollback()
                print("ABORT: counts differ; rolled back")
                return 1
            if mode == "apply":
                await db.commit()
                again = await _rows(db, only_null=True)
                print(f"committed; rows still with definition_v2 IS NULL: {len(again)}")
            else:
                await db.rollback()
                print("dry run; rolled back")
            return 1 if unmapped else 0
    finally:
        await engine.dispose()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", required=True, help="database name (never cip)")
    p.add_argument("--owner", action="store_true", help="log in as postgres (PG_OWNER) on a clone")
    p.add_argument("--tenant", default="default")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_const", dest="mode", const="dry-run")
    g.add_argument("--apply", action="store_const", dest="mode", const="apply")
    g.add_argument("--prove", action="store_const", dest="mode", const="prove")
    a = p.parse_args()
    if a.db.strip().lower() == "cip":
        raise SystemExit("ABORT: refusing to run on cip; use a pg_dump clone")
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # psycopg async on Windows
    return asyncio.run(_main(a.db, a.owner, a.mode, a.tenant))


if __name__ == "__main__":
    raise SystemExit(main())
