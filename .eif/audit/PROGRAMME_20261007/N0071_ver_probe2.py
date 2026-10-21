"""N-0071 GOV-008 read-only probe 2: shipping overdue KPI (with rule) vs supply overview overdue (no rule)."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import create_engine, func, select, text

from app.core.config import get_settings
from app.models.facts import FactInboundShipment as F
from app.services.shipment_strict_pair import exclude_open_when_shipped_twin
from app.services.shipping_commercial_kpis import predicate_overdue

url = get_settings().database_url_sync
for pre in ("postgresql+psycopg2://", "postgresql://"):
    if url.startswith(pre):
        url = "postgresql+psycopg://" + url[len(pre):]
        break
today = datetime.now(timezone.utc).date()
out: dict = {"today_utc": str(today)}
with create_engine(url).connect() as conn:
    conn.execute(text("SET TRANSACTION READ ONLY"))
    out["current_database"] = conn.execute(text("SELECT current_database()")).scalar()
    out["transaction_read_only"] = conn.execute(text("SHOW transaction_read_only")).scalar()
    base = select(func.count()).select_from(F).where(F.tenant_id == "default", predicate_overdue(today))
    out["overdue_without_rule"] = conn.execute(base).scalar()
    out["overdue_with_rule_shipping_kpi"] = conn.execute(base.where(exclude_open_when_shipped_twin(F))).scalar()
    conn.rollback()
print(json.dumps(out, indent=2))
