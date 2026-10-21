"""N-0071 VER2 read-only probe 2: open twins whose key has more than one shipped twin (cip, READ ONLY)."""
import json

from sqlalchemy import create_engine, text

from app.core.config import get_settings

url = get_settings().database_url_sync
for pre in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://"):
    if url.startswith(pre):
        url = "postgresql+psycopg://" + url[len(pre):]
        break
SQL = """
WITH sh AS (
  SELECT tenant_id, lower(btrim(coalesce(operating_unit,''))) ou, lower(btrim(order_no)) o,
         lower(btrim(item_code)) i, coalesce(quantity,0) q
  FROM fact_inbound_shipment
  WHERE lower(line_state)='shipped' AND btrim(coalesce(order_no,''))<>'' AND btrim(coalesce(item_code,''))<>''
), s AS (SELECT tenant_id, ou, o, i, sum(q) tot, max(q) mx, count(*) n FROM sh GROUP BY 1,2,3,4)
SELECT count(*) AS open_lines_multi, sum(n) AS shipped_rows,
       count(*) FILTER (WHERE coalesce(f.quantity,0) <= s.tot) AS covered_by_sum,
       count(*) FILTER (WHERE coalesce(f.quantity,0) > s.mx) AS partial_if_one_twin_only,
       sum(greatest(coalesce(f.quantity,0) - s.mx, 0)) AS units_if_one_twin_only
FROM fact_inbound_shipment f
JOIN s ON s.tenant_id=f.tenant_id AND s.ou=lower(btrim(coalesce(f.operating_unit,'')))
      AND s.o=lower(btrim(f.order_no)) AND s.i=lower(btrim(f.item_code))
WHERE lower(f.line_state)='open_order' AND btrim(coalesce(f.order_no,''))<>'' AND btrim(coalesce(f.item_code,''))<>''
  AND s.n > 1
"""
out = {}
eng = create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})
with eng.connect() as c:
    c.execute(text("SET TRANSACTION READ ONLY"))
    out["current_database"] = c.execute(text("SELECT current_database()")).scalar()
    out["transaction_read_only"] = c.execute(text("SHOW transaction_read_only")).scalar()
    out.update({k: (float(v) if v is not None else None) for k, v in c.execute(text(SQL)).mappings().one().items()})
    c.rollback()
txt = json.dumps(out, indent=2)
with open(__file__.replace(".py", "_out.json"), "w", encoding="utf-8") as fh:
    fh.write(txt)
print(txt)
