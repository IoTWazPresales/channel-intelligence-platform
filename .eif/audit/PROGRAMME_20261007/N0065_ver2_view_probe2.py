"""GOV-008 N-0065 VER2: why does shipment_evidence_current return more rows under a narrow scope? (READ ONLY, cip)

Prints the view definition, the policy columns of its base tables, and, per scope, how many view rows
have a NULL product id and how many of those are superseded-under-'*' rows (an observation that is not
current when every row is visible). Item codes are counted, never printed.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
API = os.path.join(ROOT, "apps", "api")
os.chdir(API)
sys.path.insert(0, API)

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
eng = sa.create_engine(url, poolclass=NullPool, connect_args={
    "options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None})

with eng.connect() as c:
    db = c.execute(sa.text("select current_database()")).scalar_one()
    print("current_database() =", db, "| read_only =", c.execute(sa.text("show transaction_read_only")).scalar_one())
    assert db == "cip"
    print(c.execute(sa.text("select pg_get_viewdef('shipment_evidence_current'::regclass, true)")).scalar())
    for t in ("shipment_evidence_line", "shipment_evidence_observation"):
        pol = c.execute(sa.text("select policyname, cmd, qual from pg_policies where tablename = :t and policyname='cip_pl_select'"),
                        {"t": t}).all()
        for p in pol:
            print(t, p[0], p[1], (p[2] or "")[:160])
    c.rollback()
    # Reference: current ids under '*'
    c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
    star_ids = set(c.execute(sa.text("select id from shipment_evidence_current")).scalars().all())
    c.rollback()
    for scope in ("!", "NB", "AZ"):
        c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": scope})
        rows = c.execute(sa.text("select id, product_id is null, line_identity_key from shipment_evidence_current")).all()
        ids = {r[0] for r in rows}
        extra = ids - star_ids
        nul = sum(1 for r in rows if r[1])
        extra_null = sum(1 for r in rows if r[0] in extra and r[1])
        c.rollback()
        # For the extra rows: what is the product line of the row that is current under '*' for the same identity?
        c.execute(sa.text("select set_config('cip.product_lines', '*', true)"))
        keys = [r[2] for r in rows if r[0] in extra]
        lines = []
        if keys:
            lines = c.execute(sa.text("""
                select coalesce(p.product_line, '(null line)'), count(*) from shipment_evidence_current v
                left join dim_product p on p.id = v.product_id
                where v.line_identity_key = any(:k) group by 1 order by 2 desc"""), {"k": keys}).all()
        c.rollback()
        print(f"scope={scope!r}: view rows={len(rows)} null-product rows={nul} rows not current under '*'={len(extra)} "
              f"(of which null product={extra_null}); line of the '*'-current row for those identities: "
              f"{[(l, int(k)) for l, k in lines]}")
eng.dispose()
