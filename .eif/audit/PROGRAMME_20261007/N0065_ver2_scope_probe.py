"""GOV-008 N-0065 re-verification (RUN-20261008-N0065-VER2): D-0056 on cip under 0025, both session paths.

READ ONLY. Run from the project root with the API virtualenv:
    apps/api/.venv/Scripts/python.exe .eif/audit/PROGRAMME_20261007/N0065_ver2_scope_probe.py
Every transaction runs SET TRANSACTION READ ONLY and asserts transaction_read_only = on before
any count. Only SELECT / EXPLAIN (no ANALYZE) statements. The one COMMIT is of a read-only
transaction (to leave the pooled backend in its post-commit state). Prints current_database()
first and refuses unless it is cip. Never prints a URL, credential, user name or email.
"""

from __future__ import annotations

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

from sqlalchemy import text  # noqa: E402

from app.core import security  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.core.product_line_scope import (  # noqa: E402
    product_line_scope_for,
    request_editable_product_lines,
    request_product_lines,
)

ONE = "NB"
SETS = "select current_setting('cip.product_lines', true), current_setting('cip.editable_product_lines', true)"


def ro(conn_exec) -> None:
    conn_exec(text("SET TRANSACTION READ ONLY"))


def sync_counts(label: str, s) -> dict:
    s.execute(text("SET TRANSACTION READ ONLY"))
    assert s.execute(text("show transaction_read_only")).scalar_one() == "on"
    pid = s.execute(text("select pg_backend_pid()")).scalar_one()
    r, e = s.execute(text(SETS)).one()
    out = {
        "pid": pid,
        "read": r,
        "edit": e,
        "dim_product": s.execute(text("select count(*) from dim_product")).scalar_one(),
        "fact_demand_forecast": s.execute(text("select count(*) from fact_demand_forecast")).scalar_one(),
        "other_line": s.execute(text("select count(*) from dim_product where product_line is distinct from :l"),
                                {"l": ONE}).scalar_one(),
        "editable_fn": s.execute(text(
            "select count(*) from dim_product where cip_product_line_editable(product_line)")).scalar_one(),
        "view": s.execute(text("select count(*) from shipment_evidence_current")).scalar_one(),
    }
    print(f"  [{label}] backend={pid} read={r!r} edit={e!r} dim_product={out['dim_product']} "
          f"forecast={out['fact_demand_forecast']} rows_not_{ONE}={out['other_line']} "
          f"editable(fn)={out['editable_fn']} shipment_evidence_current={out['view']}")
    return out


async def async_counts(label: str, s) -> dict:
    await s.execute(text("SET TRANSACTION READ ONLY"))
    assert (await s.execute(text("show transaction_read_only"))).scalar_one() == "on"
    r, e = (await s.execute(text(SETS))).one()
    dp = (await s.execute(text("select count(*) from dim_product"))).scalar_one()
    fc = (await s.execute(text("select count(*) from fact_demand_forecast"))).scalar_one()
    ol = (await s.execute(text("select count(*) from dim_product where product_line is distinct from :l"),
                          {"l": ONE})).scalar_one()
    ed = (await s.execute(text(
        "select count(*) from dim_product where cip_product_line_editable(product_line)"))).scalar_one()
    vw = (await s.execute(text("select count(*) from shipment_evidence_current"))).scalar_one()
    print(f"  [{label}] read={r!r} edit={e!r} dim_product={dp} forecast={fc} rows_not_{ONE}={ol} "
          f"editable(fn)={ed} shipment_evidence_current={vw}")
    return {"read": r, "edit": e, "dim_product": dp, "fact_demand_forecast": fc, "other_line": ol,
            "editable_fn": ed, "view": vw}


def sync_path(label: str) -> dict:
    from app.db.session_sync import SessionLocal

    with SessionLocal() as s:
        out = sync_counts(label + " sync SessionLocal", s)
        s.rollback()
        # second transaction in the same session after a (read-only) commit: rebound?
        s.execute(text("SET TRANSACTION READ ONLY"))
        s.execute(text("select 1"))
        s.commit()
        r, e = s.execute(text(SETS)).one()
        n = s.execute(text("select count(*) from dim_product")).scalar_one()
        print(f"  [{label} sync after commit] read={r!r} edit={e!r} dim_product={n}")
        out["after_commit_dim"] = n
        s.rollback()
    return out


async def router_path(label: str, user: dict) -> dict:
    """Drive the real router dependency with the real get_db session, then both session paths."""
    from app.api.deps import get_db
    from app.api.v1.router import _bind_request_tenant

    gen_db = get_db()
    db = await gen_db.__anext__()
    try:
        cur = (await db.execute(text("select current_database()"))).scalar_one()
        assert cur == "cip", cur
        await db.execute(text("SET TRANSACTION READ ONLY"))
        dep = _bind_request_tenant(user=user, db=db)
        await dep.__anext__()
        try:
            print(f"[{label}] bound read={request_product_lines.get()!r} edit={request_editable_product_lines.get()!r}")
            a = await async_counts(label + " async get_db", db)
            await db.rollback()
            # threadpool hand-off as FastAPI does for a sync def endpoint / asyncio.to_thread
            s = await asyncio.to_thread(sync_path, label)
        finally:
            try:
                await dep.__anext__()
            except StopAsyncIteration:
                pass
        print(f"[{label}] after request: read ctx={request_product_lines.get()!r}")
        return {"async": a, "sync": s}
    finally:
        await db.rollback()
        await gen_db.aclose()


def bound_path(label: str, read, edit) -> dict:
    """One-line scope through the helper (no grant row exists to drive the router lookup)."""
    t1 = request_product_lines.set(read)
    t2 = request_editable_product_lines.set(edit)
    try:
        print(f"[{label}] bound read={read!r} edit={edit!r}")
        return sync_path(label)
    finally:
        request_product_lines.reset(t1)
        request_editable_product_lines.reset(t2)


def explain_update(label: str, read, edit) -> None:
    """EXPLAIN (no ANALYZE) of an UPDATE: shows the edit policy qual; nothing executes."""
    from app.db.session_sync import SessionLocal

    t1 = request_product_lines.set(read)
    t2 = request_editable_product_lines.set(edit)
    try:
        with SessionLocal() as s:
            s.execute(text("SET TRANSACTION READ ONLY"))
            assert s.execute(text("show transaction_read_only")).scalar_one() == "on"
            for tbl in ("dim_product", "fact_sales_sellout"):
                col = "updated_at" if tbl == "dim_product" else "product_id"
                sql = (f"EXPLAIN (COSTS OFF) UPDATE {tbl} SET {col} = {col} "
                       f"WHERE id IN (select id from {tbl} limit 1)")
                plan = [r[0] for r in s.execute(text(sql)).all()]
                print(f"  [{label} EXPLAIN UPDATE {tbl}]")
                for ln in plan:
                    if "Filter" in ln or "SubPlan" in ln or "Update on" in ln or "cip_" in ln:
                        print("     ", ln.strip()[:240])
            s.rollback()
    finally:
        request_product_lines.reset(t1)
        request_editable_product_lines.reset(t2)


def pool_leftover() -> None:
    """Leftover '' on a pooled sync backend: open only for unscoped workers; scoped requests set their own."""
    from app.db.session_sync import SessionLocal, sync_engine

    print("[pool] sync pool status:", sync_engine.pool.status())

    def tx(label, read, edit):
        tok = None
        if read is not None or edit is not None:
            tok = (request_product_lines.set(read), request_editable_product_lines.set(edit))
        try:
            with SessionLocal() as s:
                s.execute(text("SET TRANSACTION READ ONLY"))
                pid = s.execute(text("select pg_backend_pid()")).scalar_one()
                r, e = s.execute(text(SETS)).one()
                n = s.execute(text("select count(*) from dim_product")).scalar_one()
                s.commit()  # read-only commit: leaves the backend's post-transaction state
                r2, _ = s.execute(text(SETS)).one()  # new tx (listener runs again)
                s.rollback()
            print(f"  [{label}] backend={pid} in-tx read={r!r} edit={e!r} dim_product={n}")
            return pid
        finally:
            if tok:
                request_product_lines.reset(tok[0])
                request_editable_product_lines.reset(tok[1])

    p1 = tx(f"scoped {ONE} read-only request", frozenset({ONE}), frozenset())
    # raw Core connection, no ORM listener: what a leftover '' looks like to unscoped code
    with sync_engine.connect() as c:
        c.execute(text("SET TRANSACTION READ ONLY"))
        pid = c.execute(text("select pg_backend_pid()")).scalar_one()
        r, e = c.execute(text(SETS)).one()
        n = c.execute(text("select count(*) from dim_product")).scalar_one()
        c.rollback()
    print(f"  [raw Core connection, unscoped] backend={pid} same_backend={pid == p1} read={r!r} edit={e!r} dim_product={n}")
    tx("unscoped worker SessionLocal", None, None)
    tx("scoped non-admin no rows", frozenset(), frozenset())
    tx(f"scoped {ONE} again", frozenset({ONE}), frozenset())
    tx("scoped admin", frozenset({"*"}), frozenset({"*"}))
    tx("unscoped worker again", None, None)
    print("[pool] sync pool status:", sync_engine.pool.status())


def main() -> int:
    s = get_settings()
    print("settings.cip_auth_mode =", (s.cip_auth_mode or "stub"))
    from app.db.session_sync import SessionLocal

    with SessionLocal() as x:
        db = x.execute(text("select current_database()")).scalar_one()
        print("current_database() =", db)
        assert db == "cip", "refusing: not cip"
        x.execute(text("SET TRANSACTION READ ONLY"))
        print("alembic =", x.execute(text("select version_num from alembic_version")).scalars().all())
        who = x.execute(text("select rolname, rolsuper, rolbypassrls from pg_roles where rolname = current_user")).one()
        print("role =", who[0], "super =", who[1], "bypassrls =", who[2])
        print("functions =", [tuple(r) for r in x.execute(text(
            "select proname, prosecdef, provolatile from pg_proc where proname like 'cip_product_line_%' order by 1")).all()])
        print("view reloptions =", x.execute(text(
            "select reloptions from pg_class where relname='shipment_evidence_current'")).scalar())
        print("policy kinds =", [tuple(r) for r in x.execute(text(
            "select case when qual like '%dim_product%' then 'inline_0025' when qual like '%cip_product_id%' "
            "then 'definer_0024' else 'line_fn' end, cmd, count(*) from pg_policies where policyname like 'cip_pl_%' "
            "group by 1,2 order by 1,2")).all()])
        print("grant rows =", x.execute(text("select count(*) from user_product_line_access")).scalar_one())
        k = x.execute(text("select count(*) from dim_product where product_line = :l"), {"l": ONE}).scalar_one()
        print(f"unset count of line {ONE} (all visible) =", k)
        x.rollback()

    tenant = "default"
    # A numeric id with no grant rows (ids are serial; this one is far above any real user id).
    nonadmin = security._user_payload("987654321", security.Role.VIEWER, tenant_id=tenant)
    admin = security._user_payload("987654322", security.Role.ADMIN, tenant_id=tenant)
    worker = security._user_payload("worker-x", security.Role.ADMIN, tenant_id=tenant)

    res = {}
    res["nonadmin_empty"] = asyncio.run(router_path("non-admin viewer, no grant rows (router)", nonadmin))
    res["admin"] = asyncio.run(router_path("admin (router)", admin))
    res["worker_forged"] = asyncio.run(router_path("non-numeric id, admin role (router -> unset)", worker))
    rd, ed = product_line_scope_for(is_admin=False, assignments=[(ONE, False)])
    res["one_line_ro"] = bound_path(f"non-admin {ONE} read-only (helper)", rd, ed)
    rd2, ed2 = product_line_scope_for(is_admin=False, assignments=[(ONE, True)])
    res["one_line_rw"] = bound_path(f"non-admin {ONE} read+edit (helper)", rd2, ed2)
    res["unscoped"] = sync_path("unscoped worker (no contextvars)")

    explain_update(f"{ONE} read-only", rd, ed)
    pool_leftover()

    print("\nSUMMARY")
    for k_, v in res.items():
        if "async" in v:
            print(f"  {k_:16} async dim={v['async']['dim_product']} sync dim={v['sync']['dim_product']} "
                  f"sync after-commit dim={v['sync']['after_commit_dim']} forecast a/s="
                  f"{v['async']['fact_demand_forecast']}/{v['sync']['fact_demand_forecast']} "
                  f"editable a/s={v['async']['editable_fn']}/{v['sync']['editable_fn']} "
                  f"view a/s={v['async']['view']}/{v['sync']['view']}")
        else:
            print(f"  {k_:16} sync dim={v['dim_product']} after-commit dim={v['after_commit_dim']} "
                  f"forecast={v['fact_demand_forecast']} other-line={v['other_line']} editable={v['editable_fn']} view={v['view']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
