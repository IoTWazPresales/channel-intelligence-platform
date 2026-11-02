"""GOV-008 review 2026-11-02, N-0115 query model. Read-only probe.

Part 1: RLS / FORCE RLS / policies on cip_test and cip for every table a v2 model reads.
Part 2: read-only data-shape checks on cip (shipments line states, stock duplicates, tenants).
Every cip connection is default_transaction_read_only=on with a 60 s statement timeout.
Run: apps/api/.venv/Scripts/python.exe .eif/audit/REVIEW_20261102/query/p1_rls_and_cip_facts.py
"""
from __future__ import annotations

from pathlib import Path

import psycopg

OUT = Path(__file__).with_name("p1_output.txt")
LINES: list[str] = []


def out(s: str) -> None:
    LINES.append(s)
    print(s, flush=True)


TABLES = [
    "fact_sales_sellout", "fact_customer_sellthrough", "cpor_case_line", "cpor_case", "fact_returns",
    "fact_sales_sellin", "fact_inbound_shipment", "fact_inventory_distributor", "commercial_lineup_line",
    "commercial_lineup_case", "fact_pricing", "dim_product", "dim_customer", "dim_distributor",
    "dim_region", "dim_channel",
]


def conn(db: str):
    return psycopg.connect(
        f"postgresql://cip:cip@localhost:5432/{db}",
        options="-c default_transaction_read_only=on",
    )


def rls(db: str) -> None:
    with conn(db) as c, c.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout='60s'")
        cur.execute("select current_user, rolsuper, rolbypassrls, current_setting('transaction_read_only') "
                    "from pg_roles where rolname=current_user")
        out(f"[{db}] role/super/bypassrls/ro: {cur.fetchone()}")
        cur.execute("select version_num from alembic_version")
        out(f"[{db}] alembic: {cur.fetchall()}")
        cur.execute(
            "select c.relname, pg_get_userbyid(c.relowner), c.relrowsecurity, c.relforcerowsecurity, "
            "(select count(*) from pg_attribute a where a.attrelid=c.oid and a.attname='tenant_id' and not a.attisdropped) "
            "from pg_class c join pg_namespace n on n.oid=c.relnamespace "
            "where n.nspname='public' and c.relname = any(%s) order by 1", (TABLES,))
        out(f"[{db}] table | owner | RLS | FORCE | has tenant_id")
        for r in cur.fetchall():
            out(f"[{db}]   {r}")
        cur.execute("select tablename, policyname, cmd, roles::text, qual from pg_policies "
                    "where schemaname='public' and tablename = any(%s) order by 1,2", (TABLES,))
        for r in cur.fetchall():
            q = (r[4] or "").replace("\n", " ")
            out(f"[{db}] policy {r[0]}.{r[1]} {r[2]} {r[3]} qual={q[:400]}")


def cip_shapes() -> None:
    with conn("cip") as c, c.cursor() as cur:
        cur.execute("SET LOCAL statement_timeout='60s'")
        cur.execute("select set_config('cip.product_lines','*',true)")
        cur.execute("select current_database(), current_setting('transaction_read_only')")
        out(f"[cip] db/ro: {cur.fetchone()}")
        cur.execute("select tenant_id, count(*) from fact_sales_sellout group by 1 order by 2 desc")
        out(f"[cip] sellout tenants: {cur.fetchall()}")
        cur.execute(
            "select lower(line_state), count(*), count(ship_confirm_date), coalesce(sum(quantity),0), "
            "coalesce(sum(quantity) filter (where ship_confirm_date is not null),0) "
            "from fact_inbound_shipment group by 1 order by 1")
        out("[cip] shipments state | lines | with ship_confirm | qty | qty with ship_confirm")
        for r in cur.fetchall():
            out(f"[cip]   {r}")
        cur.execute(
            "select count(*), coalesce(sum(n-1),0) from (select distributor_id, product_id, as_of_date, count(*) n "
            "from fact_inventory_distributor group by 1,2,3 having count(*)>1) d")
        out(f"[cip] distributor stock duplicate (dist,product,date) groups / extra rows: {cur.fetchone()}")
        cur.execute("select count(*), count(distinct as_of_date), count(distinct distributor_id), min(as_of_date), max(as_of_date) "
                    "from fact_inventory_distributor")
        out(f"[cip] distributor stock rows/dates/distributors/min/max: {cur.fetchone()}")
        for t in ("fact_returns", "fact_sales_sellin", "fact_pricing", "commercial_lineup_line"):
            cur.execute(f"select count(*) from {t}")
            out(f"[cip] {t} rows: {cur.fetchone()[0]}")
        # Lineup lines whose product tenant differs from the case tenant (tenant via dim_product).
        cur.execute(
            "select count(*), coalesce(sum(l.quantity_units),0) from commercial_lineup_line l "
            "left join dim_product p on p.id=l.product_id where p.id is null")
        out(f"[cip] lineup lines/units with no resolved product (dropped by tenant-via-product join): {cur.fetchone()}")
        cur.execute(
            "select count(*) from fact_returns r join dim_customer cu on cu.id=r.customer_id "
            "join dim_product p on p.id=r.product_id where cu.tenant_id is distinct from p.tenant_id")
        out(f"[cip] returns whose customer tenant != product tenant: {cur.fetchone()[0]}")
        cur.execute(
            "select count(*) filter (where s.resolved_customer_id is not null and cu.id is null) "
            "from fact_inbound_shipment s left join dim_customer cu on cu.id=s.resolved_customer_id and cu.tenant_id=s.tenant_id")
        out(f"[cip] shipments resolved_customer not in same-tenant dim_customer: {cur.fetchone()[0]}")


if __name__ == "__main__":
    for db in ("cip_test", "cip"):
        rls(db)
    cip_shapes()
    OUT.write_text("\n".join(LINES) + "\n", encoding="utf-8")
