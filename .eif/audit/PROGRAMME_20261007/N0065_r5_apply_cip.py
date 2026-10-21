"""N-0065 round 5: apply migration 20261009_0027 to cip (Warren's decision of 2026-10-09).

Run through N0065_r5_apply_cip_wrapper.py (owner URL from the user environment, never printed),
from the project root with the API virtualenv. Options:
  --smoke      READ ONLY, app role only: preflight, before-counts (expected computed as the app
               role under '*'), timings; no owner connection, no change.
  --downgrade  back to 20261009_0026 (the tested downgrade).

Order (upgrade):
  1. Preflight, READ ONLY: both connections on cip; owner superuser; app role cip, no superuser,
     no BYPASSRLS; alembic = 20261009_0026; the pick has no enable_sort / enable_incremental_sort; the four tables'
     policy texts are the 0026 ones (md5 as measured on cip and on cip_test after 0027's
     downgrade). No app code changed this round, so the API is NOT restarted.
  2. BEFORE (READ ONLY, app role): rows per scope in the view, the three lineage tables and the
     four no-product tables against expectations computed by the owner without row security
     (plain SQL, independent of the helpers and policies); view and helper timings; the pick's
     nested plan through auto_explain (owner session, SET ROLE cip, READ ONLY); heavy-path
     capture x2.
  3. alembic upgrade 20261009_0027 (owner).
  4. Catalogue after.
  5. AFTER: the same, against the 0027 rule; mismatches counted. On ANY mismatch: alembic
     downgrade 20261009_0026 immediately, re-check, stop.
  6. Restart the worker; final supervisor status.
Everything is appended to N0065_r5_apply_cip_output.txt (or ..._smoke.txt).
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
FROM_REV, TO_REV = "20261009_0026", "20261009_0027"
POLICY_MD5_0026 = "0933b362704b3b553abc66f85931371a"
LINEAGE = ("shipment_evidence_observation", "shipment_evidence_line", "fact_inbound_shipment")
FOUR = ("commercial_lineup_line", "cst_listing_seed", "customer_listing", "historical_lineup_import_line")
HELPERS = ("cip_sev_current_observation_ids", "cip_sev_observation_lineage", "cip_sev_line_lineage",
           "cip_inbound_shipment_lineage")
HEAVY = ",".join([
    "/api/v1/plan-vs-executed",
    "/api/v1/channel-ops/summary",
    "/api/v1/channel-ops/cover-distribution",
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
_log = open(os.path.join(HERE, "N0065_r5_apply_cip_smoke.txt" if SMOKE else "N0065_r5_apply_cip_output.txt"),
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

RO = {"options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None}


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
    say(f"[restart {name}] {time.strftime('%H:%M:%S')} before: pid={old_pid}")
    say(supervisor(os.path.join("scripts", "cip-supervisor-stop.ps1"), "-Component", name, "-Restart").strip())
    deadline = time.time() + 240
    while time.time() < deadline:
        time.sleep(10)
        st = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
        state, pid = component_state(st, name)
        say(f"[restart {name}] {time.strftime('%H:%M:%S')} state={state} pid={pid}")
        if state == "healthy" and pid and pid != old_pid:
            say(f"[restart {name}] healthy.")
            return
    say(f"[restart {name}] did not report healthy with a new pid within 240 s")


def alembic_current(conn) -> list[str]:
    return list(conn.execute(sa.text("select version_num from alembic_version")).scalars().all())


# ------------------------------------------------------------------ expected (owner, no row security)
# Copied from N0065_r4_apply_cip.py (independent of the 0026 helpers): effective line and whether a
# row is "truly unresolved" (no product and no resolved identity).
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
# The four tables: no inheritance; "unresolved" = no product.
for _t in FOUR:
    EXPECTED_SQL[_t] = (f"SELECT p.product_line, (t.product_id IS NULL) AS unresolved, count(*) FROM {_t} t "
                        "LEFT JOIN dim_product p ON p.id = t.product_id GROUP BY 1, 2")
TABLES = ("view", *LINEAGE, *FOUR)


def expected_groups(conn_factory) -> dict[str, list[tuple]]:
    out = {}
    with conn_factory.connect() as c:
        c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))  # app role in --smoke
        for k, sql in EXPECTED_SQL.items():
            out[k] = [tuple(r) for r in c.execute(sa.text(sql)).all()]
        c.rollback()
    return out


def expected_count(groups: list[tuple], lines: str | None, role: str | None, rule: str, table: str) -> int:
    """rule '0026': the four tables still show rows with no product to every scope."""
    if lines is None or lines in ("", "*"):
        return sum(n for _, _, n in groups)
    allowed = set() if lines == "!" else set(lines.split(","))
    null_open = rule == "0026" and table in FOUR
    return sum(n for line, unresolved, n in groups
               if (line is not None and line in allowed) or (unresolved and (role == "steward" or null_open)))


def _bind(c, lines, role) -> None:
    if lines is not None:
        c.execute(sa.text("select set_config('cip.product_lines', :v, true), "
                          "set_config('cip.editable_product_lines', :v, true), "
                          "set_config('cip.request_role', :r, true)"), {"v": lines, "r": role or ""})


def measure(app, lines, role) -> dict:
    got = {}
    with app.connect() as c:
        _bind(c, lines, role)
        for t in TABLES:
            rel = "shipment_evidence_current" if t == "view" else t
            got[t] = c.execute(sa.text(f"select count(*) from {rel}")).scalar_one()
        best = None
        for _ in range(3):
            t0 = time.perf_counter()
            c.execute(sa.text("select count(*) from shipment_evidence_current")).scalar_one()
            ms = (time.perf_counter() - t0) * 1000
            best = ms if best is None else min(best, ms)
        got["view_ms"] = round(best)
        plan = c.execute(sa.text("explain (analyze, buffers off) select count(*) from shipment_evidence_current")).all()
        got["pick_node"] = next((ln[0].strip()[:160] for ln in plan if "cip_sev_current_observation_ids" in ln[0]), "")
        got["setting_after"] = c.execute(sa.text("select current_setting('cip.product_lines', true)")).scalar()
        got["enable_sort_after"] = (c.execute(sa.text("show enable_sort")).scalar() + "/"
                                    + c.execute(sa.text("show enable_incremental_sort")).scalar())
        c.rollback()
    return got


def per_scope(exp_factory, app, label: str, rule: str) -> int:
    groups = expected_groups(exp_factory)
    bad = 0
    say(f"--- {label}: rows per scope as the app role, got/expected (rule {rule}); view best of 3")
    for name, lines, role in SCOPES:
        got = measure(app, lines, role)
        cells = []
        for t in TABLES:
            exp = expected_count(groups[t], lines, role, rule, t)
            ok = got[t] == exp
            bad += 0 if ok else 1
            short = t.replace("shipment_evidence_", "sev_").replace("historical_lineup_import_line", "hist_line") \
                .replace("commercial_lineup_line", "cl_line").replace("fact_inbound_shipment", "inbound")
            cells.append(f"{short}={got[t]}/{exp}{'' if ok else ' MISMATCH'}")
        say(f"  {name:22} " + " ".join(cells))
        say(f"  {'':22} view {got['view_ms']} ms | setting_after={got['setting_after']!r} "
            f"enable_sort/incremental_after={got['enable_sort_after']} | pick: {got['pick_node'] or 'not in plan'}")
    return bad


def helper_times(app, label: str) -> None:
    say(f"--- {label}: helper timings as the app role under NB (count(*), best of 3)")
    with app.connect() as c:
        _bind(c, "NB", "planner")
        for fn in HELPERS:
            best, n = None, None
            for _ in range(3):
                t0 = time.perf_counter()
                n = c.execute(sa.text(f"select count(*) from public.{fn}()")).scalar_one()
                ms = (time.perf_counter() - t0) * 1000
                best = ms if best is None else min(best, ms)
            say(f"  {fn:34} rows={n:6} {round(best)} ms")
        c.rollback()


def nested_plan(owner, label: str) -> None:
    """The pick's own (nested) plan, through auto_explain to the client, as role cip, READ ONLY."""
    notices: list[str] = []
    with owner.connect() as c:
        raw = c.connection.driver_connection
        raw.add_notice_handler(lambda d: notices.append(d.message_primary or ""))
        c.execute(sa.text("LOAD 'auto_explain'"))
        for s in ("auto_explain.log_min_duration = 0", "auto_explain.log_nested_statements = on",
                  "auto_explain.log_analyze = on", "auto_explain.log_timing = off", "auto_explain.log_level = notice",
                  "client_min_messages = notice"):
            c.execute(sa.text("SET LOCAL " + s))
        c.execute(sa.text("SET LOCAL ROLE cip"))
        who = c.execute(sa.text("select current_user, current_setting('transaction_read_only')")).one()
        _bind(c, "NB", "planner")
        notices.clear()
        c.execute(sa.text("select count(*) from public.cip_sev_current_observation_ids()")).scalar_one()
        c.rollback()
    inner = [n for n in notices if "line_identity_key" in n and "DISTINCT ON" in n]
    say(f"--- {label}: nested plan of the pick (auto_explain, role {who[0]}, read_only={who[1]}, NB)")
    for n in inner[:1]:
        for ln in n.splitlines():
            if any(k in ln for k in ("Query Text", "Duration", "Scan", "Sort", "Unique", "Heap Fetches", "Subquery")):
                say("    " + ln.rstrip()[:170])
    if not inner:
        say("    (no nested plan captured;", len(notices), "notices)")


def catalogue(conn) -> None:
    say("  pick proconfig:", conn.execute(sa.text(
        "select proconfig from pg_proc where proname = 'cip_sev_current_observation_ids'")).scalar())
    for t in FOUR:
        q = conn.execute(sa.text("select cmd, coalesce(qual, '') like '%request_role%', "
                                 "coalesce(with_check, '') like '%request_role%' from pg_policies "
                                 "where tablename = :t order by cmd"), {"t": t}).all()
        say(f"  {t} policies (cmd, using has steward rule, check has steward rule):", [tuple(r) for r in q])
    say("  md5 of the four tables' policy texts:", policy_md5(conn))
    vd = conn.execute(sa.text("select pg_get_viewdef('shipment_evidence_current'::regclass)")).scalar_one()
    say("  view uses current pick:", "cip_sev_current_observation_ids" in vd)


def policy_md5(conn) -> str:
    return conn.execute(sa.text(
        "select md5(string_agg(tablename || cmd || coalesce(qual, '') || coalesce(with_check, ''), '|' "
        "order by tablename, cmd)) from pg_policies where tablename = any(:t)"), {"t": list(FOUR)}).scalar()


def capture(tag: str) -> None:
    for i in (1, 2):
        cap_json = os.path.join(HERE, f"N0065_r5_cap_cip_{tag}_{i}.json")
        say(f"heavy-path capture {tag} run {i} (unset, '*', NB; READ ONLY, statement_timeout 60 s) ...")
        out = subprocess.run([sys.executable, os.path.join(HERE, "n0065_capture.py"), cap_json, "unset,star,NB", HEAVY],
                             cwd=API, capture_output=True, text=True, timeout=1800, env=child_env())
        for ln in (out.stdout or "").splitlines():
            if ln.startswith(("unset", "star", "NB", "database")):
                say("  " + ln[:200])
        if out.returncode:
            say("  capture exit", out.returncode, (out.stderr or "")[-400:])


def run_alembic(owner_url: str, action: str, target: str) -> None:
    os.environ["DATABASE_URL_SYNC_MIGRATE"] = owner_url
    get_settings.cache_clear()
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(API, "alembic.ini"))
    say(f"{time.strftime('%H:%M:%S')} alembic {action} {target} ...")
    t0 = time.perf_counter()
    (command.downgrade if action == "downgrade" else command.upgrade)(cfg, target)
    say(f"  done in {round(time.perf_counter() - t0, 1)} s")


def main() -> None:
    downgrade = "--downgrade" in sys.argv
    say("=" * 70)
    say("N-0065 round 5 apply", "SMOKE (read only)" if SMOKE else ("DOWNGRADE" if downgrade else "UPGRADE"),
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
        cfg = c.execute(sa.text("select proconfig from pg_proc where proname = 'cip_sev_current_observation_ids'")).scalar()
        md5 = policy_md5(c)
        say(f"[app]   pick proconfig = {cfg} | four-table policy md5 = {md5}")
        c.rollback()

    if SMOKE:
        if rev != [FROM_REV]:
            fail(f"alembic is {rev}, expected {FROM_REV}")
        if md5 != POLICY_MD5_0026 or any(x.startswith(("enable_sort", "enable_incremental_sort")) for x in (cfg or [])):
            fail("cip is not in the tested 0026 state")
        per_scope(ae, ae, "SMOKE (expected computed as the app role under '*')", "0026")
        helper_times(ae, "SMOKE")
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
        say(f"[owner] current_database() = {db} | role = {who[0]} super={who[1]} bypassrls={who[2]} "
            f"| alembic = {alembic_current(c)} | {c.execute(sa.text('show server_version')).scalar()}")
        if db != "cip":
            fail("owner connection is not on cip")
        if not who[1]:
            fail("owner role is not superuser")
        c.rollback()

    if downgrade:
        if rev != [TO_REV]:
            fail(f"alembic is {rev}, expected {TO_REV}")
        run_alembic(owner_url, "downgrade", FROM_REV)
        with oe.connect() as c:
            say(f"[owner] alembic now = {alembic_current(c)}")
            catalogue(c)
            c.rollback()
        per_scope(oe, ae, "AFTER DOWNGRADE (0026)", "0026")
        return

    if rev != [FROM_REV]:
        fail(f"alembic is {rev}, expected {FROM_REV}")
    if md5 != POLICY_MD5_0026 or any(x.startswith(("enable_sort", "enable_incremental_sort")) for x in (cfg or [])):
        fail("cip is not in the tested 0026 state (policy md5 or pick config differ)")
    say("preflight OK. No app code changed this round: the API is not restarted.")

    bad_before = per_scope(oe, ae, "BEFORE (0026)", "0026")
    say(f"before: mismatches against the 0026 rule = {bad_before}")
    helper_times(ae, "BEFORE (0026)")
    nested_plan(oe, "BEFORE (0026)")
    capture("before_0027")

    run_alembic(owner_url, "upgrade", TO_REV)
    with oe.connect() as c:
        say(f"[owner] current_database() = {c.execute(sa.text('select current_database()')).scalar_one()}"
            f" | alembic now = {alembic_current(c)}")
        catalogue(c)
        c.rollback()

    bad = per_scope(oe, ae, "AFTER (0027)", "0027")
    if bad:
        say(f"MISMATCHES: {bad}. Rolling back to {FROM_REV} now (tested downgrade).")
        run_alembic(owner_url, "downgrade", FROM_REV)
        with oe.connect() as c:
            say(f"[owner] alembic now = {alembic_current(c)}")
            catalogue(c)
            c.rollback()
        per_scope(oe, ae, "AFTER ROLLBACK (0026)", "0026")
        fail("0027 rolled back because of mismatches")
    say("after 0027: every per-scope cell matches the decision")
    helper_times(ae, "AFTER (0027)")
    nested_plan(oe, "AFTER (0027)")
    capture("after_0027")

    restart("worker")
    st = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
    for ln in st.splitlines():
        if ln.strip().startswith(("api", "worker", "tunnel")) or "local api" in ln:
            say("  " + ln.strip())
    say("finished", time.strftime("%H:%M:%S"), "- mismatches:", bad)


if __name__ == "__main__":
    main()
