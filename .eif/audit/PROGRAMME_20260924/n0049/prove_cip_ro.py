"""N-0049 proof: customer SOH check before (fact_inventory_customer) vs after (CST), read-only on cip."""
import os
import sys
from datetime import date

API = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "apps", "api"))
sys.path.insert(0, API)
os.chdir(API)
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.services.cpor.customer_soh_check import customer_soh_check  # noqa: E402

from app.db.session_sync import sync_engine as eng  # noqa: E402
AS_OF = date(2026, 9, 24)
with Session(eng) as s:
    s.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database() =", s.execute(text("select current_database()")).scalar())
    print("fact_inventory_customer rows:", s.execute(text("select count(*) from fact_inventory_customer")).scalar())
    print("fact_customer_sellthrough rows:", s.execute(text("select count(*) from fact_customer_sellthrough")).scalar())
    # One pair per customer (most recent SOH row), plus CPOR case lines with a stored cost_basis.
    pairs = s.execute(text("""
        select distinct on (f.customer_id) f.customer_id, f.product_id, c.name, null::numeric as cost_basis, null::int as line_id
        from fact_customer_sellthrough f join dim_customer c on c.id = f.customer_id
        order by f.customer_id, (f.reported_soh is not null) desc, (coalesce(f.unit_mac, f.unit_cost) is not null) desc, f.period_start_date desc
    """)).all()
    lines = s.execute(text("""
        select k.customer_id, l.product_id, c.name, l.cost_basis, l.id
        from cpor_case_line l join cpor_case k on k.id = l.case_id join dim_customer c on c.id = k.customer_id
        where l.cost_basis is not null and exists (
          select 1 from fact_customer_sellthrough f where f.customer_id = k.customer_id and f.product_id = l.product_id and f.reported_soh is not null)
        order by l.id desc limit 4
    """)).all()
    for cid, pid, name, cost_basis, line_id in list(pairs) + list(lines):
        before = s.execute(
            text("select count(*), coalesce(sum(on_hand_units),0) from fact_inventory_customer where customer_id=:c and product_id=:p"),
            {"c": cid, "p": pid},
        ).first()
        after = customer_soh_check(s, customer_id=cid, product_id=pid, as_of=AS_OF, derived_mac=cost_basis)
        tag = f"line {line_id}" if line_id else "pair"
        print(f"\n[{tag}] {name} cust={cid} prod={pid} as_of={AS_OF}")
        print(f"  BEFORE fact_inventory_customer: rows={before[0]} on_hand={before[1]} -> no customer SOH")
        print("  AFTER  " + ", ".join(f"{k}={after.get(k)}" for k in (
            "status", "period_start_date", "row_count", "soh_units", "soh_unit_cost", "cost_field", "vat_basis",
            "derived_mac", "delta", "flags", "reason") if k in after))
    s.rollback()
