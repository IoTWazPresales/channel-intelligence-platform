"""READ-ONLY: is there a single line (or the booked/other lines) that closes 168 lines / 13,431 units to 169 / 14,278?"""
from datetime import date

from sqlalchemy import create_engine, text

out: list[str] = []


def p(*a):
    s = " ".join(str(x) for x in a)
    out.append(s)
    print(s)


eng = create_engine("postgresql+psycopg://cip:cip@localhost:5432/cip")
with eng.connect() as con:
    con.execute(text("SET TRANSACTION READ ONLY"))
    p("db/user/ro:", tuple(con.execute(text("select current_database(), current_user, current_setting('transaction_read_only')")).one()))
    p("rows with quantity 800-900 in job 1697, no POD:")
    for r in con.execute(text("""select o.id, o.line_state, o.source_sheet, o.ship_confirm_date, o.on_board_date, o.port_eta_date, o.port_ata_date, o.pod_date, o.quantity, o.ship_way, o.order_no
                                 from shipment_evidence_observation o where o.import_job_id=1697 and o.quantity between 800 and 900 and o.pod_date is null order by o.quantity""")).all():
        p("  ", tuple(r))
    p("\nrows by (sheet, line_state, ATA?, POD?, sc?, ob?) with no POD, units:")
    for r in con.execute(text("""select source_sheet, line_state, port_ata_date is not null ata, ship_confirm_date is not null sc, on_board_date is not null ob,
                                        on_board_date > date '2026-10-27' later, count(*), round(sum(quantity))
                                 from shipment_evidence_observation where import_job_id=1697 and pod_date is null group by 1,2,3,4,5,6 order by 8 desc nulls last""")).all():
        p("  ", tuple(r))
    con.rollback()
open(".eif/audit/ON_THE_WATER_20261029/diag_reconcile4.txt", "w", encoding="utf-8").write("\n".join(out) + "\n")
