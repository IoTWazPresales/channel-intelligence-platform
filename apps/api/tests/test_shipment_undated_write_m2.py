"""GOV-008 review 2 Nov, M2: an undated complete-book file must never re-open a closed fact or leave two open facts for one line.

The probes P4 and P5 of the review, as tests. Rule (Warren can overrule): the undated file's fact write leaves closed facts
closed, and writes no second open fact for a line that is already open under another key. The load reports both
("already closed, not re-opened"; "already open under another key, not written twice"). A dated newer file is unchanged:
it closes what it no longer carries and re-opens what it carries again.

cip_test only; every test rolls back.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select, text

from app.db.session_sync import SessionLocal
from app.models.facts import FactInboundShipment
from app.models.iam import Tenant
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.models.shipment_evidence import ShipmentEvidenceLine
from app.services.imports.shipment_evidence_source_keys import stable_source_key_for_row
from tests.shipment_evidence_fixtures import add_evidence_line, row_of
from app.services.imports.shipment_open_book import (
    OPEN_BOOK_NOTICE_HEADLINE,
    UNDATED_WRITE_KEY,
    close_open_book_for_job,
    open_book_close_notice,
    write_shipment_facts_and_close_book,
)

UNSHIP, SHIPPED = "acza_workbook_unship", "acza_workbook_shipped"


@pytest.fixture
def world():
    with SessionLocal() as db:
        if db.scalar(text("select current_database()")) != "cip_test":
            pytest.skip("cip_test only")
        tenant = f"m2-{uuid.uuid4().hex[:10]}"
        db.add(Tenant(id=tenant, name="M2 fixture"))
        db.flush()

        def job(file_name: str, status: str = "completed") -> ImportJob:
            tok = uuid.uuid4().hex[:10]
            tpl = ImportTemplate(slug=f"m2-{tok}", display_name="m2", pipeline_handler="inbound_shipments")
            db.add(tpl)
            db.flush()
            src = SourceDefinition(import_template_id=int(tpl.id), code=f"m2-{tok}", name="m2", source_kind="file")
            db.add(src)
            db.flush()
            j = ImportJob(tenant_id=tenant, source_id=int(src.id), template_slug="inbound_shipments", status=status,
                          stage="loaded" if status == "completed" else "validated", file_name=file_name,
                          completed_at=datetime(2026, 10, 1, tzinfo=timezone.utc) if status == "completed" else None)
            db.add(j)
            db.flush()
            return j

        n = 0

        def line(j, *, rt, state, key, order="SO", oline="1", item="IT", qty=1, sheet="Unship", ou=None, delivery=None,
                 invoice=None, confirm=None) -> ShipmentEvidenceLine:
            nonlocal n
            n += 1
            return add_evidence_line(db, import_job_id=int(j.id), source_sheet=sheet, source_row_number=n, report_type=rt, line_state=state,
                                     source_key=key, raw_source_row={}, order_no=order, order_line=oline, item_code=item, quantity=qty,
                                     operating_unit=ou, delivery_no=delivery, invoice_line=invoice, ship_confirm_date=confirm,
                                     product_resolution_status="unresolved", distributor_resolution_status="unresolved")

        def fact(j, *, rt, state, key, order="SO", oline="1", item="IT", qty=1, ou=None, ev=None, delivery=None, confirm=None) -> FactInboundShipment:
            nonlocal n
            n += 1
            f = FactInboundShipment(tenant_id=tenant, import_job_id=int(j.id), source_key=key, fact_upsert_key=key,
                                    shipment_evidence_line_id=int(ev.id) if ev is not None else None, source_row_number=n,
                                    report_type=rt, line_state=state, raw_source_row={}, order_no=order, order_line=oline,
                                    item_code=item, quantity=qty, operating_unit=ou, delivery_no=delivery, ship_confirm_date=confirm,
                                    product_resolution_status="unresolved", distributor_resolution_status="unresolved", status="scheduled")
            db.add(f)
            db.flush()
            return f

        yield db, tenant, job, line, fact
        db.rollback()


def _state(db, f) -> str:
    db.expire(f)
    return db.scalar(select(FactInboundShipment.line_state).where(FactInboundShipment.id == f.id))


def _rows(db, tenant, order):
    return db.execute(
        select(FactInboundShipment.line_state, FactInboundShipment.quantity, FactInboundShipment.source_key)
        .where(FactInboundShipment.tenant_id == tenant, FactInboundShipment.order_no == order)
        .order_by(FactInboundShipment.id)
    ).all()


def _open(db, tenant, order):
    return [r for r in _rows(db, tenant, order) if r.line_state == "open_order"]


# ------------------------------------------------------------------------------------------------------------- P4


def test_p4_undated_file_does_not_reopen_a_closed_fact(world):
    db, tenant, job, line, fact = world
    e = job("ACZA Shipped Unshipped 20260901.xlsx")
    k = f"u-{uuid.uuid4().hex}"
    gone = fact(e, rt=UNSHIP, state="open_order", key=k, order="SO-R", item="IT-R", qty=5,
                ev=line(e, rt=UNSHIP, state="open_order", key=k, order="SO-R", item="IT-R", qty=5))
    newer = job("ACZA Shipped Unshipped 20260911.xlsx")
    line(newer, rt=UNSHIP, state="open_order", key=f"x-{uuid.uuid4().hex}", order="SO-X")
    assert len(close_open_book_for_job(db, newer)) == 1
    assert _state(db, gone) == "closed_disappeared"

    undated = job("ACZA Shipped Unshipped (copy).xlsx", status="validated")
    line(undated, rt=UNSHIP, state="open_order", key=k, order="SO-R", item="IT-R", qty=5)
    result = write_shipment_facts_and_close_book(db, undated)

    assert _state(db, gone) == "closed_disappeared"  # before the fix: open_order
    assert not _open(db, tenant, "SO-R")
    assert result["fact_rows"] == 0 and result["already_closed_not_reopened"] == 1 and result["already_open_not_duplicated"] == 0
    assert result["closed"] == 0  # an undated file closes nothing either
    # the job keeps the count, and the Import Center notice says it
    assert undated.staged_metadata[UNDATED_WRITE_KEY]["already_closed_not_reopened"] == 1
    assert undated.staged_metadata[UNDATED_WRITE_KEY]["already_closed_not_reopened_units"] == 5.0
    notice = open_book_close_notice(db, undated)
    assert notice["headline"] == OPEN_BOOK_NOTICE_HEADLINE and notice["code"] == "no_report_date"
    assert "1 line(s) already closed, not re-opened" in notice["reason"]
    assert notice["already_closed_not_reopened"] == 1


def test_a_closed_shipped_state_fact_also_stays_closed(world):
    """The shipped writer replaces by key (delete + insert): a closed_superseded PO-less fact must not come back as shipped."""
    from app.services.imports.shipment_inbound_facts import _row_values_from_evidence

    db, tenant, job, line, fact = world
    e = job("ACZA Shipped Unshipped 20260901.xlsx")
    undated = job("ACZA Shipped Unshipped.xlsx", status="validated")
    ev = line(undated, rt=SHIPPED, state="shipped", key=f"s-{uuid.uuid4().hex}", order="SO-S", item="IT-S", qty=9, sheet="Shipped",
              delivery="D-S", invoice="1", confirm=date(2026, 8, 20))
    key = _row_values_from_evidence(row_of(db, ev), tenant_id=tenant)["fact_upsert_key"]  # the key the writer will use for this line
    retired = fact(e, rt=SHIPPED, state="closed_superseded", key=key, order="SO-S", item="IT-S", qty=9, delivery="D-S", confirm=date(2026, 8, 20))
    result = write_shipment_facts_and_close_book(db, undated)
    assert result["fact_rows"] == 0 and result["already_closed_not_reopened"] == 1
    assert _state(db, retired) == "closed_superseded"  # not deleted and re-inserted as shipped
    assert db.scalar(select(func.count()).where(FactInboundShipment.tenant_id == tenant, FactInboundShipment.line_state == "shipped")) == 0


# ------------------------------------------------------------------------------------------------------------- P5


def test_p5_undated_file_does_not_leave_two_open_facts_for_one_line(world):
    db, tenant, job, line, fact = world
    ex = {"operating_unit": "OU1", "delivery_no": "D-K", "invoice_line": None, "item_code": "IT-K", "order_no": "SO-K", "order_line": "3"}
    new_key = stable_source_key_for_row(report_type=SHIPPED, sheet_name="Shipped", ex=ex)
    old_key = f"{SHIPPED}:shipped|OU1|D-K|IT-K"  # the shape written before a blank invoice line kept its order key
    assert new_key != old_key
    e = job("ACZA Shipped Unshipped 20260901.xlsx")
    old = fact(e, rt=SHIPPED, state="open_order", key=old_key, order="SO-K", oline="3", item="IT-K", qty=12, ou="OU1", delivery="D-K",
               ev=line(e, rt=SHIPPED, state="open_order", key=old_key, order="SO-K", oline="3", item="IT-K", qty=12, sheet="Shipped", ou="OU1", delivery="D-K"))

    undated = job("ACZA Shipped Unshipped.xlsx", status="validated")
    line(undated, rt=SHIPPED, state="open_order", key=new_key, order="SO-K", oline="3", item="IT-K", qty=12, sheet="Shipped", ou="OU1", delivery="D-K")
    result = write_shipment_facts_and_close_book(db, undated)

    open_rows = _open(db, tenant, "SO-K")
    assert len(open_rows) == 1 and float(open_rows[0].quantity) == 12.0  # before the fix: two open facts, 12 + 12 units
    assert open_rows[0].source_key == old_key and _state(db, old) == "open_order"
    assert result["fact_rows"] == 0 and result["already_open_not_duplicated"] == 1 and result["already_closed_not_reopened"] == 0
    notice = open_book_close_notice(db, undated)
    assert "1 line(s) already open under another key, not written twice" in notice["reason"]

    # Control (the review's): a DATED newer file does re-key the line: the old fact closes, the new one is the open one.
    dated = job("ACZA Shipped Unshipped 20260915.xlsx", status="validated")
    line(dated, rt=SHIPPED, state="open_order", key=new_key, order="SO-K", oline="3", item="IT-K", qty=12, sheet="Shipped", ou="OU1", delivery="D-K")
    res2 = write_shipment_facts_and_close_book(db, dated)
    assert res2["already_closed_not_reopened"] == 0 and res2["already_open_not_duplicated"] == 0
    assert _state(db, old) == "closed_disappeared"
    now_open = _open(db, tenant, "SO-K")
    assert len(now_open) == 1 and now_open[0].source_key == new_key


# ------------------------------------------------------------------------------------- what the guard must not change


def test_undated_file_still_adds_new_lines_and_updates_open_facts_under_the_same_key(world):
    db, tenant, job, line, fact = world
    e = job("ACZA Shipped Unshipped 20260901.xlsx")
    k = f"u-{uuid.uuid4().hex}"
    same = fact(e, rt=UNSHIP, state="open_order", key=k, order="SO-U1", item="IT-U1", qty=5,
                ev=line(e, rt=UNSHIP, state="open_order", key=k, order="SO-U1", item="IT-U1", qty=5))
    undated = job("ACZA Shipped Unshipped.xlsx", status="validated")
    line(undated, rt=UNSHIP, state="open_order", key=k, order="SO-U1", item="IT-U1", qty=8)  # same key, quantity changed
    line(undated, rt=UNSHIP, state="open_order", key=f"n-{uuid.uuid4().hex}", order="SO-U2", item="IT-U2", qty=3)  # a new line
    result = write_shipment_facts_and_close_book(db, undated)
    assert result["fact_rows"] == 2 and result["already_closed_not_reopened"] == 0 and result["already_open_not_duplicated"] == 0
    db.expire(same)
    assert float(db.scalar(select(FactInboundShipment.quantity).where(FactInboundShipment.id == same.id))) == 8.0
    assert [float(r.quantity) for r in _open(db, tenant, "SO-U2")] == [3.0]


def test_dated_newer_file_may_reopen_a_line_it_carries_again(world):
    """A dated newer book is authoritative: a closed line it carries again is open again. Only an undated file is guarded."""
    db, tenant, job, line, fact = world
    e = job("ACZA Shipped Unshipped 20260901.xlsx")
    k = f"u-{uuid.uuid4().hex}"
    gone = fact(e, rt=UNSHIP, state="closed_disappeared", key=k, order="SO-V", item="IT-V", qty=4,
                ev=line(e, rt=UNSHIP, state="open_order", key=k, order="SO-V", item="IT-V", qty=4))
    newer = job("ACZA Shipped Unshipped 20260920.xlsx", status="validated")
    line(newer, rt=UNSHIP, state="open_order", key=k, order="SO-V", item="IT-V", qty=4)
    result = write_shipment_facts_and_close_book(db, newer)
    assert result["already_closed_not_reopened"] == 0
    assert _state(db, gone) == "open_order"


def test_a_re_read_undated_job_keeps_its_own_old_key_for_the_orphan_retire(world):
    """Facts of the SAME job under an old key are the orphan retire's business, not the guard's: the new key is written."""
    db, tenant, job, line, fact = world
    undated = job("ACZA Shipped Unshipped.xlsx", status="validated")
    old_ev = line(undated, rt=SHIPPED, state="open_order", key="old-k", order="SO-W", oline="2", item="IT-W", qty=6, sheet="Shipped")
    write_shipment_facts_and_close_book(db, undated)
    assert [r.source_key for r in _open(db, tenant, "SO-W")] == ["old-k"]
    db.execute(text("DELETE FROM shipment_evidence_line WHERE id = :i"), {"i": old_ev.id})  # the re-read purges the old line
    line(undated, rt=SHIPPED, state="open_order", key="new-k", order="SO-W", oline="2", item="IT-W", qty=6, sheet="Shipped")
    result = write_shipment_facts_and_close_book(db, undated)
    assert result["already_open_not_duplicated"] == 0
    assert [r.source_key for r in _open(db, tenant, "SO-W")] == ["new-k"]  # one open fact; the old one was retired
    assert sorted(r.line_state for r in _rows(db, tenant, "SO-W")) == ["closed_superseded", "open_order"]
