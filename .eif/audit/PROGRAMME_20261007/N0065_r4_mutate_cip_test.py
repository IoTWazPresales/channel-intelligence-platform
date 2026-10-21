"""N-0065 round 4 mutation check on cip_test ONLY. Run from apps/api with its virtualenv.

For each mutation: commit a mutated piece of migration 0026 on cip_test (as role cip),
run the lineage DB tests (expect failures), then restore by re-running 0026's own upgrade()
(idempotent) and confirm the tests pass again. Prints current_database() first.

  M1  view without the scope-independent current pick (0025 view body)
  M2  lineage tables back on the 0025 rule (a row with no product visible to everyone)
  M3  steward branch removed (truly unresolved rows hidden from stewards)
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def _swap(url: str) -> str:
    base, _, tail = url.rpartition("/")
    query = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    return f"{base}/cip_test{query}"


s = get_settings()
assert not (s.database_url_sync_migrate or "").strip(), "DATABASE_URL_SYNC_MIGRATE is set; refusing"
URL = _swap(s.database_url_sync).replace("postgresql://", "postgresql+psycopg://", 1)
spec = importlib.util.spec_from_file_location(
    "_m26", os.path.join(API, "alembic", "versions", "20261009_0026_shipment_evidence_lineage_rls.py"))
m26 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m26)


def ddl(fn) -> None:
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    eng = create_engine(URL, poolclass=NullPool)
    with eng.connect() as c:
        db = c.execute(text("select current_database()")).scalar_one()
        assert db == "cip_test", db
        c.rollback()
        with c.begin():
            with Operations.context(MigrationContext.configure(c)):
                fn()
    eng.dispose()


def run_tests(label: str) -> str:
    code = ("import runpy,os,sys; sys.argv=['N0065_run_db_tests.py','tests/test_shipment_evidence_lineage_rls_n0065_db.py',"
            "'-q','-p','no:cacheprovider','-rf']; runpy.run_path(os.path.join(" + repr(HERE) + ",'N0065_run_db_tests.py'), run_name='__main__')")
    out = subprocess.run([sys.executable, "-c", code], cwd=API, capture_output=True, text=True, timeout=900)
    import re

    lines = [ln for ln in (out.stdout + out.stderr).splitlines() if ln.strip()]
    summary = next((ln for ln in reversed(lines) if re.search(r"\d+ (passed|failed)", ln)), lines[-1] if lines else "")
    failed = [ln.split(" - ")[0] for ln in lines if ln.startswith("FAILED ")]
    if failed:
        summary += " | " + "; ".join(f.replace("FAILED tests/test_shipment_evidence_lineage_rls_n0065_db.py::", "") for f in failed)
    print(f"  [{label}] exit={out.returncode} {summary.strip()}")
    return summary


def m1() -> None:
    from alembic import op

    op.execute(m26.VIEW_SQL.format(current_filter=""))


def m2() -> None:
    for table in m26.LINEAGE_TABLES:
        m26._set_policies(
            table,
            m26.predicate_0025(m26.READ_SETTING, "cip_product_line_visible"),
            m26.predicate_0025(m26.EDIT_SETTING, "cip_product_line_editable"),
            m26.predicate_0025(m26.EDIT_SETTING, "cip_product_line_editable"),
        )


def m3() -> None:
    orig = m26.STEWARD
    m26.STEWARD = "nobody"
    try:
        for table, helper in m26.LINEAGE_TABLES.items():
            m26._set_policies(
                table,
                m26.lineage_predicate(m26.READ_SETTING, "cip_product_line_visible", helper),
                m26.lineage_predicate(m26.EDIT_SETTING, "cip_product_line_editable", helper),
                m26.predicate_0025(m26.EDIT_SETTING, "cip_product_line_editable"),
            )
    finally:
        m26.STEWARD = orig


def main() -> None:
    eng = create_engine(URL, poolclass=NullPool)
    with eng.connect() as c:
        print("current_database() =", c.execute(text("select current_database()")).scalar_one(),
              "| alembic =", c.execute(text("select version_num from alembic_version")).scalars().all())
        c.rollback()
    eng.dispose()
    run_tests("baseline 0026")
    for name, fn in (("M1 no current pick", m1), ("M2 0025 null rule", m2), ("M3 no steward branch", m3)):
        ddl(fn)
        run_tests(name)
        ddl(m26.upgrade)
        run_tests(name + " restored")


if __name__ == "__main__":
    main()
