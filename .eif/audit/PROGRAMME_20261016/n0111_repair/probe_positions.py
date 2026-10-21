"""N-0111 repair: READ-ONLY. Stock positions per customer and status after the recompute."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "PROGRAMME_20261014" / "n0110"))
import psycopg  # noqa: E402
from n0110_numbers import url_for  # noqa: E402
with psycopg.connect(url_for(sys.argv[1])) as conn:
    conn.read_only = True
    print("current_database()", conn.execute("select current_database()").fetchone()[0], "(read-only)")
    for r in conn.execute(
        "select c.id, c.name, p.status, count(*), count(distinct p.product_id) from customer_stock_position p "
        "join dim_customer c on c.id = p.customer_id group by 1, 2, 3 order by 1, 3").fetchall():
        print(r)
    for r in conn.execute(
        "select customer_id, period_grain, count(*), count(reported_soh), min(period_start_date), max(period_start_date) "
        "from fact_customer_sellthrough group by 1, 2 order by 1, 2").fetchall():
        print("facts", r)
