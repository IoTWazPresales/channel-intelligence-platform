"""N-0071 VER2 read-only probe 3: suggested-PO ``total_shipped_units`` (evidence read model) on cip.

How much of the PO-linked evidence total is open_order, and how much of that is covered by
a strict shipped twin (D-0057/D-0065). SELECT only, READ ONLY. No secret printed.
"""
import json

from sqlalchemy import create_engine, func, select, text

from app.core.config import get_settings
from app.services.imports.shipment_evidence_read import (
    active_evidence_line_predicate,
    apply_active_evidence_filter,
    shipment_evidence_read_model,
)
from app.services.shipment_strict_pair import twin_remainder

url = get_settings().database_url_sync
for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
    if url.startswith(pre):
        url = "postgresql+psycopg://" + url[len(pre):]
        break
EV = shipment_evidence_read_model()
out = {"evidence_model": EV.__tablename__}
eng = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    out["current_database"] = c.execute(text("SELECT current_database()")).scalar()
    out["transaction_read_only"] = c.execute(text("SHOW transaction_read_only")).scalar()
    base = apply_active_evidence_filter(
        select(EV.line_state, func.count(), func.coalesce(func.sum(EV.quantity), 0))
        .where(EV.purchase_order_id.isnot(None), EV.product_id.isnot(None))
        .group_by(EV.line_state),
        model=EV,
    )
    out["po_linked_by_state"] = {str(s): {"rows": int(n), "units": float(q)} for s, n, q in c.execute(base).all()}
    tw = twin_remainder(EV, row_filter=active_evidence_line_predicate)
    counted = apply_active_evidence_filter(
        select(func.count(), func.coalesce(func.sum(EV.quantity), 0), func.coalesce(func.sum(tw.counted_quantity), 0))
        .select_from(EV)
        .outerjoin(tw.subquery, tw.onclause)
        .where(EV.purchase_order_id.isnot(None), EV.product_id.isnot(None), EV.line_state == "open_order", ~tw.kept),
        model=EV,
    )
    n, stored, _cnt = c.execute(counted).one()
    out["po_linked_open_covered_by_twin"] = {"rows": int(n), "units": float(stored)}
    part = apply_active_evidence_filter(
        select(func.count(), func.coalesce(func.sum(EV.quantity), 0), func.coalesce(func.sum(tw.counted_quantity), 0))
        .select_from(EV)
        .outerjoin(tw.subquery, tw.onclause)
        .where(EV.purchase_order_id.isnot(None), EV.product_id.isnot(None), EV.line_state == "open_order", tw.is_partial_twin),
        model=EV,
    )
    n2, stored2, rem2 = c.execute(part).one()
    out["po_linked_open_partial"] = {"rows": int(n2), "stored_units": float(stored2), "remainder": float(rem2)}
    c.rollback()
txt = json.dumps(out, indent=2)
with open(__file__.replace(".py", "_out.json"), "w", encoding="utf-8") as fh:
    fh.write(txt)
print(txt)
