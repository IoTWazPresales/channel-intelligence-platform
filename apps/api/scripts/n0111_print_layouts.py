"""N-0111: print the saved sell-through layouts and how the identifier slots treat each (read only).

usage (API venv python, from apps/api): python scripts/n0111_print_layouts.py
Prints current_database() first. Writes nothing.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.imports.cst_layouts import uses_legacy_product_slot  # noqa: E402

NEW_SLOTS = {"raw_part_number_token", "raw_barcode_token", "raw_sales_model_token"}

with SessionLocal() as s:
    print("current_database() =", s.execute(text("select current_database()")).scalar())
    rows = s.execute(
        text(
            "select l.id, l.customer_id, c.name, l.name, l.is_hidden, l.field_mapping "
            "from customer_sellthrough_layout l left join dim_customer c on c.id = l.customer_id order by l.id"
        )
    ).all()
    print(f"{len(rows)} saved layout(s)\n")
    for lid, cid, cname, lname, hidden, fm in rows:
        fm = fm or {}
        targets = set(fm.values())
        if targets & NEW_SLOTS:
            treat = "maps the new identifier slots: resolved Part number -> Barcode -> Sales model"
        elif uses_legacy_product_slot(fm):
            treat = "old single product column: still resolves as before ('any identifier'); mapping step offers Re-map"
        else:
            treat = "no product column mapped (unusual)"
        print(f"#{lid} customer {cid} {cname!r} layout {lname!r}{' [hidden]' if hidden else ''}\n    {treat}")
        print("    mapping:", {k: v for k, v in fm.items() if "product" in v or v in NEW_SLOTS or v == "raw_article_token"})
