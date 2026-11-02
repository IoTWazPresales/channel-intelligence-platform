"""GOV-008 review 2 Nov, batch-2 minors on the open book, the orphan retire, pointers, the sheet memory and the reclassify scope.

cip_test only; every test rolls back (the ``world`` fixture is the one of the M2 tests).
"""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.models.facts import FactInboundShipment
from app.models.platform_audit import PlatformAuditEvent
from app.services.imports.shipment_field_mapping import (
    initial_sheet_selection,
    remember_selected_sheets,
    remembered_seen_sheet_names,
    sheet_changes_since_remembered,
)
from app.services.imports.shipment_open_book import (
    PARTIAL_SHIP_KEY,
    close_open_book_for_job,
    job_is_older_than_applied_book,
    open_book_close_notice,
    preview_unconfirmed_shipped_ids,
    reclassify_unconfirmed_shipped,
    write_shipment_facts_and_close_book,
)
from app.services.imports.shipment_shipped_fact_identity_twin_merge import (
    plan_orphaned_open_rows,
    refresh_superseded_pointers,
    retire_orphaned_open_rows,
)
from tests.test_shipment_undated_write_m2 import SHIPPED, UNSHIP, _open, _state, world  # noqa: F401


def _k() -> str:
    return f"u-{uuid.uuid4().hex}"


# ------------------------------------------------------------------------- older-report guard respects the unit


def test_a_lagging_operating_unit_book_is_not_older_than_another_units_book(world):
    db, tenant, job, line, fact = world
    applied = job("ACZA Shipped Unshipped 20260911.xlsx")
    line(applied, rt=UNSHIP, state="open_order", key=_k(), order="SO-A", ou="OU-A")
    lagging = job("ACZA Shipped Unshipped 20260901.xlsx", status="validated")
    line(lagging, rt=UNSHIP, state="open_order", key=_k(), order="SO-B", ou="OU-B")
    assert job_is_older_than_applied_book(db, lagging) is False  # before: True (the guard compared across units)
    result = write_shipment_facts_and_close_book(db, lagging)
    assert result["skipped_reason"] is None and result["fact_rows"] == 1
    assert len(_open(db, tenant, "SO-B")) == 1


def test_the_same_unit_older_book_is_still_older(world):
    db, tenant, job, line, fact = world
    applied = job("ACZA Shipped Unshipped 20260911.xlsx")
    line(applied, rt=UNSHIP, state="open_order", key=_k(), order="SO-A", ou="OU-A")
    older = job("ACZA Shipped Unshipped 20260901.xlsx", status="validated")
    line(older, rt=UNSHIP, state="open_order", key=_k(), order="SO-A2", ou="OU-A")
    assert job_is_older_than_applied_book(db, older) is True
    result = write_shipment_facts_and_close_book(db, older)
    assert result["skipped_reason"] == "older_report_date" and result["fact_rows"] == 0
    assert not _open(db, tenant, "SO-A2")


def test_a_file_with_one_current_and_one_superseded_unit_writes_only_the_current_unit(world):
    db, tenant, job, line, fact = world
    applied = job("ACZA Shipped Unshipped 20260911.xlsx")
    line(applied, rt=UNSHIP, state="open_order", key=_k(), order="SO-A", ou="OU-A")
    mixed = job("ACZA Shipped Unshipped 20260905.xlsx", status="validated")
    line(mixed, rt=UNSHIP, state="open_order", key=_k(), order="SO-MIX-A", ou="OU-A")  # unit A has a newer book
    line(mixed, rt=UNSHIP, state="open_order", key=_k(), order="SO-MIX-C", ou="OU-C")  # unit C has none
    assert job_is_older_than_applied_book(db, mixed) is False
    result = write_shipment_facts_and_close_book(db, mixed)
    assert result["fact_rows"] == 1
    assert not _open(db, tenant, "SO-MIX-A") and len(_open(db, tenant, "SO-MIX-C")) == 1


# --------------------------------------------------------------------------------------- partial shipment flagged


def _partial_book(world, shipped_qty):
    db, tenant, job, line, fact = world
    e = job("ACZA Shipped Unshipped 20260901.xlsx")
    k = _k()
    open100 = fact(e, rt=UNSHIP, state="open_order", key=k, order="SO-P", item="IT-P", qty=100,
                   ev=line(e, rt=UNSHIP, state="open_order", key=k, order="SO-P", item="IT-P", qty=100))
    n = job("ACZA Shipped Unshipped 20260911.xlsx")
    ks = _k()
    sl = line(n, rt=SHIPPED, state="shipped", key=ks, order="SO-P", item="IT-P", qty=shipped_qty, sheet="Shipped", delivery="D-P",
              invoice="1", confirm=date(2026, 9, 5))
    fact(n, rt=SHIPPED, state="shipped", key=ks, order="SO-P", item="IT-P", qty=shipped_qty, ev=sl, delivery="D-P", confirm=date(2026, 9, 5))
    line(n, rt=UNSHIP, state="open_order", key=_k(), order="SO-OTHER")  # the 0911 book still carries the Unship scope
    return db, n, open100


def test_partial_shipment_flags_the_missing_units_instead_of_closing_silently(world):
    db, n, open100 = _partial_book(world, 60)
    closed = close_open_book_for_job(db, n)
    row = next(r for r in closed if r["id"] == open100.id)
    assert row["line_state"] == "closed_shipped" and row["shipped_quantity"] == 60.0 and row["missing_quantity"] == 40.0
    event = db.scalars(select(PlatformAuditEvent).where(PlatformAuditEvent.action == "open_book_close", PlatformAuditEvent.target_id == str(n.id))).one()
    assert event.detail_json["partial_shipments"] == 1 and event.detail_json["partial_missing_units"] == 40.0
    assert next(f for f in event.detail_json["facts"] if f["fact_id"] == open100.id)["missing_quantity"] == 40.0
    assert n.staged_metadata[PARTIAL_SHIP_KEY]["missing_units"] == 40.0
    notice = open_book_close_notice(db, n)
    assert notice["code"] == "partial_shipment" and "40" in notice["reason"] and notice["lines"] == 1


def test_a_full_shipment_is_not_flagged(world):
    db, n, open100 = _partial_book(world, 100)
    closed = close_open_book_for_job(db, n)
    row = next(r for r in closed if r["id"] == open100.id)
    assert row["line_state"] == "closed_shipped" and row["missing_quantity"] is None
    assert PARTIAL_SHIP_KEY not in (n.staged_metadata or {})
    assert open_book_close_notice(db, n) is None


# ----------------------------------------------------------------------------------------------- orphan retire


@pytest.fixture
def orphans(world):
    db, tenant, job, line, fact = world
    j = job("ACZA Shipped Unshipped 20260901.xlsx")

    def open_fact(order, qty, *, oline="1.1", carried=False):
        key = _k()
        ev = line(j, rt=SHIPPED, state="open_order", key=key, order=order, oline=oline, item="IT-O", qty=qty, sheet="Shipped") if carried else None
        return fact(j, rt=SHIPPED, state="open_order", key=key, order=order, oline=oline, item="IT-O", qty=qty, ev=ev)

    return db, tenant, j, open_fact


def _audit(db, j):
    return db.scalars(select(PlatformAuditEvent).where(
        PlatformAuditEvent.action == "shipped_fact_orphan_open_retire", PlatformAuditEvent.target_id == str(j.id))).all()


def test_orphan_with_another_quantity_on_its_replacement_is_flagged_not_retired(orphans):
    db, tenant, j, open_fact = orphans
    orphan = open_fact("SO-Q", 10)
    open_fact("SO-Q", 7, carried=True)
    plan = [r for r in plan_orphaned_open_rows(db, int(j.id)) if r["id"] == orphan.id]
    assert plan[0]["action"] == "quantity_differs"
    assert retire_orphaned_open_rows(db, int(j.id), plan) == {"superseded": 0, "disappeared": 0}
    assert _state(db, orphan) == "open_order"  # a person decides; it is not hidden
    assert not _audit(db, j)  # a caller that passes its plan writes its own audit event
    retire_orphaned_open_rows(db, int(j.id))  # the load-time call
    event = _audit(db, j)[0]
    assert event.detail_json["flagged_left_open"][0]["reason"] == "quantity_differs"
    assert event.detail_json["flagged_left_open"][0]["fact_id"] == orphan.id


def test_orphan_with_the_same_quantity_is_still_superseded_and_the_load_writes_an_audit_event(orphans):
    db, tenant, j, open_fact = orphans
    orphan = open_fact("SO-S", 10)
    keeper = open_fact("SO-S", 10, carried=True)
    done = retire_orphaned_open_rows(db, int(j.id))
    assert done == {"superseded": 1, "disappeared": 0}
    db.refresh(orphan)
    assert orphan.line_state == "closed_superseded" and orphan.superseded_by_fact_id == keeper.id
    events = _audit(db, j)
    assert len(events) == 1 and events[0].detail_json["trigger"] == "load"
    assert events[0].detail_json["superseded_fact_ids"] == [orphan.id] and events[0].tenant_id == tenant


def test_two_orphans_never_point_at_one_fact(orphans):
    db, tenant, j, open_fact = orphans
    first = open_fact("SO-T", 5, oline=None)
    second = open_fact("SO-T", 5, oline=None)
    keeper = open_fact("SO-T", 5, oline=None, carried=True)
    plan = {r["id"]: r for r in plan_orphaned_open_rows(db, int(j.id)) if r["id"] in (first.id, second.id)}
    assert plan[first.id]["action"] == "supersede" and plan[second.id]["action"] == "ambiguous"
    assert retire_orphaned_open_rows(db, int(j.id)) == {"superseded": 1, "disappeared": 0}
    db.refresh(first)
    db.refresh(second)
    assert first.superseded_by_fact_id == keeper.id and second.line_state == "open_order"
    pointing = db.scalars(select(FactInboundShipment.id).where(FactInboundShipment.superseded_by_fact_id == keeper.id)).all()
    assert pointing == [first.id]


# ------------------------------------------------------------------------------------------ pointer refresh scope


def test_refresh_superseded_pointers_touches_only_the_keepers_the_job_wrote(world):
    db, tenant, job, line, fact = world
    j1, j2 = job("ACZA Shipped Unshipped 20260901.xlsx"), job("ACZA Shipped Unshipped 20260902.xlsx")
    k1, k2 = _k(), _k()
    keeper1 = fact(j1, rt=SHIPPED, state="shipped", key=k1, order="SO-R1", qty=1)
    keeper2 = fact(j2, rt=SHIPPED, state="shipped", key=k2, order="SO-R2", qty=1)
    for order, key in (("SO-R1", k1), ("SO-R2", k2)):
        old = fact(j1, rt=SHIPPED, state="closed_superseded", key=_k(), order=order + "-old", qty=1)
        old.superseded_by_key, old.superseded_by_fact_id = key, 999_999_999  # a pointer that went stale on a reload
    db.flush()
    assert refresh_superseded_pointers(db, written_by_job=int(j1.id)) == 1  # not the whole table
    pointers = {f.superseded_by_key: f.superseded_by_fact_id for f in db.scalars(select(FactInboundShipment).where(
        FactInboundShipment.tenant_id == tenant, FactInboundShipment.line_state == "closed_superseded")).all()}
    assert pointers[k1] == keeper1.id and pointers[k2] == 999_999_999
    assert refresh_superseded_pointers(db) >= 1  # no scope: every pointer is repaired (the scripts)
    db.expire_all()
    assert db.scalar(select(FactInboundShipment.superseded_by_fact_id).where(
        FactInboundShipment.tenant_id == tenant, FactInboundShipment.superseded_by_key == k2)) == keeper2.id


# ------------------------------------------------------------------------------ reclassify is never table-wide


def test_reclassify_unconfirmed_shipped_needs_a_scope_and_touches_only_it(world):
    db, tenant, job, line, fact = world
    j1, j2 = job("ACZA Shipped Unshipped 20260901.xlsx"), job("ACZA Shipped Unshipped 20260902.xlsx")
    mine = fact(j1, rt=SHIPPED, state="shipped", key=_k(), order="SO-RC1", qty=3)
    other = fact(j2, rt=SHIPPED, state="shipped", key=_k(), order="SO-RC2", qty=4)  # a leaked-test-fact stand-in
    with pytest.raises(ValueError):
        reclassify_unconfirmed_shipped(db)
    with pytest.raises(ValueError):
        preview_unconfirmed_shipped_ids(db)
    assert preview_unconfirmed_shipped_ids(db, import_job_id=int(j1.id)) == [mine.id]
    assert reclassify_unconfirmed_shipped(db, import_job_id=int(j1.id)) == [mine.id]
    assert _state(db, mine) == "open_order" and _state(db, other) == "shipped"
    assert reclassify_unconfirmed_shipped(db, loaded_on_or_before=date(2000, 1, 1)) == []  # a date before the load: nothing
    assert other.id in reclassify_unconfirmed_shipped(db, import_job_id=int(j2.id), loaded_on_or_before=date.today())


# ------------------------------------------------------------------------------------- remembered sheets are shown


def _source(selected, seen=None):
    memory = {"selected_sheet_names": selected}
    if seen is not None:
        memory["seen_sheet_names"] = seen
    return SimpleNamespace(column_mapping_memory=memory)


def test_a_new_sheet_is_never_dropped_silently():
    source = _source(["Unship", "Shipped"], seen=["Unship", "Shipped", "Notes"])
    chosen, confirmed, changes = initial_sheet_selection(source, ["Unship", "Shipped", "Notes", "Shipped Q4"], ["Unship", "Shipped"])
    assert chosen == ["Unship", "Shipped"] and confirmed is False  # before: confirmed True, the new sheet silently left out
    assert changes == {"new": ["Shipped Q4"], "missing": []}


def test_a_renamed_sheet_is_one_new_and_one_missing():
    source = _source(["Unship", "Shipped"], seen=["Unship", "Shipped"])
    chosen, confirmed, changes = initial_sheet_selection(source, ["Unship", "Shipped 2026"], ["Unship"])
    assert chosen == ["Unship"] and confirmed is False
    assert changes == {"new": ["Shipped 2026"], "missing": ["Shipped"]}


def test_an_unchanged_workbook_still_skips_the_dialog_and_an_ignored_sheet_is_not_new():
    source = _source(["Unship", "Shipped"], seen=["Unship", "Shipped", "Notes"])
    chosen, confirmed, changes = initial_sheet_selection(source, ["Unship", "Shipped", "Notes"], ["Unship", "Shipped"])
    assert chosen == ["Unship", "Shipped"] and confirmed is True and changes == {"new": [], "missing": []}


def test_memory_from_before_the_seen_list_asks_once():
    source = _source(["Unship", "Shipped"])  # no seen_sheet_names
    chosen, confirmed, changes = initial_sheet_selection(source, ["Unship", "Shipped", "Notes"], ["Unship", "Shipped"])
    assert confirmed is False and changes["new"] == ["Notes"]
    assert sheet_changes_since_remembered(source, ["Unship", "Shipped"])["new"] == []


def test_nothing_remembered_keeps_the_default_choice():
    chosen, confirmed, changes = initial_sheet_selection(SimpleNamespace(column_mapping_memory={}), ["Shipped", "Unship"], ["Shipped", "Unship"])
    assert chosen == ["Shipped", "Unship"] and confirmed is False and changes["new"] == []
    assert initial_sheet_selection(None, ["Only"], ["Only"])[1] is True  # a one-sheet file is confirmed


def test_remember_selected_sheets_stores_every_sheet_that_was_shown():
    src = SimpleNamespace(column_mapping_memory={})
    db = MagicMock()
    db.get = MagicMock(return_value=src)
    remember_selected_sheets(db, source_id=1, sheet_names=["Shipped"], available_sheets=["Shipped", "Notes"])
    assert src.column_mapping_memory["selected_sheet_names"] == ["Shipped"]
    assert remembered_seen_sheet_names(src) == ["Shipped", "Notes"]
