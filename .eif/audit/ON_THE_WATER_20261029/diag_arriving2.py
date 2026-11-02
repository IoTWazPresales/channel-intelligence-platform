"""READ-ONLY on cip: the 'Arriving this week' tile (estimated delivery date, 2-8 Nov) against vessels due this week by ETA at port."""
from collections import defaultdict

from sqlalchemy import create_engine, text

eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
W0, W1 = "2026-11-02", "2026-11-08"
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    print(con.execute(text("select current_database(), current_setting('transaction_read_only')")).one())
    rows = con.execute(text("""
        select f.id, f.quantity, f.line_state, f.ship_way, f.port_eta_date, f.port_ata_date, f.eta_date, f.on_board_date,
               (f.status = 'scheduled' and f.pod_date is null and f.eta_date between :a and :b) as in_tile,
               (f.line_state = 'shipped' and f.on_board_date <= current_date and f.port_ata_date is null and f.pod_date is null
                and upper(coalesce(f.ship_way,'')) like '%SEA%' and f.port_eta_date between :a and :b) as on_vessel_due
        from fact_inbound_shipment f where f.tenant_id='default' and f.line_state in ('shipped','open_order')
          and ((f.status='scheduled' and f.pod_date is null and f.eta_date between :a and :b)
               or (f.line_state='shipped' and f.on_board_date <= current_date and f.port_ata_date is null and f.pod_date is null
                   and upper(coalesce(f.ship_way,'')) like '%SEA%' and f.port_eta_date between :a and :b))"""), {"a": W0, "b": W1}).all()
    g = defaultdict(lambda: [0, 0.0])
    for r in rows:
        k = ("in the tile" if r[8] else "not in the tile") + " / " + ("on a vessel due this week" if r[9] else "not on one")
        if r[8] and not r[9]:
            k += " | " + (f"state {r[2]}, " + ("sea" if "SEA" in (r[3] or "").upper() else (r[3] or "no ship way")) + (", port ETA outside the week" if r[4] else ", no port ETA"))
        g[k][0] += 1
        g[k][1] += float(r[1] or 0)
    for k, v in sorted(g.items()):
        print(f"  {k:<100} {v[0]:>4} lines {v[1]:>8,.0f} units")
    tile = [r for r in rows if r[8]]
    vessel = [r for r in rows if r[9]]
    print("tile total:", len(tile), round(sum(float(r[1] or 0) for r in tile)), "| vessels due this week:", len(vessel), round(sum(float(r[1] or 0) for r in vessel)))
    con.rollback()
