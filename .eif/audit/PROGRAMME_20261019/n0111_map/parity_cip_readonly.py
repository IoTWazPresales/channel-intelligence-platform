"""N-0111 mapping slots: read-only parity on cip. For staged sell-through lines of older layouts, the new line
resolver (`resolve_line_product`) must return exactly what the former resolver (`resolve_product_id_for_sellthrough`)
returns. Reads only; writes nothing.

usage: python .eif/audit/PROGRAMME_20261014/n0110/dbrun.py cip -- python <this file>
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine as L
from app.services.imports.customer_sell_through import (
    line_uses_identifier_slots,
    resolve_line_product,
    resolve_product_id_for_sellthrough,
)
from app.services.imports.distributor_sales_inventory import _load_product_resolution_index

LIMIT = 30000

with SessionLocal() as s:
    s.execute(text("set transaction read only"))
    print("current_database()=" + s.execute(text("select current_database()")).scalar() + " (read only)")
    total = s.scalar(select(func.count(L.id)))
    print(f"staging lines on cip: {total}; checking the newest {LIMIT}")
    idx = _load_product_resolution_index(s)
    lines = s.scalars(select(L).order_by(L.id.desc()).limit(LIMIT)).all()
    same = diff = slot_path = stored_same = stored_diff = 0
    examples: list[str] = []
    cache: dict = {}
    for ln in lines:
        if line_uses_identifier_slots(ln):
            slot_path += 1
            continue
        old = resolve_product_id_for_sellthrough(
            idx,
            ln.raw_product_token,
            session=s,
            customer_id=ln.resolved_customer_id,
            article_token=ln.raw_article_token,
            raw_row_payload=ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else None,
            as_of=ln.period_start_date,
        )
        new, tier, check = resolve_line_product(idx, ln, session=s, customer_id=ln.resolved_customer_id, alias_cache=cache)
        if old == new and check is None:
            same += 1
        else:
            diff += 1
            if len(examples) < 5:
                examples.append(f"line {ln.id}: old {old} new {new} tier {tier}")
        # How the stored result (which may carry steward/AI decisions) compares with the resolver alone.
        if new is not None and ln.resolved_product_id is not None:
            if new == ln.resolved_product_id:
                stored_same += 1
            else:
                stored_diff += 1
    print(f"older-layout lines checked: {same + diff}; new resolver == former resolver: {same}; different: {diff}")
    print(f"lines on the identifier-slot path (new layouts): {slot_path}")
    print(f"resolved by the resolver and also stored resolved: same product {stored_same}, different {stored_diff}")
    for e in examples:
        print("  DIFF " + e)
    print("PARITY " + ("PASS" if diff == 0 else "FAIL"))
