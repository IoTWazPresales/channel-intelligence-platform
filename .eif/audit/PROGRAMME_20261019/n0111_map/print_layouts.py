"""N-0111 mapping slots: print the saved sell-through layouts (read only) and how each is treated.

usage: python .eif/audit/PROGRAMME_20261014/n0110/dbrun.py <db> -- python <this file>
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())  # dbrun.py runs this with cwd = apps/api

from sqlalchemy import text

from app.db.session_sync import SessionLocal

NEW_IDENTIFIER_TARGETS = {"raw_part_number_token", "raw_barcode_token", "raw_sales_model_token"}

with SessionLocal() as s:
    print("current_database()=" + s.execute(text("select current_database()")).scalar())
    rows = s.execute(
        text(
            """
            select l.id, l.customer_id, c.name as customer_name, l.name as layout_name, l.origin, l.is_hidden, l.field_mapping
            from customer_sellthrough_layout l join dim_customer c on c.id = l.customer_id
            order by l.id
            """
        )
    ).all()
    print(f"layouts: {len(rows)}")
    for r in rows:
        fm = dict(r.field_mapping or {})
        targets = set(fm.values())
        old = [h for h, t in fm.items() if t == "raw_product_token"]
        new_ids = sorted(targets & NEW_IDENTIFIER_TARGETS)
        art = [h for h, t in fm.items() if t == "raw_article_token"]
        if old and not new_ids:
            how = "old single product column -> 'any identifier' (resolves as before); mapping step offers re-map"
        elif new_ids:
            how = "already uses new identifier slots"
        else:
            how = "no product column mapped (unusable until re-mapped)"
        print(
            f"- layout {r.id} | customer {r.customer_id} {r.customer_name} | '{r.layout_name}' | origin {r.origin} | hidden {r.is_hidden}"
            f"\n    mapping: {fm}\n    old product column: {old} | customer code column: {art}\n    treated as: {how}"
        )
