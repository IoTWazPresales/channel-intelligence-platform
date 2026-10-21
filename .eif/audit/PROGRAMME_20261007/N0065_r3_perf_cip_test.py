"""N-0065 round 3: row-security cost at cip-like volume, 0024 vs 0025, on cip_test ONLY.

One transaction, always rolled back: swaps to the 0024 policies (0025's downgrade()),
seeds 18,177 products on 14 lines (10 with NULL line) and 200,000 fact_sales_sellout rows
(constraints relaxed in the transaction), times EXPLAIN ANALYZE of a scan and a group-by
under unset / '*' / one line (about a third of the products, like NB on cip) and '!'; then
applies 0025's upgrade() in the same transaction and times the same statements.
Run from apps/api with its venv (cip_test URL swapped in-process, asserted).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def _swap(url: str) -> str:
    base, _, tail = url.rpartition("/")
    query = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    return f"{base}/cip_test{query}"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


API = Path(os.getcwd())
m25 = _load(API / "alembic" / "versions" / "20261007_0025_product_line_rls_inline.py", "m25")
parity = _load(API / "tests" / "test_product_line_rls_parity_n0065_db.py", "parity")

STMTS = {
    "scan count": "SELECT count(*) FROM fact_sales_sellout",
    "group by product": "SELECT product_id, sum(units) FROM fact_sales_sellout GROUP BY product_id",
}


def main() -> int:
    url = _swap(get_settings().database_url_sync).replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url, poolclass=NullPool)
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    results = []
    with eng.connect() as conn:
        db = conn.execute(text("select current_database()")).scalar_one()
        print("current_database() =", db)
        assert db == "cip_test"
        conn.rollback()
        tx = conn.begin()
        try:
            with Operations.context(MigrationContext.configure(conn)):
                m25.downgrade()
            for t in ("dim_product", "fact_sales_sellout"):
                conn.execute(text(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY"))
            conn.execute(text(
                """insert into dim_product (sku, name, is_active, product_line)
                   select 'N0065PERF-' || g, 'perf ' || g, true,
                          case when g <= 10 then null
                               when g % 3 = 0 then 'PERF-NB' else 'PERF-L' || (g % 13) end
                   from generate_series(1, 18167) g"""))
            meta = parity._relax(conn, "fact_sales_sellout", "product_id")
            assert not meta["need"], meta
            conn.execute(text(
                """insert into fact_sales_sellout (product_id, units)
                   select (select array_agg(id) from dim_product where sku like 'N0065PERF-%')
                          [1 + (g * 7919) % 18167], 1
                   from generate_series(1, 200000) g"""))
            for t in ("dim_product", "fact_sales_sellout"):
                conn.execute(text(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY"))
            conn.execute(text("ANALYZE dim_product"))
            conn.execute(text("ANALYZE fact_sales_sellout"))
            nb = conn.execute(text("select count(*) from dim_product where product_line = 'PERF-NB'")).scalar_one()
            print("products:", conn.execute(text("select count(*) from dim_product")).scalar_one(),
                  "| PERF-NB products:", nb,
                  "| fact rows:", conn.execute(text("select count(*) from fact_sales_sellout")).scalar_one())

            def run(ver: str) -> None:
                for scope in (None, "*", "PERF-NB", "!"):
                    for label, sql in STMTS.items():
                        sp = conn.begin_nested()
                        if scope is not None:
                            conn.execute(text("select set_config('cip.product_lines', :v, true)"), {"v": scope})
                        best = None
                        rows = None
                        for _ in range(3):
                            plan = conn.execute(text("EXPLAIN (ANALYZE, FORMAT JSON) " + sql)).scalar_one()[0]
                            ms = plan["Execution Time"]
                            best = ms if best is None else min(best, ms)
                            rows = plan["Plan"].get("Actual Rows")
                        sp.rollback()
                        results.append((ver, repr(scope), label, round(best, 1), rows))

            # The None scope must be measured before any set_config on this backend.
            run("0024")
            with Operations.context(MigrationContext.configure(conn)):
                m25.upgrade()
            run("0025")
        finally:
            tx.rollback()
    eng.dispose()
    print(f"{'ver':5} {'scope':10} {'statement':18} {'best of 3 ms':>12} {'rows':>7}")
    for r in results:
        print(f"{r[0]:5} {r[1]:10} {r[2]:18} {r[3]:12} {r[4]:7}")
    by = {(v, s, lbl): ms for v, s, lbl, ms, _ in results}
    print("speed-up 0024/0025:")
    for (v, s, lbl), ms in by.items():
        if v == "0024":
            new = by[("0025", s, lbl)]
            print(f"  {s:10} {lbl:18} {ms:9} -> {new:9} ms  x{round(ms / new, 1) if new else 'inf'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
