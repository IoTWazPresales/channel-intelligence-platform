"""N-0065 round 5 mutation check on cip_test ONLY. From the project root with the API virtualenv.

For each mutation: commit a mutated piece of migration 0027 on cip_test (as role cip), run the
lineage/round-5 DB tests (expect failures), then restore by re-running 0027's own upgrade()
(idempotent) and confirm the tests pass again. Prints current_database() first.
Output appended to N0065_r5_mutate_cip_test_output.txt.

  Ma  pick without enable_sort = off (RESET), plus the pick's plan under the default settings
  Mb  the four tables back on the 0025 rule (a row with no product visible to everyone)
  Mc  steward branch removed on the four tables (rows with no product hidden from stewards)
  Md  pick without enable_incremental_sort = off (RESET; added in the resumed session, finding F5-1)
"""

from __future__ import annotations

import importlib.util
import os
import re
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

LOG = open(os.path.join(HERE, "N0065_r5_mutate_cip_test_output.txt"), "a", encoding="utf-8")


def say(s: str) -> None:
    print(s, flush=True)
    LOG.write(s + "\n")
    LOG.flush()


def _swap(url: str) -> str:
    base, _, tail = url.rpartition("/")
    query = ("?" + tail.split("?", 1)[1]) if "?" in tail else ""
    return f"{base}/cip_test{query}"


s = get_settings()
assert not (s.database_url_sync_migrate or "").strip(), "DATABASE_URL_SYNC_MIGRATE is set; refusing"
URL = _swap(s.database_url_sync).replace("postgresql://", "postgresql+psycopg://", 1)
spec = importlib.util.spec_from_file_location(
    "_m27", os.path.join(API, "alembic", "versions", "20261009_0027_current_pick_index_order_no_product_steward.py"))
m27 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m27)
TEST = "tests/test_shipment_evidence_lineage_rls_n0065_db.py"


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


def run_tests(label: str) -> None:
    code = ("import runpy,os,sys; sys.argv=['N0065_run_db_tests.py'," + repr(TEST) + ","
            "'-q','-p','no:cacheprovider','-rf']; runpy.run_path(" + repr(os.path.join(HERE, "N0065_run_db_tests.py"))
            + ", run_name='__main__')")
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL_SYNC_MIGRATE"}
    env["PYTHONPATH"] = API
    out = subprocess.run([sys.executable, "-c", code], cwd=API, capture_output=True, text=True, timeout=900, env=env)
    lines = [ln for ln in (out.stdout + out.stderr).splitlines() if ln.strip()]
    db = next((ln for ln in lines if ln.startswith("current_database()")), "")
    summary = next((ln for ln in reversed(lines) if re.search(r"\d+ (passed|failed)", ln)), lines[-1] if lines else "")
    failed = [ln.split(" - ")[0].replace("FAILED " + TEST + "::", "") for ln in lines if ln.startswith("FAILED ")]
    say(f"  [{label}] {db} exit={out.returncode} {summary.strip()}")
    if failed:
        say("     failed: " + "; ".join(failed))


def pick_plan(label: str) -> None:
    eng = create_engine(URL, poolclass=NullPool)
    with eng.connect() as c:
        cfg, src = c.execute(text("select proconfig, prosrc from pg_proc where proname = 'cip_sev_current_observation_ids'")).one()
        q = src.split("RETURN QUERY", 1)[1].split(";", 1)[0]
        c.execute(text("select set_config('cip.product_lines', '*', true)"))
        for item in cfg or []:
            n, v = item.split("=", 1)
            c.execute(text("select set_config(:n, :v, true)"), {"n": n, "v": v})
        plan = [r[0] for r in c.execute(text("explain (costs off) " + q)).all()]
        c.rollback()
    eng.dispose()
    tops = [p.strip() for p in plan if any(k in p for k in ("Sort", "Scan on shipment", "Scan using", "Unique"))]
    say(f"  [{label}] pick proconfig={cfg} plan nodes: {tops}")


def ma() -> None:
    from alembic import op

    op.execute(f"ALTER FUNCTION public.{m27.PICK_FN}() RESET enable_sort")


def md() -> None:
    from alembic import op

    op.execute(f"ALTER FUNCTION public.{m27.PICK_FN}() RESET enable_incremental_sort")


def mb() -> None:
    for t in m27.NO_PRODUCT_STEWARD_TABLES:
        m27._set_policies(t, m27.predicate_0025(m27.READ_SETTING, "cip_product_line_visible"),
                          m27.predicate_0025(m27.EDIT_SETTING, "cip_product_line_editable"),
                          m27.predicate_0025(m27.EDIT_SETTING, "cip_product_line_editable"))


def mc() -> None:
    orig = m27.STEWARD
    m27.STEWARD = "nobody"
    try:
        for t in m27.NO_PRODUCT_STEWARD_TABLES:
            m27._set_policies(t, m27.steward_predicate(m27.READ_SETTING, "cip_product_line_visible"),
                              m27.steward_predicate(m27.EDIT_SETTING, "cip_product_line_editable"),
                              m27.predicate_0025(m27.EDIT_SETTING, "cip_product_line_editable"))
    finally:
        m27.STEWARD = orig


def main() -> None:
    eng = create_engine(URL, poolclass=NullPool)
    with eng.connect() as c:
        say("=" * 60)
        say(f"current_database() = {c.execute(text('select current_database()')).scalar_one()} | alembic = "
            f"{c.execute(text('select version_num from alembic_version')).scalars().all()}")
        c.rollback()
    eng.dispose()
    pick_plan("baseline 0027")
    run_tests("baseline 0027")
    for name, fn in (("Ma pick without enable_sort=off", ma), ("Mb four tables on the 0025 rule", mb),
                     ("Mc no steward branch on the four tables", mc),
                     ("Md pick without enable_incremental_sort=off", md)):
        ddl(fn)
        if fn in (ma, md):
            pick_plan(name)
        run_tests(name)
        ddl(m27.upgrade)
        run_tests(name + " restored")
    pick_plan("final")


if __name__ == "__main__":
    main()
