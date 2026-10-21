"""N-0065 round 4: apply migration 20261009_0026 to cip, then the approved ANALYZE.

Run through N0065_r4_apply_cip_wrapper.py (owner URL from the user environment, never printed),
from the project root with the API virtualenv. Options: --downgrade (back to 0025), --smoke
(READ ONLY, app role only: preflight checks, before-counts and timings; no owner, no changes).

Order:
  1. Preflight, READ ONLY: both connections on cip; owner superuser; app role cip, no superuser,
     no BYPASSRLS; alembic = 20261007_0025; code on disk binds cip.request_role.
  2. BEFORE (READ ONLY, app role): rows per scope in the view and the three lineage tables, the
     decision's expected counts (computed by the owner without row security, independently of
     the 0026 helpers), and view timings. Heavy-path capture before.
  3. Restart the API through the supervisor FIRST (the app now binds cip.request_role) and wait
     for healthy with a new pid. Then alembic upgrade 20261009_0026.
  4. Catalogue: revision, helpers, policies, view definition and option, index.
  5. AFTER: the same per-scope counts against the decision (mismatches counted), the r3 spot
     tables, view timings, heavy-path capture after.
  6. Restart the worker; final supervisor status.
  7. ANALYZE (owner) of dim_product, fact_sales_sellout, fact_inventory_distributor,
     fact_demand_forecast, fact_inventory_reconciliation; print last_analyze for each.
Everything is appended to N0065_r4_apply_cip_output.txt (or ..._smoke.txt).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
FROM_REV, TO_REV = "20261007_0025", "20261009_0026"
SPOT_TABLES = ("fact_sales_sellout", "fact_inventory_distributor", "weeks_of_cover_observation")
LINEAGE = ("shipment_evidence_observation", "shipment_evidence_line", "fact_inbound_shipment")
ANALYZE_TABLES = ("dim_product", "fact_sales_sellout", "fact_inventory_distributor", "fact_demand_forecast",
                  "fact_inventory_reconciliation")
HEAVY = ",".join([
    "/api/v1/channel-ops/summary",
    "/api/v1/channel-ops/cover-distribution",
    "/api/v1/plan-vs-executed",
    "/api/v1/brief/signals",
    "/api/v1/lineup/net-requirement",
])
# (label, product_lines setting or None for unset, request_role)
SCOPES = [
    ("worker (unset)", None, None),
    ("admin '*'", "*", "admin"),
    ("planner NB", "NB", "planner"),
    ("steward NB", "NB", "steward"),
    ("planner NB,NR", "NB,NR", "planner"),
    ("planner no lines '!'", "!", "planner"),
    ("steward no lines '!'", "!", "steward"),
]

os.chdir(API)
sys.path.insert(0, API)
SMOKE = "--smoke" in sys.argv
_log = open(os.path.join(HERE, "N0065_r4_apply_cip_smoke.txt" if SMOKE else "N0065_r4_apply_cip_output.txt"),
            "a", encoding="utf-8")


def say(*parts) -> None:
    line = " ".join(str(p) for p in parts)
    print(line, flush=True)
    _log.write(line + "\n")
    _log.flush()


def fail(msg: str) -> None:
    say("STOPPED:", msg)
    sys.exit(1)


import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.migrate_url_guard import database_name_from_url  # noqa: E402

RO = {"options": "-c default_transaction_read_only=on -c statement_timeout=120000", "prepare_threshold": None}


def _engine(url: str, read_only: bool):
    u = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if u.startswith("postgresql://"):
        u = "postgresql+psycopg://" + u[len("postgresql://"):]
    return sa.create_engine(u, poolclass=NullPool, connect_args=RO if read_only else {"prepare_threshold": None})


def child_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "DATABASE_URL_SYNC_MIGRATE"}


def supervisor(*args: str) -> str:
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", *args]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=180, env=child_env())
    return (out.stdout or "") + (out.stderr or "")


def component_state(text: str, name: str) -> tuple[str | None, str | None]:
    m = re.search(rf"^\s*{name}\s+(\w+)\s+pid=(\d*)", text, re.M)
    return (m.group(1), m.group(2)) if m else (None, None)


def restart(name: str) -> None:
    before = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
    _, old_pid = component_state(before, name)
    say(f"[restart {name}] before: pid={old_pid}")
    say(supervisor(os.path.join("scripts", "cip-supervisor-stop.ps1"), "-Component", name, "-Restart").strip())
    deadline = time.time() + 240
    while time.time() < deadline:
        time.sleep(10)
        st = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
        state, pid = component_state(st, name)
        say(f"[restart {name}] {time.strftime('%H:%M:%S')} state={state} pid={pid}")
        if state == "healthy" and pid and pid != old_pid:
            last = [ln for ln in st.splitlines() if "local api" in ln]
            say(f"[restart {name}] healthy.", last[-1].strip() if last else "")
            return
    fail(f"{name} did not come back healthy with a new pid within 240 s; migration not applied" if name == "api"
         else f"{name} did not report healthy within 240 s (migration already applied)")


def alembic_current(conn) -> list[str]:
    return list(conn.execute(sa.text("select version_num from alembic_version")).scalars().all())


# ------------------------------------------------------------------ expected (owner, no row security)
# Independent of the 0026 helpers: plain SQL over every row, grouped by the effective line and
# whether the row is "truly unresolved" (no product and no resolved identity).
_RES = """res AS (
  SELECT DISTINCT ON (line_identity_key) line_identity_key, product_id
  FROM shipment_evidence_observation WHERE product_id IS NOT NULL
  ORDER BY line_identity_key, valid_from DESC NULLS LAST, id DESC)"""
_LINE_ID = """lid AS (
  SELECT o.evidence_line_id AS line_id, max(res.product_id) AS pid
  FROM (SELECT DISTINCT evidence_line_id, line_identity_key FROM shipment_evidence_observation
        WHERE evidence_line_id IS NOT NULL) o
  LEFT JOIN res USING (line_identity_key) GROUP BY o.evidence_line_id)"""
EXPECTED_SQL = {
    "shipment_evidence_observation": f"""WITH {_RES}
      SELECT p.product_line, (o.product_id IS NULL AND res.product_id IS NULL) AS unresolved, count(*)
      FROM shipment_evidence_observation o LEFT JOIN res USING (line_identity_key)
      LEFT JOIN dim_product p ON p.id = coalesce(o.product_id, res.product_id) GROUP BY 1, 2""",
    "shipment_evidence_line": f"""WITH {_RES}, {_LINE_ID}
      SELECT p.product_line, (s.product_id IS NULL AND lid.pid IS NULL) AS unresolved, count(*)
      FROM shipment_evidence_line s LEFT JOIN lid ON lid.line_id = s.id
      LEFT JOIN dim_product p ON p.id = coalesce(s.product_id, lid.pid) GROUP BY 1, 2""",
    "fact_inbound_shipment": f"""WITH {_RES}, {_LINE_ID}
      SELECT p.product_line, (f.product_id IS NULL AND s.product_id IS NULL AND lid.pid IS NULL) AS unresolved, count(*)
      FROM fact_inbound_shipment f LEFT JOIN shipment_evidence_line s ON s.id = f.shipment_evidence_line_id
      LEFT JOIN lid ON lid.line_id = f.shipment_evidence_line_id
      LEFT JOIN dim_product p ON p.id = coalesce(f.product_id, s.product_id, lid.pid) GROUP BY 1, 2""",
    "view": f"""WITH {_RES}, cur AS (
        SELECT DISTINCT ON (line_identity_key) id, line_identity_key, product_id
        FROM shipment_evidence_observation WHERE superseded_by_id IS NULL
        ORDER BY line_identity_key, valid_from DESC NULLS LAST, id DESC)
      SELECT p.product_line, (c.product_id IS NULL AND res.product_id IS NULL) AS unresolved, count(*)
      FROM cur c LEFT JOIN res USING (line_identity_key)
      LEFT JOIN dim_product p ON p.id = coalesce(c.product_id, res.product_id) GROUP BY 1, 2""",
}
# The 0025 rule, for the BEFORE column: a row with no product is visible to everyone.
EXPECTED_0025_NULLS = {
    "shipment_evidence_observation": "select count(*) from shipment_evidence_observation where product_id is null",
    "shipment_evidence_line": "select count(*) from shipment_evidence_line where product_id is null",
    "fact_inbound_shipment": "select count(*) from fact_inbound_shipment where product_id is null",
}


def expected_groups(owner) -> dict[str, list[tuple]]:
    out = {}
    with owner.connect() as c:
        for k, sql in EXPECTED_SQL.items():
            out[k] = [tuple(r) for r in c.execute(sa.text(sql)).all()]
        c.rollback()
    return out


def expected_count(groups: list[tuple], lines: str | None, role: str | None) -> int:
    if lines is None or lines in ("", "*"):
        return sum(n for _, _, n in groups)
    allowed = set() if lines == "!" else set(lines.split(","))
    return sum(n for line, unresolved, n in groups
               if (line is not None and line in allowed) or (unresolved and role == "steward"))


def measure(app, scope_lines: str | None, role: str | None, timed: bool) -> dict:
    with app.connect() as c:
        if scope_lines is not None:
            c.execute(sa.text("select set_config('cip.product_lines', :v, true), "
                              "set_config('cip.editable_product_lines', :v, true), "
                              "set_config('cip.request_role', :r, true)"), {"v": scope_lines, "r": role or ""})
        got = {}
        t0 = time.perf_counter()
        got["view"] = c.execute(sa.text("select count(*) from shipment_evidence_current")).scalar_one()
        got["view_ms"] = round((time.perf_counter() - t0) * 1000)
        for t in LINEAGE:
            t0 = time.perf_counter()
            got[t] = c.execute(sa.text(f"select count(*) from {t}")).scalar_one()
            got[t + "_ms"] = round((time.perf_counter() - t0) * 1000)
        got["setting_after"] = c.execute(sa.text("select current_setting('cip.product_lines', true)")).scalar()
        if timed:
            plan = c.execute(sa.text("explain (analyze, buffers off, timing off) "
                                     "select count(*) from shipment_evidence_current")).all()
            got["view_plan_ms"] = next((ln[0] for ln in plan if "Execution Time" in ln[0]), "")
            got["pick_loops"] = [ln[0].strip() for ln in plan if "cip_sev_current_observation_ids" in ln[0]][:1]
        c.rollback()
    return got


def per_scope(owner, app, label: str, rule: str, timed: bool) -> int:
    groups = expected_groups(owner)
    nulls = {}
    if rule == "0025":
        with owner.connect() as c:
            nulls = {t: c.execute(sa.text(sql)).scalar_one() for t, sql in EXPECTED_0025_NULLS.items()}
            c.rollback()
    bad = 0
    say(f"--- {label}: rows per scope as the app role (expected = Warren 2026-10-08 decision)")
    for name, lines, role in SCOPES:
        got = measure(app, lines, role, timed)
        cells = []
        for t in ("view", *LINEAGE):
            exp = expected_count(groups[t], lines, role)
            ok = got[t] == exp
            if rule == "0026":
                bad += 0 if ok else 1
            cells.append(f"{t.replace('shipment_evidence_', 'sev_')}={got[t]}/{exp}{'' if ok else ' MISMATCH' if rule == '0026' else ' (differs)'}")
        say(f"  {name:22} setting_after={got['setting_after']!r:8} " + " ".join(cells)
            + f" | view {got['view_ms']} ms" + (f" plan {got.get('view_plan_ms')} pick {got.get('pick_loops')}" if timed else ""))
    if rule == "0025":
        say(f"  (0025 rule: rows with no product visible to every scope: {nulls})")
    return bad


def spot_check(owner, app) -> int:
    with owner.connect() as c:
        line = "NB"
        exp: dict[tuple[str, str], int] = {}
        total_dim = c.execute(sa.text("select count(*) from dim_product")).scalar_one()
        line_dim = c.execute(sa.text("select count(*) from dim_product where product_line = :l"), {"l": line}).scalar_one()
        exp[("dim_product", "unset")] = exp[("dim_product", "*")] = total_dim
        exp[("dim_product", line)] = line_dim
        exp[("dim_product", "!")] = 0
        for t in SPOT_TABLES:
            tot = c.execute(sa.text(f"select count(*) from {t}")).scalar_one()
            nul = c.execute(sa.text(f"select count(*) from {t} where product_id is null")).scalar_one()
            inl = c.execute(sa.text(f"""select count(*) from {t} x where x.product_id is null or x.product_id in
                                        (select id from dim_product where product_line = :l)"""), {"l": line}).scalar_one()
            exp[(t, "unset")] = exp[(t, "*")] = tot
            exp[(t, line)] = inl
            exp[(t, "!")] = nul
        c.rollback()
    bad = 0
    say(f"--- r3 spot tables as the app role (unchanged by 0026; one line = {line!r}):")
    for scope in ("unset", "*", line, "!"):
        with app.connect() as c:
            if scope != "unset":
                c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": scope})
            got = {"dim_product": c.execute(sa.text("select count(*) from dim_product")).scalar_one()}
            for t in SPOT_TABLES:
                got[t] = c.execute(sa.text(f"select count(*) from {t}")).scalar_one()
            c.rollback()
        line_out = []
        for t, n in got.items():
            ok = n == exp[(t, scope)]
            bad += 0 if ok else 1
            line_out.append(f"{t}={n}/{exp[(t, scope)]}{'' if ok else ' MISMATCH'}")
        say(f"  scope={scope!r:8} " + " ".join(line_out))
    return bad


def catalogue(conn) -> None:
    say("  helpers (name, security definer, config):", [tuple(r) for r in conn.execute(sa.text(
        "select proname, prosecdef, proconfig from pg_proc where proname like 'cip_sev_%' or proname = "
        "'cip_inbound_shipment_lineage' order by 1")).all()])
    say("  helper EXECUTE grants:", [tuple(r) for r in conn.execute(sa.text(
        "select routine_name, grantee from information_schema.routine_privileges where routine_name like 'cip_sev_%' "
        "or routine_name = 'cip_inbound_shipment_lineage' order by 1, 2")).all()])
    for t in LINEAGE:
        q = conn.execute(sa.text("select cmd, qual like '%lineage%', with_check like '%lineage%' from pg_policies "
                                 "where tablename = :t order by cmd"), {"t": t}).all()
        say(f"  {t} policies (cmd, using has lineage, check has lineage):", [tuple(r) for r in q])
    vd = conn.execute(sa.text("select pg_get_viewdef('shipment_evidence_current'::regclass)")).scalar_one()
    say("  view uses current pick:", "cip_sev_current_observation_ids" in vd, "| reloptions:", conn.execute(sa.text(
        "select reloptions from pg_class where relname = 'shipment_evidence_current'")).scalar())
    say("  index:", conn.execute(sa.text(
        "select indexdef from pg_indexes where indexname = 'ix_shipment_ev_obs_identity_latest'")).scalar())


def capture(tag: str) -> None:
    cap_json = os.path.join(HERE, f"N0065_r4_cap_cip_{tag}.json")
    say(f"heavy-path capture {tag} (unset, '*', NB; READ ONLY) ...")
    out = subprocess.run([sys.executable, os.path.join(HERE, "n0065_capture.py"), cap_json, "unset,star,NB", HEAVY],
                         cwd=API, capture_output=True, text=True, timeout=1200, env=child_env())
    for ln in (out.stdout or "").splitlines():
        if ln.startswith(("unset", "star", "NB")):
            say("  " + ln)
    if out.returncode:
        say("  capture exit", out.returncode, (out.stderr or "")[-400:])


def analyze(owner_url: str) -> None:
    eng = _engine(owner_url, read_only=False)
    with eng.connect() as c:
        db = c.execute(sa.text("select current_database()")).scalar_one()
        if db != "cip":
            fail("owner connection for ANALYZE is not on cip")
        c.rollback()
        c.execution_options(isolation_level="AUTOCOMMIT")
        for t in ANALYZE_TABLES:
            t0 = time.perf_counter()
            c.exec_driver_sql(f"ANALYZE public.{t}")
            say(f"  ANALYZE {t}: {round((time.perf_counter() - t0) * 1000)} ms")
        rows = c.execute(sa.text("""select relname, last_analyze, last_autoanalyze, n_live_tup
                                    from pg_stat_user_tables where relname = any(:t) order by relname"""),
                         {"t": list(ANALYZE_TABLES)}).all()
        for r in rows:
            say(f"  {r[0]:32} last_analyze={r[1]} last_autoanalyze={r[2]} n_live_tup={r[3]}")
        est = c.execute(sa.text("explain select * from dim_product where tenant_id = 'default'")).all()
        act = c.execute(sa.text("select count(*) from dim_product where tenant_id = 'default'")).scalar_one()
        say(f"  dim_product tenant_id='default' estimate: {est[0][0]} | actual {act}")
    eng.dispose()


def main() -> None:
    downgrade = "--downgrade" in sys.argv
    say("=" * 70)
    say("N-0065 round 4 apply", "SMOKE (read only)" if SMOKE else ("DOWNGRADE" if downgrade else "UPGRADE"),
        time.strftime("%Y-%m-%d %H:%M:%S"))
    s = get_settings()
    app_url = s.database_url_sync
    if database_name_from_url(app_url) != "cip":
        fail("DATABASE_URL_SYNC does not name cip")
    ae = _engine(app_url, read_only=True)
    with ae.connect() as c:
        db = c.execute(sa.text("select current_database()")).scalar_one()
        who = c.execute(sa.text(
            "select current_user, rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
        rev = alembic_current(c)
        say(f"[app]   current_database() = {db} | role = {who[0]} super={who[1]} bypassrls={who[2]} | alembic = {rev}")
        if db != "cip" or who[1] or who[2]:
            fail("app connection must be cip, not superuser, no BYPASSRLS")
        c.rollback()

    from app.core import product_line_scope as pls

    if "cip.request_role" not in pls._SCOPE_SQL or not hasattr(pls, "request_role"):
        fail("app code on disk does not bind cip.request_role")
    router_src = open(os.path.join(API, "app", "api", "v1", "router.py"), encoding="utf-8").read()
    if "request_role.set(" not in router_src:
        fail("router on disk does not set the request role")
    say("code on disk binds cip.request_role: yes")

    if SMOKE:
        per_scope(ae, ae, "SMOKE (expected computed as the app role under '*'; owner not used)", "0025", timed=False)
        st = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
        say("supervisor parse: api", component_state(st, "api"), "worker", component_state(st, "worker"))
        return

    owner_url = (os.environ.get("DATABASE_URL_SYNC_MIGRATE") or "").strip()
    if not owner_url:
        fail("DATABASE_URL_SYNC_MIGRATE is not set (run through the wrapper)")
    if database_name_from_url(owner_url) != "cip":
        fail("the owner URL does not name database cip")
    oe = _engine(owner_url, read_only=True)
    with oe.connect() as c:
        db = c.execute(sa.text("select current_database()")).scalar_one()
        who = c.execute(sa.text(
            "select current_user, rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
        say(f"[owner] current_database() = {db} | role = {who[0]} super={who[1]} bypassrls={who[2]} | alembic = {alembic_current(c)}")
        if db != "cip":
            fail("owner connection is not on cip")
        if not who[1]:
            fail("owner role is not superuser")
        c.rollback()

    target = FROM_REV if downgrade else TO_REV
    if rev == [target]:
        say(f"alembic already at {target}; skipping the migration step")
    else:
        expected_from = TO_REV if downgrade else FROM_REV
        if rev != [expected_from]:
            fail(f"alembic is {rev}, expected {expected_from}")
        if not downgrade:
            per_scope(oe, ae, "BEFORE (0025)", "0025", timed=False)
            capture("before_0026")
            restart("api")
        os.environ["DATABASE_URL_SYNC_MIGRATE"] = owner_url
        get_settings.cache_clear()
        from alembic import command
        from alembic.config import Config

        cfg = Config(os.path.join(API, "alembic.ini"))
        say(f"alembic {'downgrade' if downgrade else 'upgrade'} {target} ...")
        t0 = time.perf_counter()
        if downgrade:
            command.downgrade(cfg, target)
        else:
            command.upgrade(cfg, target)
        say(f"  done in {round(time.perf_counter() - t0, 1)} s")

    with oe.connect() as c:
        say(f"[owner] current_database() = {c.execute(sa.text('select current_database()')).scalar_one()}"
            f" | alembic now = {alembic_current(c)}")
        catalogue(c)
        c.rollback()
    if downgrade:
        say("Downgrade done.")
        return

    bad = per_scope(oe, ae, "AFTER (0026)", "0026", timed=True)
    bad += spot_check(oe, ae)
    if bad:
        say(f"MISMATCHES: {bad}. Roll back with --downgrade through the wrapper.")
    else:
        say("after 0026: every per-scope cell matches the decision; r3 spot tables unchanged")
    capture("after_0026")

    restart("worker")
    st = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
    for ln in st.splitlines():
        if ln.strip().startswith(("api", "worker", "tunnel")) or "local api" in ln:
            say("  " + ln.strip())

    say("ANALYZE (approved by Warren 2026-10-08), as owner:")
    analyze(owner_url)
    say("finished", time.strftime("%H:%M:%S"), "- mismatches:", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
