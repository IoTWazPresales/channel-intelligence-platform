"""GOV-008 review 2026-11-02: read-only checks of the On the water / shipment data claims on cip.

Every connection is forced read-only: asyncpg engines get server_settings default_transaction_read_only=on (patched
before the app is imported) and libpq/psycopg connections get PGOPTIONS from the caller. A write would raise
"cannot execute ... in a read-only transaction".

Run from apps/api:  PYTHONPATH=. PGOPTIONS="-c default_transaction_read_only=on" DATABASE_URL=...cip DATABASE_URL_SYNC=...cip
    .venv/Scripts/python.exe -X utf8 <this file>
"""
import asyncio
import json
import os
import sys

assert "default_transaction_read_only=on" in os.environ.get("PGOPTIONS", ""), "PGOPTIONS read-only required"
assert os.environ.get("DATABASE_URL", "").endswith("/cip"), "expects cip"

import sqlalchemy.ext.asyncio as sa_async  # noqa: E402

_orig = sa_async.create_async_engine


def _ro_engine(*a, **kw):
    ca = kw.setdefault("connect_args", {})
    ca.setdefault("server_settings", {})["default_transaction_read_only"] = "on"
    return _orig(*a, **kw)


sa_async.create_async_engine = _ro_engine

import httpx  # noqa: E402
import psycopg  # noqa: E402

SQL = {
    "readonly_check": "SELECT current_database(), current_setting('default_transaction_read_only'), current_user",
    "alembic": "SELECT version_num FROM alembic_version",
    "audit_events": """SELECT id, area, action, target_type, target_id, created_at,
                              left(detail::text, 600) AS detail
                       FROM platform_audit_event WHERE id IN (18, 22, 26) ORDER BY id""",
    "audit_since_17": "SELECT id, action, target_id, created_at FROM platform_audit_event WHERE id >= 17 ORDER BY id",
    "line_states": """SELECT line_state, count(*) AS lines, sum(quantity) AS units FROM fact_inbound_shipment
                      GROUP BY line_state ORDER BY line_state""",
    "superseded_total": """SELECT count(*) AS lines, sum(quantity) AS units,
                                  count(*) FILTER (WHERE superseded_by_fact_id IS NULL) AS no_pointer,
                                  count(*) FILTER (WHERE superseded_by_fact_id IS NOT NULL AND NOT EXISTS
                                      (SELECT 1 FROM fact_inbound_shipment k WHERE k.id = f.superseded_by_fact_id)) AS dangling
                           FROM fact_inbound_shipment f WHERE line_state = 'closed_superseded'""",
    "superseded_pointer_target_states": """SELECT k.line_state, count(*) FROM fact_inbound_shipment f
                           JOIN fact_inbound_shipment k ON k.id = f.superseded_by_fact_id
                           WHERE f.line_state = 'closed_superseded' GROUP BY k.line_state""",
    "orphan_open_all_jobs": """SELECT import_job_id, count(*) AS lines, sum(quantity) AS units FROM fact_inbound_shipment
                               WHERE shipment_evidence_line_id IS NULL AND lower(line_state) = 'open_order'
                               GROUP BY import_job_id ORDER BY import_job_id""",
    "orphan_shipped_all_jobs": """SELECT import_job_id, count(*) AS lines, sum(quantity) AS units FROM fact_inbound_shipment
                               WHERE shipment_evidence_line_id IS NULL AND lower(line_state) = 'shipped'
                               GROUP BY import_job_id ORDER BY import_job_id DESC LIMIT 15""",
    "job1697_evidence": "SELECT count(*) FROM shipment_evidence_line WHERE import_job_id = 1697",
    "job1697_obs": "SELECT count(*) FROM shipment_evidence_observation WHERE import_job_id = 1697",
    "job1697_facts_by_state": """SELECT line_state, count(*), sum(quantity) FROM fact_inbound_shipment WHERE import_job_id = 1697
                                 GROUP BY line_state ORDER BY 1""",
    "dup_open_same_order_line": """SELECT import_job_id, order_no, order_line, item_code, count(*) AS n, sum(quantity) AS units
                                   FROM fact_inbound_shipment WHERE lower(line_state) = 'open_order' AND order_no IS NOT NULL
                                   GROUP BY 1,2,3,4 HAVING count(*) > 1 ORDER BY n DESC LIMIT 20""",
    "orphan_retired_facts": """SELECT f.id, f.line_state, f.quantity, f.superseded_by_fact_id, k.quantity AS keeper_qty,
                                      k.line_state AS keeper_state, k.import_job_id AS keeper_job
                               FROM fact_inbound_shipment f LEFT JOIN fact_inbound_shipment k ON k.id = f.superseded_by_fact_id
                               WHERE f.id IN (148768,148777,148780,148785,148786,148801,157127,163464,163465) ORDER BY f.id""",
    "rls_flags": """SELECT relname, relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) AS owner FROM pg_class
                    WHERE relname IN ('fact_inbound_shipment','shipment_evidence_line','shipment_evidence_observation','port_condition',
                                      'dashboard','dashboard_widget','saved_report','cpor_case','platform_audit_event','import_job')
                    ORDER BY relname""",
    "role_attrs": "SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
}


def sql_checks() -> dict:
    out: dict = {}
    with psycopg.connect("postgresql://cip:cip@localhost:5432/cip", options="-c default_transaction_read_only=on") as c:
        with c.cursor() as cur:
            cur.execute("SET statement_timeout = '60s'")
            for k, q in SQL.items():
                try:
                    cur.execute(q)
                    cols = [d.name for d in cur.description]
                    out[k] = [dict(zip(cols, r)) for r in cur.fetchall()]
                except Exception as e:  # noqa: BLE001
                    c.rollback()
                    out[k] = f"ERROR {type(e).__name__}: {e}"
            # prove the connection refuses writes
            try:
                cur.execute("CREATE TEMP TABLE _gov008_probe(x int)")
                out["write_refused"] = False
            except Exception as e:  # noqa: BLE001
                out["write_refused"] = f"{type(e).__name__}: {str(e).splitlines()[0]}"
            c.rollback()
    return out


async def app_checks() -> dict:
    sys.path[:0] = ["."]
    from app.core.security import Role, get_current_user, get_optional_current_user
    from app.main import app

    stand_in = {"id": "0", "role": Role.ADMIN, "tenant_id": "default", "email": "gov008@example.invalid", "display_name": "gov008"}
    app.dependency_overrides[get_optional_current_user] = lambda: stand_in
    app.dependency_overrides[get_current_user] = lambda: stand_in
    out: dict = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=180) as c:
        r = await c.get("/api/v1/shipping/on-the-water")
        out["otw_status"] = r.status_code
        d = r.json()
        out["as_of"], out["report_date"], out["report_stale"] = d.get("as_of"), d.get("report_date"), d.get("report_stale")
        out["tiles"] = d.get("tiles")
        vs = d.get("vessels") or []
        out["vessels"] = len(vs)
        out["vessels_overdue"] = sum(1 for v in vs if v.get("overdue"))
        out["vessel_units_sum"] = sum(float(v.get("units") or 0) for v in vs)
        out["vessel_lines_sum"] = sum(int(v.get("lines") or 0) for v in vs)
        out["overdue_units"] = sum(float(v.get("units") or 0) for v in vs if v.get("overdue"))
        out["vessel_rows"] = [{k: v.get(k) for k in ("forwarder", "lane_label", "eta", "slip_days", "overdue", "units", "lines")} for v in vs]
        nl = d.get("needs_look")
        out["needs_look"] = None if nl is None else {k: nl.get(k) for k in ("lines", "units", "since", "days")}
        out["ports"] = [(p.get("code"), p.get("waiting_units")) for p in d.get("port_rows") or []]
        n = await c.get("/api/v1/shipping/lines", params={"cohort": "needs_look", "limit": 500})
        items = n.json().get("items", [])
        out["needs_look_grid"] = {"status": n.status_code, "rows": len(items), "units": sum(float(i.get("quantity") or 0) for i in items)}
        # unauthenticated: drop the overrides and ask again
        app.dependency_overrides.clear()
        u = await c.get("/api/v1/shipping/on-the-water")
        out["unauthenticated_otw_status"] = u.status_code
        p = await c.get("/api/v1/shipping/port-conditions")
        out["unauthenticated_port_conditions_status"] = p.status_code
    return out


if __name__ == "__main__":
    res = {"sql": sql_checks()}
    try:
        res["app"] = asyncio.run(app_checks())
    except Exception as e:  # noqa: BLE001
        res["app"] = f"ERROR {type(e).__name__}: {e}"
    print(json.dumps(res, indent=1, default=str))
