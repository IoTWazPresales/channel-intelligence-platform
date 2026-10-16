"""N-0111 (Warren 2026-10-16): a sell-through upload picks a reporting customer; the column layout is the
only per-customer configuration. One rolled-back transaction; cip_test only.

- the picker lists only customers ticked as reporting customers (the list that opens the report slots);
- an unrecognised layout needs the mapping step; once mapped it is saved for the customer;
- a second file with the same headers matches the saved layout by itself and loads the same way;
- uploading the same file again changes nothing;
- another header set is another layout of the same customer; a hidden layout is not matched;
- a hidden source is never offered.
"""

from __future__ import annotations

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

import pytest

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.customer_report_config import CustomerReportConfig
from app.models.customer_sellthrough_layout import CustomerSellthroughLayout
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.imports.cst_d1 import advance_cst_report_slots
from app.services.imports.cst_layouts import (
    ANCHOR_SOURCE_CODE,
    create_customer_upload_jobs,
    find_matching_layout,
    get_or_create_anchor_source,
    inspect_files_for_customer,
    is_reporting_customer,
    list_reporting_customers,
)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(text("select to_regclass('customer_sellthrough_layout')")).scalar():
            pytest.skip("20261016_0043 is not applied")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _customer(db: Session, code: str, *, reporting: bool, key_account: bool = True) -> int:
    cust = DimCustomer(code=code, name=f"{code} name", is_key_account=key_account)
    db.add(cust)
    db.flush()
    db.add(CustomerReportConfig(customer_id=cust.id, reports_expected=reporting, expected_cadence="weekly"))
    db.flush()
    return int(cust.id)


def _products(db: Session) -> list[DimProduct]:
    prods = list(db.scalars(select(DimProduct).order_by(DimProduct.id).limit(2)).all())
    if len(prods) < 2:
        pytest.skip("cip_test needs two products")
    return prods


def _csv(header: list[str], rows: list[list]) -> bytes:
    return ("\n".join(",".join(str(c) for c in r) for r in [header, *rows]) + "\n").encode()


# A header set no alias knows (Afrikaans-style), so the mapping step has to map it.
HEADER = ["Artikel Nr", "Stuks", "Voorraad", "Verkoopdatum"]
MAPPING = {
    "Artikel Nr": "raw_product_token",
    "Stuks": "units_sold",
    "Voorraad": "reported_soh",
    "Verkoopdatum": "raw_period_ref",
}


def _week_file(prods: list[DimProduct], day: str, units: tuple[int, int]) -> bytes:
    return _csv(HEADER, [[prods[0].sku, units[0], 20, day], [prods[1].sku, units[1], 30, day]])


def _facts(db: Session, customer_id: int) -> tuple[int, float, float]:
    row = db.execute(
        select(
            func.count(FactCustomerSellthrough.id),
            func.coalesce(func.sum(FactCustomerSellthrough.units_sold), 0),
            func.coalesce(func.sum(FactCustomerSellthrough.reported_soh), 0),
        ).where(FactCustomerSellthrough.customer_id == customer_id)
    ).one()
    return int(row[0]), float(row[1]), float(row[2])


def test_picker_lists_only_reporting_customers_the_slot_list_is_inside_it(session: Session) -> None:
    yes = _customer(session, "N0111L-YES", reporting=True)
    no = _customer(session, "N0111L-NO", reporting=False)
    non_key = _customer(session, "N0111L-NONKEY", reporting=True, key_account=False)
    merged = _customer(session, "N0111L-MERGED", reporting=True)
    session.get(DimCustomer, merged).merged_into_customer_id = yes
    session.flush()

    ids = {c["id"] for c in list_reporting_customers(session)}
    assert yes in ids and non_key in ids
    assert no not in ids and merged not in ids
    assert is_reporting_customer(session, yes) and not is_reporting_customer(session, no)

    # The customers the late / missing slots are opened for are all in the picker.
    from app.models.customer_cst_report_slot import CustomerCstReportSlot

    before = {int(c) for c in session.scalars(select(CustomerCstReportSlot.customer_id)).all()}
    advance_cst_report_slots(session)
    opened = {int(c) for c in session.scalars(select(CustomerCstReportSlot.customer_id)).all()} - before
    assert yes in opened
    assert no not in opened and non_key not in opened  # the slot job also needs a key account
    # (The slot job also opens one for a merged-away customer that is still ticked; the picker never lists those.)
    assert opened - {merged} <= ids


def test_unknown_layout_is_mapped_saved_matched_next_time_and_a_reupload_changes_nothing(session: Session) -> None:
    prods = _products(session)
    cid = _customer(session, "N0111L-UPLOAD", reporting=True)
    first = _week_file(prods, "2026-03-02", (3, 5))
    second = _week_file(prods, "2026-03-09", (4, 6))

    # 1. Unrecognised headers: no layout, nothing detected, the mapping step is needed.
    info = inspect_files_for_customer(session, cid, [("week 1.csv", first)])[0]
    assert info["readable"] and info["layout"] is None and info["detected_mapping"] == {}
    assert info["columns"] == HEADER
    sig = info["layout_signature"]

    # Without the mapping nothing is created and nothing is saved.
    out = create_customer_upload_jobs(
        session, customer_id=cid, filenames_and_bytes=[("week 1.csv", first)], import_mode="apply"
    )
    assert [o["outcome"] for o in out] == ["error"] and "not mapped yet" in out[0]["error"]
    assert session.scalar(select(func.count(CustomerSellthroughLayout.id)).where(CustomerSellthroughLayout.customer_id == cid)) == 0

    # 2. Mapped once: the layout is saved for the customer and the file loads through the pipeline.
    out = create_customer_upload_jobs(
        session,
        customer_id=cid,
        filenames_and_bytes=[("week 1.csv", first)],
        new_layouts=[{"signature": sig, "name": "Weekly report", "field_mapping": MAPPING}],
        import_mode="apply",
    )
    assert [o["outcome"] for o in out] == ["created"]
    job1 = session.get(ImportJob, out[0]["import_job_id"])
    assert job1.stage == "loaded" and job1.field_mapping == MAPPING
    assert job1.staged_metadata["customer_id"] == cid and job1.source.code == ANCHOR_SOURCE_CODE
    layout = find_matching_layout(session, cid, HEADER)
    assert layout is not None and layout.name == "Weekly report" and layout.field_mapping == MAPPING
    assert layout.origin == "upload" and layout.report_structure_type == "flat"
    after_first = _facts(session, cid)
    assert after_first == (2, 8.0, 50.0)

    # 3. A second file with the same headers matches by itself and loads the same way.
    info2 = inspect_files_for_customer(session, cid, [("week 2.csv", second)])[0]
    assert info2["layout"] == {"id": layout.id, "name": "Weekly report"} and info2["detected_mapping"] == {}
    out = create_customer_upload_jobs(
        session, customer_id=cid, filenames_and_bytes=[("week 2.csv", second)], import_mode="apply"
    )
    assert [o["outcome"] for o in out] == ["created"] and out[0]["layouts"] == [{"id": layout.id, "name": "Weekly report"}]
    job2 = session.get(ImportJob, out[0]["import_job_id"])
    assert job2.stage == "loaded" and job2.field_mapping == job1.field_mapping == MAPPING
    assert job2.source_id == job1.source_id
    assert _facts(session, cid) == (4, 18.0, 100.0)
    assert session.scalar(select(func.count(CustomerSellthroughLayout.id)).where(CustomerSellthroughLayout.customer_id == cid)) == 1

    # 4. Uploading the first file again changes nothing.
    out = create_customer_upload_jobs(
        session, customer_id=cid, filenames_and_bytes=[("week 1 again.csv", first)], import_mode="apply"
    )
    assert [o["outcome"] for o in out] == ["created"]
    assert _facts(session, cid) == (4, 18.0, 100.0)
    assert session.scalar(select(func.count(CustomerSellthroughLayout.id)).where(CustomerSellthroughLayout.customer_id == cid)) == 1


def test_another_header_set_is_another_layout_and_starts_from_the_closest_one(session: Session) -> None:
    prods = _products(session)
    cid = _customer(session, "N0111L-TWO", reporting=True)
    first = _week_file(prods, "2026-03-02", (3, 5))
    sig = inspect_files_for_customer(session, cid, [("a.csv", first)])[0]["layout_signature"]
    create_customer_upload_jobs(
        session,
        customer_id=cid,
        filenames_and_bytes=[("a.csv", first)],
        new_layouts=[{"signature": sig, "name": "Weekly report", "field_mapping": MAPPING}],
        import_mode="apply",
    )
    # History file: the same columns plus one the first did not have.
    header2 = [*HEADER, "Bestel"]
    hist = _csv(header2, [[prods[0].sku, 1, 9, "2026-02-23", 2], [prods[1].sku, 2, 8, "2026-02-23", 3]])
    info = inspect_files_for_customer(session, cid, [("history.csv", hist)])[0]
    assert info["layout"] is None
    assert info["similar_layout"]["name"] == "Weekly report"
    # The mapping step starts from the closest layout: the four known columns arrive mapped.
    assert info["detected_mapping"] == MAPPING

    out = create_customer_upload_jobs(
        session,
        customer_id=cid,
        filenames_and_bytes=[("history.csv", hist)],
        new_layouts=[
            {"signature": info["layout_signature"], "name": "Weekly report", "field_mapping": {**MAPPING, "Bestel": "on_order_units"}}
        ],
        import_mode="apply",
    )
    assert [o["outcome"] for o in out] == ["created"]
    names = sorted(
        session.scalars(select(CustomerSellthroughLayout.name).where(CustomerSellthroughLayout.customer_id == cid)).all()
    )
    assert names == ["Weekly report", "Weekly report (2)"]


def test_a_mapping_without_a_product_column_is_refused_and_saves_nothing(session: Session) -> None:
    prods = _products(session)
    cid = _customer(session, "N0111L-BAD", reporting=True)
    data = _week_file(prods, "2026-03-02", (3, 5))
    sig = inspect_files_for_customer(session, cid, [("a.csv", data)])[0]["layout_signature"]
    out = create_customer_upload_jobs(
        session,
        customer_id=cid,
        filenames_and_bytes=[("a.csv", data)],
        new_layouts=[{"signature": sig, "name": "x", "field_mapping": {"Stuks": "units_sold"}}],
        import_mode="apply",
    )
    assert out[0]["outcome"] == "error" and "product" in out[0]["error"]
    assert session.scalar(select(func.count(CustomerSellthroughLayout.id)).where(CustomerSellthroughLayout.customer_id == cid)) == 0


def test_a_customer_that_is_not_ticked_cannot_be_uploaded_for(session: Session) -> None:
    prods = _products(session)
    cid = _customer(session, "N0111L-NOTICK", reporting=False)
    with pytest.raises(ValueError, match="not ticked as a reporting customer"):
        create_customer_upload_jobs(
            session, customer_id=cid, filenames_and_bytes=[("a.csv", _week_file(prods, "2026-03-02", (1, 1)))]
        )


def test_a_hidden_layout_is_not_matched_and_a_hidden_source_is_not_offered(session: Session) -> None:
    prods = _products(session)
    cid = _customer(session, "N0111L-HIDE", reporting=True)
    data = _week_file(prods, "2026-03-02", (3, 5))
    sig = inspect_files_for_customer(session, cid, [("a.csv", data)])[0]["layout_signature"]
    create_customer_upload_jobs(
        session,
        customer_id=cid,
        filenames_and_bytes=[("a.csv", data)],
        new_layouts=[{"signature": sig, "name": "Weekly report", "field_mapping": MAPPING}],
        import_mode="apply",
    )
    lay = find_matching_layout(session, cid, HEADER)
    lay.is_hidden = True
    session.flush()
    assert find_matching_layout(session, cid, HEADER) is None
    assert inspect_files_for_customer(session, cid, [("a.csv", data)])[0]["layout"] is None

    # The one internal source is hidden, active, and never in the sources the API offers.
    anchor = get_or_create_anchor_source(session)
    assert anchor.is_hidden and anchor.is_active
    offered = session.scalars(
        select(SourceDefinition.code).where(SourceDefinition.is_active.is_(True), SourceDefinition.is_hidden.is_(False))
    ).all()
    assert ANCHOR_SOURCE_CODE not in offered


def _loaded_job(db: Session, source_id: int, customer_id: int, name: str, data: bytes, mapping: dict, structure: str = "flat") -> int:
    import uuid

    from app.models.ingestion import RawFileMetadata
    from app.storage.local import get_storage_backend

    job = ImportJob(
        source_id=source_id,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="loaded",
        file_name=name,
        field_mapping=mapping,
        staged_metadata={"customer_id": customer_id, "report_structure_type": structure},
    )
    db.add(job)
    db.flush()
    key = f"imports/n0111l-test/{uuid.uuid4().hex}/{name}"
    get_storage_backend().save(key, data, "text/csv")
    db.add(RawFileMetadata(job_id=job.id, storage_key=key, byte_size=len(data), checksum=None))
    db.flush()
    return int(job.id)


def _source(db: Session, code: str, customer_id: int | None, structure: str = "flat") -> SourceDefinition:
    from app.models.ingestion import ImportTemplate

    tpl = db.scalar(select(ImportTemplate).where(ImportTemplate.slug == "customer_sell_through"))
    src = SourceDefinition(
        import_template_id=tpl.id,
        code=code,
        name=code,
        source_kind="file",
        expected_template={"customer_id": customer_id, "report_structure_type": structure},
        is_active=True,
    )
    db.add(src)
    db.flush()
    return src


def test_source_migration_keeps_applied_mappings_as_layouts_hides_every_source_and_is_repeatable(session: Session) -> None:
    from app.services.imports.cst_layout_migration import apply_source_migration, plan_source_migration

    prods = _products(session)
    real = _customer(session, "N0111L-MIG", reporting=True)
    not_reporting = _customer(session, "N0111L-MIG-NO", reporting=False)
    data = _week_file(prods, "2026-03-02", (3, 5))
    data2 = _week_file(prods, "2026-03-09", (4, 6))

    used = _source(session, "n0111l_used", real, "pivoted")
    twin = _source(session, "n0111l_twin", real)
    unused = _source(session, "n0111l_unused", real)
    other = _source(session, "n0111l_other_customer", not_reporting)
    job_a = _loaded_job(session, used.id, real, "week 1.csv", data, MAPPING, "pivoted")
    job_b = _loaded_job(session, twin.id, real, "week 2.csv", data2, MAPPING)  # same header set, other source
    _loaded_job(session, other.id, not_reporting, "x.csv", data, MAPPING)
    jobs_before = session.scalar(select(func.count(ImportJob.id)))
    sources_before = session.scalar(select(func.count(SourceDefinition.id)))

    rows, cands = plan_source_migration(session)
    mine = {r.slug: r for r in rows if r.slug.startswith("n0111l_")}
    assert mine["n0111l_used"].applied_jobs == 1 and mine["n0111l_used"].outcome.startswith("layout saved")
    assert mine["n0111l_twin"].outcome.startswith("same header set as layout")
    assert mine["n0111l_unused"].outcome == "hidden (no applied jobs)"
    assert "not ticked as a reporting customer" in mine["n0111l_other_customer"].outcome
    ours = [c for c in cands if c.customer_id == real]
    assert len(ours) == 1 and ours[0].job_id == job_b and set(ours[0].jobs) == {job_a, job_b}  # the last load's mapping

    result = apply_source_migration(session)
    assert result["layouts_created"] >= 1 and result["sources_hidden"] >= 4
    lay = find_matching_layout(session, real, HEADER)
    assert lay is not None and lay.field_mapping == MAPPING  # exactly as the job loaded
    assert lay.origin == "migrated_source" and lay.origin_source_id == used.id
    assert lay.report_structure_type == "flat"  # structure of the job that loaded last
    assert session.scalar(select(func.count(CustomerSellthroughLayout.id)).where(CustomerSellthroughLayout.customer_id == not_reporting)) == 0
    assert all(session.get(SourceDefinition, s.id).is_hidden for s in (used, twin, unused, other))

    # Nothing is deleted, and a second run changes nothing.
    assert session.scalar(select(func.count(ImportJob.id))) == jobs_before
    assert session.scalar(select(func.count(SourceDefinition.id))) == sources_before
    again = apply_source_migration(session)
    assert again["layouts_created"] == 0 and again["sources_hidden"] == 0

    # The migrated layout is what the next upload matches.
    info = inspect_files_for_customer(session, real, [("week 3.csv", _week_file(prods, "2026-03-16", (1, 2)))])[0]
    assert info["layout"] is not None and info["layout"]["name"].startswith("Imported layout")
