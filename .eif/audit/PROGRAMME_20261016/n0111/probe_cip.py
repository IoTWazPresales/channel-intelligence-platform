"""N-0111 read-only probe on cip: customers, CST source, products and date ranges for the synthetic proof."""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "PROGRAMME_20261014" / "n0110"))

import psycopg  # noqa: E402

from n0110_numbers import url_for  # noqa: E402

with psycopg.connect(url_for("cip")) as conn:
    conn.autocommit = True

    def q(sql, *a):
        try:
            return conn.execute(sql, a).fetchall()
        except Exception as exc:  # noqa: BLE001
            return f"ERR {exc}"
    print("current_database()", q("select current_database()")[0][0], "read-only probe")
    print("customers", q("select id, code, name from dim_customer where id in (20, 26, 299, 295)"))
    print("cst facts by customer", q(
        "select customer_id, tenant_id, count(*), min(period_start_date), max(period_start_date), sum(units_sold) "
        "from fact_customer_sellthrough where customer_id in (20, 299) group by 1, 2"))
    print("cst sources", q(
        "select s.id, s.name, s.is_active, t.slug from source_definition s join import_template t on t.id = s.import_template_id "
        "where t.slug = 'customer_sell_through' order by s.id"))
    print("cst template expected", q(
        "select left(cast(field_mapping as text), 600), left(cast(expected_columns as text), 900) from import_template where slug = 'customer_sell_through'"))
    print("distributor 29", q("select id, code, name from dim_distributor where id = 29"))
    print("dsi sellout 29", q(
        "select tenant_id, count(*), min(transaction_date), max(transaction_date), sum(units) from fact_sales_sellout where distributor_id = 29 group by 1"))
    print("dsi inventory 29", q(
        "select tenant_id, count(*), min(as_of_date), max(as_of_date) from fact_inventory_distributor where distributor_id = 29 group by 1"))
    print("dsi template", q("select s.id, s.name from source_definition s join import_template t on t.id = s.import_template_id where t.slug = 'distributor_inventory' order by s.id limit 3"))
    print("products", q(
        "select id, sku, name from dim_product where sku is not null "
        "and id not in (select distinct product_id from fact_customer_sellthrough where customer_id in (20, 299)) "
        "and id not in (select distinct product_id from fact_sales_sellout where distributor_id = 29) order by id limit 3"))
    print("open customer for dsi", q("select id, code from dim_customer where code = 'OPEN_CHANNEL'"))
