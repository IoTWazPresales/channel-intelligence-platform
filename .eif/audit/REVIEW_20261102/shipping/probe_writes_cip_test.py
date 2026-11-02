"""GOV-008 adversarial probes on cip_test. ONE transaction, ROLLED BACK at the end (nothing committed).

Scenarios (see probe_writes_cip_test.out.txt):
  P1 partial shipment: open 100, report now shows shipped 60 and no open line
  P2 an old partial shipment of the same order+item labels a vanished remainder closed_shipped
  P3 older-report guard is OU-blind (a lagging OU's file writes nothing)
  P4 undated report re-opens a closed fact through the upsert
  P5 undated report + source-key change -> two open facts for one line (orphan rule only covers the same job)
  P6 orphan retire edge cases (other sheet, shipped replacement, NULL order_line multi-candidate, other job untouched)
  P7 chunking: one fact key with more lines than the chunk size
  P8 fact_upsert_key is global: tenant B's shipped load deletes tenant A's fact
  P9 PO-less twin: two POs on one delivery+item; OU scope; tenant scope
  P10 0050 downgrade statement applied to an orphan-retired open row

Run from apps/api with DATABASE_URL / DATABASE_URL_SYNC pointing at cip_test.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, datetime, timezone

sys.path.insert(0, os.getcwd())

assert "cip_test" in os.environ.get("DATABASE_URL_SYNC", ""), "refusing: DATABASE_URL_SYNC must point at cip_test"

from sqlalchemy import func, select, text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.facts import FactInboundShipment  # noqa: E402
from app.models.iam import Tenant  # noqa: E402
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition  # noqa: E402
from app.models.purchase_order import PurchaseOrder  # noqa: E402
from app.models.shipment_evidence import ShipmentEvidenceLine  # noqa: E402
from app.services.imports import shipment_inbound_facts as facts_mod  # noqa: E402
from app.services.imports.shipment_open_book import (  # noqa: E402
    close_open_book_for_job,
    job_is_older_than_applied_book,
    write_shipment_facts_and_close_book,
)
from app.services.imports.shipment_evidence_line_identity import fact_upsert_key_for_evidence_values  # noqa: E402
from app.services.imports.shipment_evidence_source_keys import stable_source_key_for_row  # noqa: E402
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (  # noqa: E402
    plan_orphaned_open_rows,
    plan_po_less_shipped_twins,
    retire_orphaned_open_rows,
)

UNSHIP, SHIPPED = "acza_workbook_unship", "acza_workbook_shipped"


def out(*a):
    print(*a, flush=True)


db = SessionLocal()
assert db.scalar(text("select current_database()")) == "cip_test"
out("database:", db.scalar(text("select current_database()")))


def tenant(label):
    t = f"gov8-{label}-{uuid.uuid4().hex[:8]}"
    db.add(Tenant(id=t, name="GOV-008 probe"))
    db.flush()
    return t


def job(t, file_name, status="completed"):
    tok = uuid.uuid4().hex[:10]
    tpl = ImportTemplate(slug=f"g8-{tok}", display_name="g8", pipeline_handler="inbound_shipments")
    db.add(tpl)
    db.flush()
    src = SourceDefinition(import_template_id=int(tpl.id), code=f"g8-{tok}", name="g8", source_kind="file")
    db.add(src)
    db.flush()
    j = ImportJob(tenant_id=t, source_id=int(src.id), template_slug="inbound_shipments", status=status, stage="loaded",
                  file_name=file_name, completed_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    db.add(j)
    db.flush()
    return j


_n = 0


def line(j, *, rt, state, key, order="SO", oline="1", item="IT", qty=1, sheet="Unship", ou=None, delivery=None,
         invoice=None, confirm=None, po=None):
    global _n
    _n += 1
    r = ShipmentEvidenceLine(import_job_id=int(j.id), source_sheet=sheet, source_row_number=_n, report_type=rt, line_state=state,
                             source_key=key, raw_source_row={}, order_no=order, order_line=oline, item_code=item, quantity=qty,
                             operating_unit=ou, delivery_no=delivery, invoice_line=invoice, ship_confirm_date=confirm,
                             purchase_order_id=po, product_resolution_status="unresolved", distributor_resolution_status="unresolved")
    db.add(r)
    db.flush()
    return r


def fact(t, j, *, rt, state, key, upsert_key=None, order="SO", oline="1", item="IT", qty=1, ou=None, ev=None, delivery=None,
         confirm=None, po=None):
    global _n
    _n += 1
    f = FactInboundShipment(tenant_id=t, import_job_id=int(j.id), source_key=key, fact_upsert_key=upsert_key or key,
                            shipment_evidence_line_id=int(ev.id) if ev is not None else None, source_row_number=_n,
                            report_type=rt, line_state=state, raw_source_row={}, order_no=order, order_line=oline, item_code=item,
                            quantity=qty, operating_unit=ou, delivery_no=delivery, ship_confirm_date=confirm, purchase_order_id=po,
                            product_resolution_status="unresolved", distributor_resolution_status="unresolved", status="scheduled")
    db.add(f)
    db.flush()
    return f


def state_of(f):
    db.expire(f)
    return db.scalar(select(FactInboundShipment.line_state).where(FactInboundShipment.id == f.id))


def open_rows(t, order):
    return db.execute(select(FactInboundShipment.id, FactInboundShipment.line_state, FactInboundShipment.quantity,
                             FactInboundShipment.source_key)
                      .where(FactInboundShipment.tenant_id == t, FactInboundShipment.order_no == order)
                      .order_by(FactInboundShipment.id)).all()


try:
    # ---------------------------------------------------------------- P1 partial shipment
    out("\n== P1 partial shipment: open 100 on the 0901 book; 0911 book shows Shipped 60 confirmed, no open line")
    t = tenant("p1")
    e = job(t, "ACZA Shipped Unshipped 20260901.xlsx")
    k = f"u-{uuid.uuid4().hex}"
    open100 = fact(t, e, rt=UNSHIP, state="open_order", key=k, order="SO-P", item="IT-P", qty=100, ev=line(e, rt=UNSHIP, state="open_order", key=k, order="SO-P", item="IT-P", qty=100))
    n = job(t, "ACZA Shipped Unshipped 20260911.xlsx")
    ks = f"s-{uuid.uuid4().hex}"
    sl = line(n, rt=SHIPPED, state="shipped", key=ks, order="SO-P", item="IT-P", qty=60, sheet="Shipped", delivery="D-P", invoice="1", confirm=date(2026, 9, 5))
    fact(t, n, rt=SHIPPED, state="shipped", key=ks, order="SO-P", item="IT-P", qty=60, ev=sl, delivery="D-P", confirm=date(2026, 9, 5))
    closed = close_open_book_for_job(db, n)
    out("P1a (0911 book has no Unship line at all) closed rows:", closed, "| SO-P:", open_rows(t, "SO-P"))
    out("=> a newer book whose Unship sheet is empty closes no Unship fact: the scope is the report types the job carries")
    line(n, rt=UNSHIP, state="open_order", key=f"x-{uuid.uuid4().hex}", order="SO-OTHER", item="IT-O", qty=1)
    closed = close_open_book_for_job(db, n)
    out("P1b (0911 book carries one unrelated Unship line) closed rows:", [(r["id"] == open100.id, r["line_state"], r["quantity"]) for r in closed])
    out("rows for SO-P now:", open_rows(t, "SO-P"))
    out("=> 100 open closed as closed_shipped although only 60 shipped; the 40 remainder leaves the book with no flag")

    # ---------------------------------------------------------------- P2 stale shipped twin labels a cancellation
    out("\n== P2 an old partial shipment of the same order+item; the open remainder then vanishes (cancelled)")
    t = tenant("p2")
    old = job(t, "ACZA Shipped Unshipped 20260801.xlsx")
    ks = f"s-{uuid.uuid4().hex}"
    fact(t, old, rt=SHIPPED, state="shipped", key=ks, order="SO-Q", item="IT-Q", qty=10, delivery="D-Q", confirm=date(2026, 8, 1),
         ev=line(old, rt=SHIPPED, state="shipped", key=ks, order="SO-Q", item="IT-Q", qty=10, sheet="Shipped", delivery="D-Q", invoice="1", confirm=date(2026, 8, 1)))
    e = job(t, "ACZA Shipped Unshipped 20260901.xlsx")
    k = f"u-{uuid.uuid4().hex}"
    rem = fact(t, e, rt=UNSHIP, state="open_order", key=k, order="SO-Q", item="IT-Q", qty=30, ev=line(e, rt=UNSHIP, state="open_order", key=k, order="SO-Q", item="IT-Q", qty=30))
    n = job(t, "ACZA Shipped Unshipped 20260911.xlsx")
    line(n, rt=UNSHIP, state="open_order", key=f"x-{uuid.uuid4().hex}", order="SO-OTHER", item="IT-O", qty=1)
    close_open_book_for_job(db, n)
    out("remainder 30 state:", state_of(rem), "(the only shipment of SO-Q/IT-Q was 10 units on 1 Aug)")

    # ---------------------------------------------------------------- P3 OU-blind older guard
    out("\n== P3 OU A's book dated 0911 is applied; OU B's book dated 0905 arrives later")
    t = tenant("p3")
    a = job(t, "ACZA Shipped Unshipped 20260911.xlsx")
    line(a, rt=UNSHIP, state="open_order", key=f"a-{uuid.uuid4().hex}", order="SO-A", ou="OU-A")
    b = job(t, "ACZA Shipped Unshipped 20260905.xlsx", status="validated")
    line(b, rt=UNSHIP, state="open_order", key=f"b-{uuid.uuid4().hex}", order="SO-B", ou="OU-B", qty=7)
    out("job_is_older_than_applied_book(B):", job_is_older_than_applied_book(db, b))
    res = write_shipment_facts_and_close_book(db, b)
    out("write_shipment_facts_and_close_book(B):", res, "| SO-B facts:", open_rows(t, "SO-B"))
    out("=> the guard compares report dates per tenant+report_type, not per OU; OU B's lines are not written at all")

    # ---------------------------------------------------------------- P4 undated report re-opens a closed fact
    out("\n== P4 a closed fact; then an undated file that still carries its key is applied")
    t = tenant("p4")
    e = job(t, "ACZA Shipped Unshipped 20260901.xlsx")
    k = f"u-{uuid.uuid4().hex}"
    gone = fact(t, e, rt=UNSHIP, state="open_order", key=k, order="SO-R", item="IT-R", qty=5, ev=line(e, rt=UNSHIP, state="open_order", key=k, order="SO-R", item="IT-R", qty=5))
    n = job(t, "ACZA Shipped Unshipped 20260911.xlsx")
    line(n, rt=UNSHIP, state="open_order", key=f"x-{uuid.uuid4().hex}", order="SO-X")
    close_open_book_for_job(db, n)
    out("after 0911 close:", state_of(gone))
    u = job(t, "ACZA Shipped Unshipped (copy).xlsx", status="validated")
    line(u, rt=UNSHIP, state="open_order", key=k, order="SO-R", item="IT-R", qty=5)
    res = write_shipment_facts_and_close_book(db, u)
    out("undated apply:", res, "| fact state now:", state_of(gone))

    # ---------------------------------------------------------------- P5 undated + key change double count
    out("\n== P5 old-shape key (blank invoice) open from 0901; an undated re-export carries the same line under the new ord: key")
    t = tenant("p5")
    ex = {"operating_unit": "OU1", "delivery_no": "D-K", "invoice_line": None, "item_code": "IT-K", "order_no": "SO-K", "order_line": "3"}
    new_key = stable_source_key_for_row(report_type=SHIPPED, sheet_name="Shipped", ex=ex)
    old_key = f"{SHIPPED}:shipped|OU1|D-K|IT-K"  # the pre-aa83b93c shape for a blank invoice line
    out("old key:", old_key, "| new key:", new_key)
    e = job(t, "ACZA Shipped Unshipped 20260901.xlsx")
    fact(t, e, rt=SHIPPED, state="open_order", key=old_key, order="SO-K", oline="3", item="IT-K", qty=12, ou="OU1", delivery="D-K",
         ev=line(e, rt=SHIPPED, state="open_order", key=old_key, order="SO-K", oline="3", item="IT-K", qty=12, sheet="Shipped", ou="OU1", delivery="D-K"))
    u = job(t, "ACZA Shipped Unshipped.xlsx", status="validated")
    line(u, rt=SHIPPED, state="open_order", key=new_key, order="SO-K", oline="3", item="IT-K", qty=12, sheet="Shipped", ou="OU1", delivery="D-K")
    out("undated apply:", write_shipment_facts_and_close_book(db, u))
    out("SO-K rows:", open_rows(t, "SO-K"))
    n = job(t, "ACZA Shipped Unshipped 20260915.xlsx", status="validated")
    line(n, rt=SHIPPED, state="open_order", key=new_key, order="SO-K", oline="3", item="IT-K", qty=12, sheet="Shipped", ou="OU1", delivery="D-K")
    out("control, dated 0915 apply:", write_shipment_facts_and_close_book(db, n), "| SO-K rows:", open_rows(t, "SO-K"))

    # ---------------------------------------------------------------- P6 orphan retire edge cases
    out("\n== P6 orphan retire (same job re-read)")
    t = tenant("p6")
    j = job(t, "ACZA Shipped Unshipped 20261027.xlsx")
    other = job(t, "ACZA Shipped Unshipped 20261020.xlsx")
    # a) Unship-sheet fact whose evidence line went (e.g. re-validate with the Unship sheet not selected)
    a_ = fact(t, j, rt=UNSHIP, state="open_order", key=f"a-{uuid.uuid4().hex}", order="SO-6A", qty=8)
    # b) orphan Unship fact; the job now carries the same order line on the Shipped sheet (open)
    b_ = fact(t, j, rt=UNSHIP, state="open_order", key=f"b-{uuid.uuid4().hex}", order="SO-6B", qty=9)
    kb = f"bn-{uuid.uuid4().hex}"
    b_new = fact(t, j, rt=SHIPPED, state="open_order", key=kb, order="SO-6B", qty=9, ev=line(j, rt=SHIPPED, state="open_order", key=kb, order="SO-6B", qty=9, sheet="Shipped"))
    # c) orphan Shipped open fact; the line is now shipped in the same job
    c_ = fact(t, j, rt=SHIPPED, state="open_order", key=f"c-{uuid.uuid4().hex}", order="SO-6C", qty=10)
    kc = f"cn-{uuid.uuid4().hex}"
    fact(t, j, rt=SHIPPED, state="shipped", key=kc, order="SO-6C", qty=10, ev=line(j, rt=SHIPPED, state="shipped", key=kc, order="SO-6C", qty=10, sheet="Shipped"))
    # d) NULL order_line: two orphans (qty 5 and 50) and two carried lines (qty 5 and 50) of one order+item
    d1 = fact(t, j, rt=SHIPPED, state="open_order", key=f"d1-{uuid.uuid4().hex}", order="SO-6D", oline=None, qty=50)
    d2 = fact(t, j, rt=SHIPPED, state="open_order", key=f"d2-{uuid.uuid4().hex}", order="SO-6D", oline=None, qty=5)
    kd1, kd2 = f"dn1-{uuid.uuid4().hex}", f"dn2-{uuid.uuid4().hex}"
    dn1 = fact(t, j, rt=SHIPPED, state="open_order", key=kd1, order="SO-6D", oline=None, qty=5, ev=line(j, rt=SHIPPED, state="open_order", key=kd1, order="SO-6D", oline=None, qty=5, sheet="Shipped"))
    dn2 = fact(t, j, rt=SHIPPED, state="open_order", key=kd2, order="SO-6D", oline=None, qty=50, ev=line(j, rt=SHIPPED, state="open_order", key=kd2, order="SO-6D", oline=None, qty=50, sheet="Shipped"))
    # e) another job's fact with no evidence line, same order line as a carried line of j
    e_ = fact(t, other, rt=SHIPPED, state="open_order", key=f"e-{uuid.uuid4().hex}", order="SO-6B", qty=9)
    plan = plan_orphaned_open_rows(db, int(j.id))
    out("plan:", [(r["id"], r["order_no"], float(r["quantity"]), r["replaced_by"]) for r in plan])
    out("retire:", retire_orphaned_open_rows(db, int(j.id), plan))
    for label, f in (("a unship, sheet dropped", a_), ("b moved to Shipped sheet", b_), ("c now shipped", c_), ("d1 qty50", d1), ("d2 qty5", d2), ("e other job", e_)):
        db.expire(f)
        row = db.execute(select(FactInboundShipment.line_state, FactInboundShipment.superseded_by_fact_id).where(FactInboundShipment.id == f.id)).one()
        out(f"  {label}: {row.line_state} -> superseded_by {row.superseded_by_fact_id}")
    out("  d carried ids: qty5 =", dn1.id, " qty50 =", dn2.id, "| b_new =", b_new.id)

    # ---------------------------------------------------------------- P7 chunking
    out("\n== P7 one shipped fact key with 5 invoice lines, chunk_size=3, plus 4 single-line keys")
    t = tenant("p7")
    j = job(t, "ACZA Shipped Unshipped 20261027.xlsx")
    po = PurchaseOrder(po_number_raw=f"G8PO{uuid.uuid4().hex[:6]}", po_number_norm=f"G8PO{uuid.uuid4().hex[:6]}")
    db.add(po)
    db.flush()
    dl = f"D7-{uuid.uuid4().hex[:6]}"
    line(j, rt=SHIPPED, state="shipped", key=f"s1-{uuid.uuid4().hex}", order="SO-7Z", item="IT-7Z", qty=1, sheet="Shipped", delivery=f"{dl}-z", invoice="1", po=int(po.id), confirm=date(2026, 10, 1))
    for i in range(5):
        line(j, rt=SHIPPED, state="shipped", key=f"s-{i}-{uuid.uuid4().hex}", order="SO-7", item="IT-7", qty=10 + i, sheet="Shipped", delivery=dl, invoice=str(i + 1), po=int(po.id), confirm=date(2026, 10, 1))
        if i == 1:
            line(j, rt=SHIPPED, state="shipped", key=f"s2-{uuid.uuid4().hex}", order="SO-7Y", item="IT-7Y", qty=2, sheet="Shipped", delivery=f"{dl}-y", invoice="1", po=int(po.id), confirm=date(2026, 10, 1))
    n_written = facts_mod.upsert_inbound_shipment_facts_for_job(db, int(j.id), chunk_size=3)
    qty = db.scalar(select(func.sum(FactInboundShipment.quantity)).where(FactInboundShipment.tenant_id == t, FactInboundShipment.delivery_no == dl))
    cnt = db.scalar(select(func.count()).where(FactInboundShipment.tenant_id == t, FactInboundShipment.delivery_no == dl))
    out("lines written:", n_written, "| facts for the 5-line key:", cnt, "qty:", float(qty), "(expected 1 fact, 60)")

    # ---------------------------------------------------------------- P8 global fact_upsert_key across tenants
    out("\n== P8 tenant A and tenant B load the same OU/delivery/item/PO shipped line")
    ta, tb = tenant("p8a"), tenant("p8b")
    ja, jb = job(ta, "ACZA Shipped Unshipped 20261027.xlsx"), job(tb, "ACZA Shipped Unshipped 20261027.xlsx")
    dl8 = f"D8-{uuid.uuid4().hex[:6]}"
    for jj in (ja,):
        line(jj, rt=SHIPPED, state="shipped", key=f"s8-{uuid.uuid4().hex}", order="SO-8", item="IT-8", qty=40, sheet="Shipped", delivery=dl8, invoice="1", po=int(po.id), ou="OU8", confirm=date(2026, 10, 1))
    facts_mod.upsert_inbound_shipment_facts_for_job(db, int(ja.id))
    out("A facts before B:", db.scalar(select(func.count()).where(FactInboundShipment.tenant_id == ta, FactInboundShipment.delivery_no == dl8)))
    line(jb, rt=SHIPPED, state="shipped", key=f"s8b-{uuid.uuid4().hex}", order="SO-8", item="IT-8", qty=3, sheet="Shipped", delivery=dl8, invoice="1", po=int(po.id), ou="OU8", confirm=date(2026, 10, 1))
    try:
        with db.begin_nested():
            facts_mod.upsert_inbound_shipment_facts_for_job(db, int(jb.id))
        out("A facts after B:", db.scalar(select(func.count()).where(FactInboundShipment.tenant_id == ta, FactInboundShipment.delivery_no == dl8)),
            "| B facts:", db.scalar(select(func.count()).where(FactInboundShipment.tenant_id == tb, FactInboundShipment.delivery_no == dl8)))
    except Exception as exc:  # noqa: BLE001
        out("B load raised:", type(exc).__name__, str(exc)[:200])

    # ---------------------------------------------------------------- P9 PO-less twin scope
    out("\n== P9 PO-less twin: two POs on one delivery+item (sum match), other OU, other tenant")
    t9, t9b = tenant("p9"), tenant("p9b")
    o9, n9 = job(t9, "ACZA Shipped Unshipped 20260901.xlsx"), job(t9, "ACZA Shipped Unshipped 20261027.xlsx")
    o9b, n9b = job(t9b, "ACZA Shipped Unshipped 20260901.xlsx"), job(t9b, "ACZA Shipped Unshipped 20261027.xlsx")
    po2 = PurchaseOrder(po_number_raw=f"G8PO2{uuid.uuid4().hex[:6]}", po_number_norm=f"G8PO2{uuid.uuid4().hex[:6]}")
    db.add(po2)
    db.flush()
    d9 = f"D9-{uuid.uuid4().hex[:6]}"
    old9 = fact(t9, o9, rt=SHIPPED, state="shipped", key=f"o9-{uuid.uuid4().hex}", item="IT9", qty=30, delivery=d9, ou="OU9")
    fact(t9, n9, rt=SHIPPED, state="shipped", key=f"n9a-{uuid.uuid4().hex}", item="IT9", qty=10, delivery=d9, ou="OU9", po=int(po.id))
    fact(t9, n9, rt=SHIPPED, state="shipped", key=f"n9b-{uuid.uuid4().hex}", item="IT9", qty=20, delivery=d9, ou="OU9", po=int(po2.id))
    ou_other = fact(t9, o9, rt=SHIPPED, state="shipped", key=f"o9ou-{uuid.uuid4().hex}", item="IT9", qty=30, delivery=d9, ou="OU-OTHER")
    tb_old = fact(t9b, o9b, rt=SHIPPED, state="shipped", key=f"o9t-{uuid.uuid4().hex}", item="IT9", qty=30, delivery=d9, ou="OU9")
    plan = {p.old_id: p for p in plan_po_less_shipped_twins(db) if p.old_id in (old9.id, ou_other.id, tb_old.id)}
    out("planned:", {("same OU+tenant" if k == old9.id else "other OU" if k == ou_other.id else "other tenant"): (v.twins, v.twin_qty, v.qty_match) for k, v in plan.items()})
    out("=> two POs summing to the PO-less quantity are treated as one twin set (retire OK); other OU / tenant are not matched")

    # ---------------------------------------------------------------- P10 0050 downgrade on an orphan-retired open row
    out("\n== P10 0050 downgrade statement on an orphan-retired open row (savepoint, rolled back)")
    with db.begin_nested() as sp:
        before = db.execute(select(FactInboundShipment.line_state).where(FactInboundShipment.id == d1.id)).scalar_one()
        db.execute(text("UPDATE fact_inbound_shipment SET line_state = 'shipped' WHERE line_state = 'closed_superseded' AND id = :i"), {"i": d1.id})
        db.expire_all()
        row = db.execute(select(FactInboundShipment.line_state, FactInboundShipment.ship_confirm_date, FactInboundShipment.report_type).where(FactInboundShipment.id == d1.id)).one()
        out("orphan d1 before:", before, "| after the downgrade statement:", tuple(row), "(it was an open_order line with no confirm date)")
        sp.rollback()
finally:
    db.rollback()
    db.close()
    out("\nrolled back; nothing committed")
