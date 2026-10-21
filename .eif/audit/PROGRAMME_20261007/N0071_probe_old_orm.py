"""N-0071 read-only: time the previous (correlated NOT EXISTS) ORM helper on cip. SELECT only."""
from __future__ import annotations

import time

from sqlalchemy import create_engine, exists, func, or_, select, text
from sqlalchemy.orm import aliased

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F


def old_exclude(model):
    """Verbatim logic of the helper before N-0071 (dirty tree, 2026-10-07)."""
    twin = aliased(model)
    pair = [
        twin.tenant_id == model.tenant_id,
        twin.id != model.id,
        func.lower(twin.line_state) == "shipped",
        func.trim(func.coalesce(model.order_no, "")) != "",
        func.trim(func.coalesce(model.item_code, "")) != "",
        func.lower(func.trim(func.coalesce(twin.operating_unit, "")))
        == func.lower(func.trim(func.coalesce(model.operating_unit, ""))),
        func.lower(func.trim(twin.order_no)) == func.lower(func.trim(model.order_no)),
        func.lower(func.trim(twin.item_code)) == func.lower(func.trim(model.item_code)),
    ]
    return or_(func.lower(model.line_state) != "open_order", ~exists(select(twin.id).where(*pair)))


url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
eng = create_engine(url)
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    c.execute(text("SET statement_timeout = '120s'"))
    print("current_database =", c.execute(text("SELECT current_database()")).scalar(), flush=True)
    t = time.time()
    try:
        r = c.execute(select(func.count(), func.coalesce(func.sum(F.quantity), 0)).where(old_exclude(F))).one()
        print("old ORM where-form kept rows, qty =", tuple(str(v) for v in r), "seconds", round(time.time() - t, 2))
    except Exception as exc:
        print("old ORM where-form:", type(exc).__name__, "after seconds", round(time.time() - t, 2))
    c.rollback()
