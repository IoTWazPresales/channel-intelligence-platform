"""Read-only: which customers report sell-through to CIP, and which have registered listings."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "apps" / "api"))

import sqlalchemy as sa

from app.core.config import get_settings

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
engine = sa.create_engine(url)
with engine.connect() as conn:
    conn.execute(sa.text("SET TRANSACTION READ ONLY"))
    print("database:", conn.execute(sa.text("select current_database()")).scalar())
    print("\n-- customers with sell-through rows (rows, first..last period)")
    for r in conn.execute(sa.text(
        """
        select c.name, count(*) as n, min(f.period_start_date)::date, max(f.period_start_date)::date
        from fact_customer_sellthrough f join dim_customer c on c.id = f.customer_id
        group by c.name order by n desc limit 40
        """
    )):
        print(r)
    print("\n-- registered listings by marketplace and customer")
    for r in conn.execute(sa.text(
        """
        select l.marketplace, c.name, count(*)
        from customer_listing l left join dim_customer c on c.id = l.customer_id
        group by 1, 2 order by 1, 3 desc
        """
    )):
        print(r)
    print("\n-- marketplace vocab")
from app.services.listing_capture.marketplace_vocab import LISTING_MARKETPLACES

print(LISTING_MARKETPLACES)
