"""Read-only: distinct raw Shipping Method / Ship Way / Deliver Port values on one database, with line counts.

    python -I .eif/audit/ON_THE_WATER_20261029/probe_shipping_method.py <database>
"""
import re
import sys

sys.path.insert(0, "apps/api")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.db.sync_url import sqlalchemy_sync_engine_url  # noqa: E402

db = sys.argv[1]
raw = make_url(get_settings().database_url_sync).set(database=db).render_as_string(hide_password=False)
engine = create_engine(sqlalchemy_sync_engine_url(raw))
DEFAULT = re.compile(r"^(?P<forwarder>[A-Z]+)(?P<hub>[a-z]+)")
with engine.connect() as c:
    c.execute(text("SET default_transaction_read_only = on"))
    for key in ("Shipping Method", "Ship Way", "Deliver Port", "Currency"):
        rows = c.execute(
            text("SELECT raw_source_row ->> :k AS v, count(*) n FROM shipment_evidence_line GROUP BY 1 ORDER BY 2 DESC LIMIT 40"),
            {"k": key},
        ).all()
        print(f"== {key}: {len(rows)} distinct (top 40)")
        for v, n in rows:
            extra = ""
            if key == "Shipping Method" and v:
                m = DEFAULT.match(v.strip())
                extra = f"  -> forwarder={m.group('forwarder')!r} hub={m.group('hub')!r}" if m else "  -> no match"
            print(f"  {n:>7}  {v!r}{extra}")
    c.rollback()
