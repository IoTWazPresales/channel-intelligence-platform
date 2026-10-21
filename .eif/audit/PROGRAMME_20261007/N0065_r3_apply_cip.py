"""N-0065 round 3: apply migration 20261007_0025 to cip (Warren runs this; one command).

From the project root, in PowerShell:

    apps\\api\\.venv\\Scripts\\python.exe .eif\\audit\\PROGRAMME_20261007\\N0065_r3_apply_cip.py

It asks for the cip OWNER connection URL (the `postgres` role that owns the gate functions
and the shipment_evidence_current view) with a hidden prompt, unless DATABASE_URL_SYNC_MIGRATE
is already set in the environment. The URL is used in-process only and never printed.

Order (why): the running API still writes '' for "no lines". From 0025 the database reads ''
as open, so the API must run the round-3 code (which writes the '!' sentinel; under 0024 '!'
also means no lines) BEFORE the migration lands.

  1. Preflight (READ ONLY): current_database() = cip for both the app role and the owner,
     alembic current = 20261006_0024, owner role flags, app code writes '!' for no lines.
  2. Restart the API through the supervisor and wait until it is healthy with a new pid.
  3. alembic upgrade 20261007_0025 (alembic env.py with DATABASE_URL_SYNC_MIGRATE in-process).
  4. Print the new revision and the catalogue state (policies, view option, functions).
  5. Parity spot check, READ ONLY, as the app role cip, one fresh connection per scope:
     dim_product + fact_sales_sellout + fact_inventory_distributor + weeks_of_cover_observation
     under unset / '*' / one line / '!', against counts the owner computes without row security.
  6. Timings of the N0065_PERF.md heavy paths (READ ONLY capture, statement_timeout 60 s).
  7. Restart the worker; final supervisor status (expects api /auth/me=401).

Everything is also written to N0065_r3_apply_cip_output.txt next to this file.
Rollback if needed (same owner URL, API code is compatible with 0024):
    apps\\api\\.venv\\Scripts\\python.exe .eif\\audit\\PROGRAMME_20261007\\N0065_r3_apply_cip.py --downgrade
"""

from __future__ import annotations

import getpass
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
FROM_REV, TO_REV = "20261006_0024", "20261007_0025"
SPOT_TABLES = ("fact_sales_sellout", "fact_inventory_distributor", "weeks_of_cover_observation")
HEAVY = "/api/v1/brief/signals,/api/v1/channel-ops/cover-distribution,/api/v1/supply/overview,/api/v1/lineup/net-requirement"

os.chdir(API)
sys.path.insert(0, API)
_log = open(os.path.join(HERE, "N0065_r3_apply_cip_smoke.txt" if "--smoke" in sys.argv
                          else "N0065_r3_apply_cip_output.txt"), "a", encoding="utf-8")


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
    """Child processes never inherit the owner URL."""
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


def catalogue(conn) -> None:
    kinds = conn.execute(sa.text("""
        select case when qual like '%cip_product_id_visible%' then 'definer_fn_0024'
                    when qual like '%dim_product%' then 'inline_0025' else 'line_fn' end, count(*)
        from pg_policies where policyname = 'cip_pl_select' group by 1 order by 1""")).all()
    say("  select policies:", [tuple(k) for k in kinds])
    say("  shipment_evidence_current reloptions:", conn.execute(sa.text(
        "select reloptions from pg_class where relname = 'shipment_evidence_current'")).scalar())
    fns = conn.execute(sa.text("""select proname, prosecdef from pg_proc
                                  where proname like 'cip_product_%' order by 1""")).all()
    say("  functions (name, security definer):", [tuple(f) for f in fns])


def main() -> None:
    downgrade = "--downgrade" in sys.argv
    say("=" * 70)
    say("N-0065 apply", "DOWNGRADE" if downgrade else "UPGRADE", time.strftime("%Y-%m-%d %H:%M:%S"))
    s = get_settings()
    app_url = s.database_url_sync
    if database_name_from_url(app_url) != "cip":
        fail("DATABASE_URL_SYNC does not name cip")
    owner_url = (os.environ.get("DATABASE_URL_SYNC_MIGRATE") or s.database_url_sync_migrate or "").strip()
    if not owner_url:
        owner_url = getpass.getpass("cip OWNER connection URL (postgres role; hidden): ").strip()
    if not owner_url:
        fail("no owner URL given")
    if database_name_from_url(owner_url) != "cip":
        fail("the owner URL does not name database cip")

    # 1. Preflight
    oe = _engine(owner_url, read_only=True)
    with oe.connect() as c:
        db = c.execute(sa.text("select current_database()")).scalar_one()
        who = c.execute(sa.text(
            "select current_user, rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
        rev = alembic_current(c)
        say(f"[owner] current_database() = {db} | role = {who[0]} super={who[1]} bypassrls={who[2]} | alembic = {rev}")
        if db != "cip":
            fail("owner connection is not on cip")
        if not who[1]:
            fail("owner role is not superuser (needs to own tables, functions and the view)")
        c.rollback()
    ae = _engine(app_url, read_only=True)
    with ae.connect() as c:
        db = c.execute(sa.text("select current_database()")).scalar_one()
        who = c.execute(sa.text(
            "select current_user, rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
        say(f"[app]   current_database() = {db} | role = {who[0]} super={who[1]} bypassrls={who[2]}")
        if db != "cip" or who[1] or who[2]:
            fail("app connection must be cip, not superuser, no BYPASSRLS")
        c.rollback()

    from app.core.product_line_scope import NO_PRODUCT_LINES, scope_csv

    if NO_PRODUCT_LINES != "!" or scope_csv(frozenset()) != "!":
        fail("app code on disk does not write the '!' sentinel for no lines")

    target = FROM_REV if downgrade else TO_REV
    if rev == [target]:
        say(f"alembic already at {target}; skipping the migration step")
    else:
        expected_from = TO_REV if downgrade else FROM_REV
        if rev != [expected_from]:
            fail(f"alembic is {rev}, expected {expected_from}")
        # 2. API first, so no running process writes '' for no lines once '' means open.
        if not downgrade:
            restart("api")
        # 3. Migrate through alembic env.py (DATABASE_URL_SYNC_MIGRATE in-process only).
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

    # 4. New revision and catalogue
    with oe.connect() as c:
        say(f"[owner] current_database() = {c.execute(sa.text('select current_database()')).scalar_one()}"
            f" | alembic now = {alembic_current(c)}")
        catalogue(c)
        c.rollback()
    if downgrade:
        say("Downgrade done. Restart the API/worker if you want them to pick up nothing new; code is 0024-compatible.")
        return

    # 5. Parity spot check (READ ONLY)
    bad = spot_check(oe, ae)

    # 6. Timings (READ ONLY capture)
    cap_json = os.path.join(HERE, "N0065_r3_cap_cip_0025.json")
    say("timings (unset, '*', NB) for the heavy paths ...")
    out = subprocess.run([sys.executable, os.path.join(HERE, "n0065_capture.py"), cap_json, "unset,star,NB", HEAVY],
                         cwd=API, capture_output=True, text=True, timeout=900, env=child_env())
    for ln in (out.stdout or "").splitlines():
        if ln.startswith(("unset", "star", "NB", "database")):
            say("  " + ln)
    if out.returncode:
        say("  capture exit", out.returncode, (out.stderr or "")[-400:])

    # 7. Worker restart and final status
    restart("worker")
    st = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
    for ln in st.splitlines():
        if ln.strip().startswith(("api", "worker")) or "local api" in ln:
            say("  " + ln.strip())
    say("finished", time.strftime("%H:%M:%S"), "- mismatches:", bad)
    sys.exit(1 if bad else 0)


def spot_check(oe, ae) -> int:
    """Counts as the app role per scope vs counts computed on ``oe`` (owner: no row security)."""
    with oe.connect() as c:
        line = c.execute(sa.text("""select product_line from dim_product where product_line is not null
                                    group by 1 order by (product_line = 'NB') desc, count(*) desc limit 1""")).scalar()
        exp: dict[tuple[str, str], int] = {}
        total_dim = c.execute(sa.text("select count(*) from dim_product")).scalar_one()
        line_dim = c.execute(sa.text("select count(*) from dim_product where product_line = :l"), {"l": line}).scalar_one()
        for scope in ("unset", "*"):
            exp[("dim_product", scope)] = total_dim
        exp[("dim_product", line)] = line_dim
        exp[("dim_product", "!")] = 0
        for t in SPOT_TABLES:
            tot = c.execute(sa.text(f"select count(*) from {t}")).scalar_one()
            nul = c.execute(sa.text(f"select count(*) from {t} where product_id is null")).scalar_one()
            inl = c.execute(sa.text(f"""select count(*) from {t} x where x.product_id is null or x.product_id in
                                        (select id from dim_product where product_line = :l)"""), {"l": line}).scalar_one()
            orph = c.execute(sa.text(f"""select count(*) from {t} x where x.product_id is not null and not exists
                                         (select 1 from dim_product p where p.id = x.product_id)""")).scalar_one()
            exp[(t, "unset")] = tot
            exp[(t, "*")] = tot
            exp[(t, line)] = inl
            exp[(t, "!")] = nul
            say(f"  [owner] {t}: total={tot} null_product={nul} orphan_product={orph}")
        c.rollback()
    bad = 0
    say(f"parity spot check as app role (one line = {line!r}):")
    for scope in ("unset", "*", line, "!"):
        with ae.connect() as c:
            if scope != "unset":
                c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": scope})
            setting = c.execute(sa.text("select current_setting('cip.product_lines', true)")).scalar()
            got = {"dim_product": c.execute(sa.text("select count(*) from dim_product")).scalar_one()}
            for t in SPOT_TABLES:
                got[t] = c.execute(sa.text(f"select count(*) from {t}")).scalar_one()
            view = c.execute(sa.text("select count(*) from shipment_evidence_current")).scalar_one()
            c.rollback()
        for t, n in got.items():
            ok = n == exp[(t, scope)]
            bad += 0 if ok else 1
            say(f"  scope={scope!r:8} setting={setting!r:8} {t:28} got={n:7} expected={exp[(t, scope)]:7} {'OK' if ok else 'MISMATCH'}")
        say(f"  scope={scope!r:8} shipment_evidence_current rows={view}")
    if bad:
        say(f"PARITY MISMATCHES: {bad}. To roll back run this script with --downgrade, then restart the API.")
    else:
        say("parity spot check: all cells match")
    return bad


def smoke() -> None:
    """--smoke: READ ONLY, app role only, no owner, no migration, no restarts.

    Exercises the spot-check code on the current revision. Expected counts come from the app
    role with the setting unset, which is the reference for 0024 (orphans hidden there).
    """
    say("=" * 70)
    say("N-0065 apply script SMOKE (read only, no changes)", time.strftime("%Y-%m-%d %H:%M:%S"))
    ae = _engine(get_settings().database_url_sync, read_only=True)
    with ae.connect() as c:
        say(f"[app] current_database() = {c.execute(sa.text('select current_database()')).scalar_one()}"
            f" | alembic = {alembic_current(c)} | read_only = {c.execute(sa.text('show transaction_read_only')).scalar_one()}")
        catalogue(c)
        c.rollback()
    st = supervisor(os.path.join("scripts", "cip-supervisor-status.ps1"), "-Local")
    say("supervisor parse: api", component_state(st, "api"), "worker", component_state(st, "worker"))
    bad = spot_check(ae, ae)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    if "--smoke" in sys.argv:
        smoke()
    else:
        main()
