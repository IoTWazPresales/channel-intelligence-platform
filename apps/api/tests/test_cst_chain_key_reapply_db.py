"""N-0118: re-applying a job re-keys rows stored on a chain-level fact while the staged row names a site.

One rolled-back transaction. Writes only to cip_test. Prints current_database() before any write.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import Text, create_engine, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import CustomerLocation, DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.models.import_customer_sellthrough_staging import ImportCustomerSellthroughStagingLine
from app.models.ingestion import ImportJob, SourceDefinition
from app.services.imports.customer_sell_through import customer_sellthrough_source_key
from app.services.imports.customer_sell_through_apply import apply_customer_sellthrough_staging

TENANT = "n0118_chain_rekey"
WEEK = date(1999, 1, 4)
T0 = datetime(2026, 8, 1, tzinfo=timezone.utc)


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        name = conn.execute(text("select current_database()")).scalar()
        print(f"current_database={name}", flush=True)
        if name != "cip_test":
            pytest.skip(f"cip_test only, current_database={name}")
        if not conn.execute(text("select to_regclass('fact_customer_sellthrough_superseded')")).scalar():
            pytest.skip("fact_customer_sellthrough_superseded is not present")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _ids(db: Session) -> tuple[int, int, int, int]:
    source = db.scalar(select(SourceDefinition.id).order_by(SourceDefinition.id).limit(1))
    customer = db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1))
    products = db.scalars(select(DimProduct.id).order_by(DimProduct.id).limit(30)).all()
    if source is None or customer is None or len(products) < 2:
        pytest.skip("cip_test needs a source, a customer and two products")
    free: list[int] = []
    for product in products:
        keys = [
            customer_sellthrough_source_key(
                customer_id=int(customer),
                customer_location_id=None,
                product_id=int(product),
                period_start_date=WEEK,
            ),
            customer_sellthrough_source_key(
                customer_id=int(customer),
                customer_location_id=None,
                product_id=int(product),
                period_start_date=WEEK,
                site_label="S1",
            ),
            customer_sellthrough_source_key(
                customer_id=int(customer),
                customer_location_id=None,
                product_id=int(product),
                period_start_date=WEEK,
                site_label="S2",
            ),
        ]
        taken = db.scalar(
            select(func.count()).select_from(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key.in_(keys))
        )
        if not taken:
            free.append(int(product))
        if len(free) == 2:
            break
    if len(free) < 2:
        pytest.skip("cip_test has no free sell-through keys for the fixture week")
    return int(source), int(customer), free[0], free[1]


def _counts(db: Session) -> tuple[int, int]:
    products = int(db.scalar(select(func.count()).select_from(DimProduct)) or 0)
    locations = int(db.scalar(select(func.count()).select_from(CustomerLocation)) or 0)
    return products, locations


def test_reapply_rekeys_chain_level_facts_and_second_apply_changes_nothing(session: Session) -> None:
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    assert name == "cip_test"

    source, customer, product, other_product = _ids(session)
    masters_before = _counts(session)
    job = ImportJob(
        tenant_id=TENANT,
        source_id=source,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="loaded",
        file_name="store-week.xlsx",
        created_at=T0,
    )
    session.add(job)
    session.flush()

    chain_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
    )
    collapsed = FactCustomerSellthrough(
        source_key=chain_key,
        tenant_id=TENANT,
        customer_id=customer,
        product_id=product,
        period_start_date=WEEK,
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal("3"),
        reported_soh=Decimal("1"),
        site_label="S1",
        import_job_id=job.id,
    )
    other_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=other_product,
        period_start_date=WEEK,
    )
    other = FactCustomerSellthrough(
        source_key=other_key,
        tenant_id=TENANT,
        customer_id=customer,
        product_id=other_product,
        period_start_date=WEEK,
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal("9"),
        reported_soh=Decimal("8"),
        import_job_id=job.id,
    )
    session.add_all([collapsed, other])
    session.flush()

    session.add_all(
        [
            ImportCustomerSellthroughStagingLine(
                import_job_id=job.id,
                source_row_number=1,
                raw_row_payload={"site": "S1", "units": "10", "soh": "4"},
                resolved_customer_id=customer,
                resolved_product_id=product,
                period_start_date=WEEK,
                period_type="weekly",
                period_grain="week",
                units_sold=Decimal("10"),
                reported_soh=Decimal("4"),
                site_label="S1",
                resolution_status="resolved",
                apply_status="applied",
                fact_sellthrough_row_id=collapsed.id,
            ),
            ImportCustomerSellthroughStagingLine(
                import_job_id=job.id,
                source_row_number=2,
                raw_row_payload={"site": "S2", "units": "7", "soh": "2"},
                resolved_customer_id=customer,
                resolved_product_id=product,
                period_start_date=WEEK,
                period_type="weekly",
                period_grain="week",
                units_sold=Decimal("7"),
                reported_soh=Decimal("2"),
                site_label=None,
                raw_location_token="S2",
                resolution_status="resolved",
                apply_status="applied",
                fact_sellthrough_row_id=collapsed.id,
            ),
            ImportCustomerSellthroughStagingLine(
                import_job_id=job.id,
                source_row_number=3,
                raw_row_payload={"units": "9"},
                resolved_customer_id=customer,
                resolved_product_id=other_product,
                period_start_date=WEEK,
                period_type="weekly",
                period_grain="week",
                units_sold=Decimal("9"),
                reported_soh=Decimal("8"),
                resolution_status="resolved",
                apply_status="applied",
                fact_sellthrough_row_id=other.id,
            ),
            ImportCustomerSellthroughStagingLine(
                import_job_id=job.id,
                source_row_number=4,
                raw_row_payload={"site": "S9", "token": "UNMATCHED"},
                raw_product_token="UNMATCHED",
                site_label="S9",
                period_start_date=WEEK,
                units_sold=Decimal("1"),
                resolution_status="product_not_matched",
            ),
        ]
    )
    session.flush()

    first = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert first.errors == []
    # Two site re-keys. The other_product chain row has no site-named row on its fact, so it is
    # not selected again (re-key is decided per fact) and stays exactly as stored.
    assert first.applied == 2
    assert first.skipped_unresolved == 1
    assert first.superseded_rows == 1
    assert first.superseded_units == 3.0

    site_keys = {
        "S1": customer_sellthrough_source_key(
            customer_id=customer,
            customer_location_id=None,
            product_id=product,
            period_start_date=WEEK,
            site_label="S1",
        ),
        "S2": customer_sellthrough_source_key(
            customer_id=customer,
            customer_location_id=None,
            product_id=product,
            period_start_date=WEEK,
            site_label="S2",
        ),
    }
    # The upsert is a Core statement; reload ORM rows so every figure is read from the database.
    session.expire_all()
    rows = {
        row.source_key: row
        for row in session.scalars(
            select(FactCustomerSellthrough).where(FactCustomerSellthrough.tenant_id == TENANT)
        ).all()
    }
    assert chain_key not in rows
    assert set(rows) == {site_keys["S1"], site_keys["S2"], other_key}
    assert Decimal(rows[site_keys["S1"]].units_sold) == Decimal("10")
    assert Decimal(rows[site_keys["S1"]].reported_soh) == Decimal("4")
    assert rows[site_keys["S1"]].site_label == "S1"
    assert Decimal(rows[site_keys["S2"]].units_sold) == Decimal("7")
    assert Decimal(rows[site_keys["S2"]].reported_soh) == Decimal("2")
    assert rows[site_keys["S2"]].site_label == "S2"
    assert rows[other_key].id == other.id
    assert Decimal(rows[other_key].units_sold) == Decimal("9")
    assert Decimal(rows[other_key].reported_soh) == Decimal("8")

    moved = session.execute(
        text(
            "select import_job_id, superseded_by_import_job_id, reason, units_sold, "
            "row_json->>'source_key', row_json->>'site_label' "
            "from fact_customer_sellthrough_superseded where tenant_id = :t"
        ),
        {"t": TENANT},
    ).all()
    assert len(moved) == 1
    assert moved[0][0] == job.id and moved[0][1] == job.id
    assert moved[0][2] == "restated_by_newer_load"
    assert Decimal(moved[0][3]) == Decimal("3")
    assert moved[0][4] == chain_key and moved[0][5] == "S1"

    pointed = {
        int(row[0]): (row[1], row[2])
        for row in session.execute(
            select(
                ImportCustomerSellthroughStagingLine.source_row_number,
                ImportCustomerSellthroughStagingLine.fact_sellthrough_row_id,
                ImportCustomerSellthroughStagingLine.apply_status,
            ).where(ImportCustomerSellthroughStagingLine.import_job_id == job.id)
        ).all()
    }
    assert pointed[1] == (rows[site_keys["S1"]].id, "applied")
    assert pointed[2] == (rows[site_keys["S2"]].id, "applied")
    assert pointed[3] == (other.id, "applied")
    unmatched = session.scalar(
        select(ImportCustomerSellthroughStagingLine).where(
            ImportCustomerSellthroughStagingLine.import_job_id == job.id,
            ImportCustomerSellthroughStagingLine.source_row_number == 4,
        )
    )
    assert unmatched is not None
    assert unmatched.resolution_status == "product_not_matched"
    assert unmatched.apply_status is None
    assert unmatched.resolved_product_id is None
    assert _counts(session) == masters_before

    snapshot = sorted((key, str(row.units_sold), str(row.reported_soh)) for key, row in rows.items())
    second = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert second.errors == []
    assert second.applied == 0
    assert second.superseded_rows == 0
    assert second.superseded_units == 0.0
    session.expire_all()
    again = {
        row.source_key: row
        for row in session.scalars(
            select(FactCustomerSellthrough).where(FactCustomerSellthrough.tenant_id == TENANT)
        ).all()
    }
    assert sorted((key, str(row.units_sold), str(row.reported_soh)) for key, row in again.items()) == snapshot
    kept = session.execute(
        text("select count(*) from fact_customer_sellthrough_superseded where tenant_id = :t"),
        {"t": TENANT},
    ).scalar()
    assert kept == 1
    assert _counts(session) == masters_before


def test_reapply_idempotent_when_site_label_is_punctuation_only(session: Session) -> None:
    """B1: punctuation-only labels map to ``slh:…`` keys, not chain ``0``; re-apply does not double-count (B2)."""
    name = session.execute(text("select current_database()")).scalar()
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    job = ImportJob(
        tenant_id=TENANT,
        source_id=source,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="loaded",
        file_name="punct.xlsx",
        created_at=T0,
    )
    session.add(job)
    session.flush()

    punct_label = "@@@"
    site_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
        site_label=punct_label,
    )
    assert site_key.startswith(f"ct:{customer}:slh:")

    chain_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
    )
    collapsed = FactCustomerSellthrough(
        source_key=chain_key,
        tenant_id=TENANT,
        customer_id=customer,
        product_id=product,
        period_start_date=WEEK,
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal("5"),
        site_label=punct_label,
        import_job_id=job.id,
    )
    session.add(collapsed)
    session.flush()

    session.add(
        ImportCustomerSellthroughStagingLine(
            import_job_id=job.id,
            source_row_number=1,
            raw_row_payload={"u": "3"},
            resolved_customer_id=customer,
            resolved_product_id=product,
            period_start_date=WEEK,
            period_type="weekly",
            period_grain="week",
            units_sold=Decimal("3"),
            site_label=punct_label,
            resolution_status="resolved",
            apply_status="applied",
            fact_sellthrough_row_id=collapsed.id,
        )
    )
    session.flush()

    first = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert first.errors == []
    assert first.applied == 1
    row = session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key == site_key))
    assert row is not None
    assert Decimal(row.units_sold) == Decimal("3")

    second = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert second.errors == []
    assert second.applied == 0
    session.expire_all()
    again = session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key == site_key))
    assert again is not None and Decimal(again.units_sold) == Decimal("3")


def test_partial_rekey_same_job_does_not_retire_chain_while_chain_only_line_remains(session: Session) -> None:
    """B2: only some rows re-key in a run — the chain fact stays until every same-job line is rewritten."""
    name = session.execute(text("select current_database()")).scalar()
    if name != "cip_test":
        pytest.skip("cip_test only")

    source, customer, product, _other = _ids(session)
    job = ImportJob(
        tenant_id=TENANT,
        source_id=source,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="loaded",
        file_name="partial.xlsx",
        created_at=T0,
    )
    session.add(job)
    session.flush()

    chain_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
    )
    collapsed = FactCustomerSellthrough(
        source_key=chain_key,
        tenant_id=TENANT,
        customer_id=customer,
        product_id=product,
        period_start_date=WEEK,
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal("9"),
        import_job_id=job.id,
    )
    session.add(collapsed)
    session.flush()

    session.add_all(
        [
            ImportCustomerSellthroughStagingLine(
                import_job_id=job.id,
                source_row_number=1,
                raw_row_payload={"site": "S1", "units": "4"},
                resolved_customer_id=customer,
                resolved_product_id=product,
                period_start_date=WEEK,
                period_type="weekly",
                period_grain="week",
                units_sold=Decimal("4"),
                site_label="S1",
                resolution_status="resolved",
                apply_status="applied",
                fact_sellthrough_row_id=collapsed.id,
            ),
            ImportCustomerSellthroughStagingLine(
                import_job_id=job.id,
                source_row_number=2,
                raw_row_payload={"units": "5"},
                resolved_customer_id=customer,
                resolved_product_id=product,
                period_start_date=WEEK,
                period_type="weekly",
                period_grain="week",
                units_sold=Decimal("5"),
                site_label=None,
                raw_location_token=None,
                resolution_status="resolved",
                apply_status="applied",
                fact_sellthrough_row_id=collapsed.id,
            ),
        ]
    )
    session.flush()

    first = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert first.errors == []
    assert first.applied == 2
    assert first.superseded_rows == 0

    # The upsert is a Core statement; reload ORM rows so the chain fact is read from the database.
    session.expire_all()
    chain = session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key == chain_key))
    assert chain is not None
    assert Decimal(chain.units_sold) == Decimal("5")

    site_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
        site_label="S1",
    )
    site_row = session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key == site_key))
    assert site_row is not None
    assert Decimal(site_row.units_sold) == Decimal("4")

    assert (
        session.execute(
            text("select count(*) from fact_customer_sellthrough_superseded where tenant_id = :t"),
            {"t": TENANT},
        ).scalar()
        == 0
    )


def _chain_fact(customer: int, product: int, job_id: int, units: str, figure_jobs: dict | None = None):
    return FactCustomerSellthrough(
        source_key=customer_sellthrough_source_key(
            customer_id=customer,
            customer_location_id=None,
            product_id=product,
            period_start_date=WEEK,
        ),
        tenant_id=TENANT,
        customer_id=customer,
        product_id=product,
        period_start_date=WEEK,
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal(units),
        import_job_id=job_id,
        figure_import_jobs=figure_jobs or {},
    )


def _staged(job_id: int, row: int, customer: int, product: int, units: str, fact_id: int, site: str | None, **kw):
    return ImportCustomerSellthroughStagingLine(
        import_job_id=job_id,
        source_row_number=row,
        raw_row_payload={"site": site, "units": units, "row": row},
        resolved_customer_id=customer,
        resolved_product_id=product,
        period_start_date=kw.pop("period_start_date", WEEK),
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal(units),
        site_label=site,
        resolution_status="resolved",
        apply_status="applied",
        fact_sellthrough_row_id=fact_id,
        **kw,
    )


def _job(source: int, name: str, created_at: datetime) -> ImportJob:
    return ImportJob(
        tenant_id=TENANT,
        source_id=source,
        template_slug="customer_sell_through",
        import_mode="apply",
        status="completed",
        stage="loaded",
        file_name=name,
        created_at=created_at,
    )


def test_reapply_of_older_job_never_overwrites_or_retires_a_newer_jobs_chain_fact(session: Session) -> None:
    """Review B1: once a newer load wrote the chain key, re-applying the older job leaves it alone."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    older = _job(source, "older.xlsx", T0)
    newer = _job(source, "newer.xlsx", datetime(2026, 8, 8, tzinfo=timezone.utc))
    session.add_all([older, newer])
    session.flush()

    # The newer load now owns the chain fact the older job's rows still point at.
    fact = _chain_fact(customer, product, newer.id, "20", {"units_sold": newer.id})
    session.add(fact)
    session.flush()
    session.add_all(
        [
            _staged(older.id, 1, customer, product, "4", fact.id, "S1"),
            _staged(older.id, 2, customer, product, "5", fact.id, None),
            _staged(newer.id, 1, customer, product, "20", fact.id, None),
        ]
    )
    session.flush()

    result = apply_customer_sellthrough_staging(session, older.id, recompute_stock_gap=False)
    assert result.errors == []
    assert result.applied == 0
    assert result.superseded_rows == 0

    session.expire_all()
    stored = session.get(FactCustomerSellthrough, fact.id)
    assert stored is not None
    assert Decimal(stored.units_sold) == Decimal("20")
    assert int(stored.import_job_id) == newer.id
    site_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
        site_label="S1",
    )
    assert session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key == site_key)) is None
    newer_line = session.scalar(
        select(ImportCustomerSellthroughStagingLine).where(ImportCustomerSellthroughStagingLine.import_job_id == newer.id)
    )
    assert newer_line is not None and newer_line.fact_sellthrough_row_id == fact.id
    assert (
        session.execute(
            text("select count(*) from fact_customer_sellthrough_superseded where tenant_id = :t"),
            {"t": TENANT},
        ).scalar()
        == 0
    )


def test_no_rekey_while_a_line_on_the_chain_fact_would_be_skipped(session: Session) -> None:
    """Review N2: a skipped line keeps its fact off the re-key, so units never sit on both keys."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    job = _job(source, "skipped.xlsx", T0)
    session.add(job)
    session.flush()
    fact = _chain_fact(customer, product, job.id, "9")
    session.add(fact)
    session.flush()
    session.add_all(
        [
            _staged(job.id, 1, customer, product, "4", fact.id, "S1"),
            # Dated after the upload day: the apply loop leaves it staged.
            _staged(job.id, 2, customer, product, "5", fact.id, "S2", period_start_date=date(2099, 1, 5)),
        ]
    )
    session.flush()

    for _ in range(2):
        result = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
        assert result.errors == []
        assert result.applied == 0
        assert result.superseded_rows == 0

    session.expire_all()
    stored = session.get(FactCustomerSellthrough, fact.id)
    assert stored is not None and Decimal(stored.units_sold) == Decimal("9")
    site_key = customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
        site_label="S1",
    )
    assert session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key == site_key)) is None


def _site_key(customer: int, product: int, site: str) -> str:
    return customer_sellthrough_source_key(
        customer_id=customer,
        customer_location_id=None,
        product_id=product,
        period_start_date=WEEK,
        site_label=site,
    )


def _fact(session: Session, key: str):
    return session.scalar(select(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key == key))


def test_reapply_skips_chain_fact_with_a_figure_set_by_another_job(session: Session) -> None:
    """Review N7: the row names this job, but one figure on it was set by a newer job."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    older = _job(source, "older-mixed.xlsx", T0)
    newer = _job(source, "newer-mixed.xlsx", datetime(2026, 8, 8, tzinfo=timezone.utc))
    session.add_all([older, newer])
    session.flush()
    fact = _chain_fact(customer, product, older.id, "9", {"units_sold": older.id, "reported_soh": newer.id})
    fact.reported_soh = Decimal("7")
    session.add(fact)
    session.flush()
    session.add_all(
        [
            _staged(older.id, 1, customer, product, "4", fact.id, "S1"),
            _staged(older.id, 2, customer, product, "5", fact.id, "S2"),
        ]
    )
    session.flush()

    result = apply_customer_sellthrough_staging(session, older.id, recompute_stock_gap=False)
    assert result.errors == []
    assert result.applied == 0
    assert result.superseded_rows == 0
    session.expire_all()
    stored = session.get(FactCustomerSellthrough, fact.id)
    assert stored is not None
    assert Decimal(stored.units_sold) == Decimal("9") and Decimal(stored.reported_soh) == Decimal("7")
    assert _fact(session, _site_key(customer, product, "S1")) is None
    assert _fact(session, _site_key(customer, product, "S2")) is None


def _older_chain_state(session: Session, source: int, customer: int, product: int):
    """What an earlier apply left: one chain fact holding two site-named rows (S1 4/1, S2 5/2)."""
    older = _job(source, "older-chain.xlsx", T0)
    newer = _job(source, "newer-site.xlsx", datetime(2026, 8, 8, tzinfo=timezone.utc))
    session.add_all([older, newer])
    session.flush()
    chain = _chain_fact(customer, product, older.id, "9", {"units_sold": older.id, "reported_soh": older.id})
    chain.reported_soh = Decimal("3")
    session.add(chain)
    session.flush()
    session.add_all(
        [
            _staged(older.id, 1, customer, product, "4", chain.id, "S1", reported_soh=Decimal("1")),
            _staged(older.id, 2, customer, product, "5", chain.id, "S2", reported_soh=Decimal("2")),
        ]
    )
    session.flush()
    return older, newer, chain


def _newer_site_line(job_id: int, row: int, customer: int, product: int, site: str, **figures):
    return ImportCustomerSellthroughStagingLine(
        import_job_id=job_id,
        source_row_number=row,
        raw_row_payload={"site": site, "row": row, **{k: str(v) for k, v in figures.items()}},
        resolved_customer_id=customer,
        resolved_product_id=product,
        period_start_date=WEEK,
        period_type="weekly",
        period_grain="week",
        site_label=site,
        resolution_status="resolved",
        **figures,
    )


def test_older_reapply_after_newer_sales_only_site_load_keeps_newer_units(session: Session) -> None:
    """Review r5 B1: a newer sales-only load at site grain partly superseded the chain fact; the
    row still names the older job. Re-applying the older job must not write its units back."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    older, newer, chain = _older_chain_state(session, source, customer, product)
    session.add_all(
        [
            _newer_site_line(newer.id, 1, customer, product, "S1", units_sold=Decimal("6")),
            _newer_site_line(newer.id, 2, customer, product, "S2", units_sold=Decimal("5")),
        ]
    )
    session.flush()
    loaded = apply_customer_sellthrough_staging(session, newer.id, recompute_stock_gap=False)
    assert loaded.errors == [] and loaded.applied == 2
    session.expire_all()
    s1 = _fact(session, _site_key(customer, product, "S1"))
    assert s1 is not None and Decimal(s1.units_sold) == Decimal("6") and int(s1.import_job_id) == newer.id
    kept = session.execute(
        text("select count(*) from fact_customer_sellthrough_superseded where fact_id = :f and superseded_by_import_job_id = :j"),
        {"f": chain.id, "j": newer.id},
    ).scalar()
    assert kept >= 1  # precondition: the newer load superseded a figure on the chain fact

    for _ in range(2):
        again = apply_customer_sellthrough_staging(session, older.id, recompute_stock_gap=False)
        assert again.errors == []
        assert again.applied == 0
        assert again.superseded_rows == 0
    session.expire_all()
    s1 = _fact(session, _site_key(customer, product, "S1"))
    s2 = _fact(session, _site_key(customer, product, "S2"))
    assert s1 is not None and Decimal(s1.units_sold) == Decimal("6") and int(s1.import_job_id) == newer.id
    assert s2 is not None and Decimal(s2.units_sold) == Decimal("5") and int(s2.import_job_id) == newer.id
    assert session.get(FactCustomerSellthrough, chain.id) is not None
    newer_lines = session.scalars(
        select(ImportCustomerSellthroughStagingLine).where(ImportCustomerSellthroughStagingLine.import_job_id == newer.id)
    ).all()
    assert {int(x.fact_sellthrough_row_id) for x in newer_lines} == {int(s1.id), int(s2.id)}


def test_older_reapply_after_newer_stock_only_site_load_keeps_newer_on_hand(session: Session) -> None:
    """Mirror case: the newer site-grain load carries on-hand only."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    older, newer, chain = _older_chain_state(session, source, customer, product)
    session.add_all(
        [
            _newer_site_line(newer.id, 1, customer, product, "S1", reported_soh=Decimal("7")),
            _newer_site_line(newer.id, 2, customer, product, "S2", reported_soh=Decimal("8")),
        ]
    )
    session.flush()
    loaded = apply_customer_sellthrough_staging(session, newer.id, recompute_stock_gap=False)
    assert loaded.errors == [] and loaded.applied == 2
    session.expire_all()
    kept = session.execute(
        text("select count(*) from fact_customer_sellthrough_superseded where fact_id = :f and superseded_by_import_job_id = :j"),
        {"f": chain.id, "j": newer.id},
    ).scalar()
    assert kept >= 1

    again = apply_customer_sellthrough_staging(session, older.id, recompute_stock_gap=False)
    assert again.errors == []
    assert again.applied == 0
    assert again.superseded_rows == 0
    session.expire_all()
    s1 = _fact(session, _site_key(customer, product, "S1"))
    assert s1 is not None and Decimal(s1.reported_soh) == Decimal("7") and int(s1.import_job_id) == newer.id
    assert "units_sold" not in (s1.figure_import_jobs or {})
    assert session.get(FactCustomerSellthrough, chain.id) is not None


# --- N-0118 review follow-up: NB1 (chunked lookups) and NB3 (one whitespace rule) ---

from sqlalchemy import event, literal  # noqa: E402

from app.services.imports import customer_sell_through_apply as apply_mod  # noqa: E402

_NB13_SITES = ("NB13A", "NB13B", "NB13C", "NB13D", "NB13E")


def _nb13_setup(session: Session, file_name: str):
    """One chain fact this job owns, holding five site-named rows (units 1..5)."""
    source, customer, product, _other = _ids(session)
    keys = [_site_key(customer, product, site) for site in _NB13_SITES]
    taken = session.scalar(
        select(func.count()).select_from(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key.in_(keys))
    )
    if taken:
        pytest.skip("cip_test already holds a fixture site key for the fixture week")
    job = _job(source, file_name, T0)
    session.add(job)
    session.flush()
    chain = _chain_fact(customer, product, job.id, "15")
    session.add(chain)
    session.flush()
    session.add_all(
        [_staged(job.id, i + 1, customer, product, str(i + 1), chain.id, site) for i, site in enumerate(_NB13_SITES)]
    )
    session.flush()
    return source, customer, product, job, chain, keys


def _record_key_binds(session: Session, keys: list[str]):
    """How many of ``keys`` each SELECT binds; returns (counts, stop)."""
    wanted = set(keys)
    counts: list[int] = []
    conn = session.connection()

    def before(_conn, _cursor, statement, parameters, _context, _executemany):
        if not str(statement).lstrip().upper().startswith("SELECT"):
            return
        values = parameters.values() if isinstance(parameters, dict) else (parameters or ())
        n = sum(1 for v in values if isinstance(v, str) and v in wanted)
        if n:
            counts.append(n)

    event.listen(conn, "before_cursor_execute", before)
    return counts, lambda: event.remove(conn, "before_cursor_execute", before)


def test_rekey_reads_target_site_keys_in_chunks(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """NB1: five target site keys with a lookup chunk of 2 are read in three statements, and the
    re-key is the same as unchunked: five site facts, the chain fact moved aside, then nothing."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    monkeypatch.setattr(apply_mod, "_LOOKUP_CHUNK_SIZE", 2)
    _source, customer, product, job, chain, keys = _nb13_setup(session, "nb13-chunks.xlsx")
    chain_id = int(chain.id)

    counts, stop = _record_key_binds(session, keys)
    try:
        # A small apply chunk too, so no other SELECT of this run binds more than two keys.
        first = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False, chunk_size=2)
    finally:
        stop()
    assert first.errors == []
    assert first.applied == 5
    assert first.superseded_rows == 1
    assert first.superseded_units == 15.0
    assert counts, "the target site keys were never looked up"
    assert max(counts) <= 2, counts
    assert len([n for n in counts if n]) >= 3, counts

    session.expire_all()
    assert session.get(FactCustomerSellthrough, chain_id) is None
    for i, key in enumerate(keys):
        row = _fact(session, key)
        assert row is not None and Decimal(row.units_sold) == Decimal(i + 1)
        assert int(row.import_job_id) == job.id

    second = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert second.errors == [] and second.applied == 0 and second.superseded_rows == 0


def test_target_key_in_a_later_chunk_still_blocks_the_rekey(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """NB1 + NB4: the only protection here is the target-key check. The last site key (third
    chunk of 2) already holds a newer job's fact, so the chain fact is left exactly as stored."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    monkeypatch.setattr(apply_mod, "_LOOKUP_CHUNK_SIZE", 2)
    source, customer, product, job, chain, keys = _nb13_setup(session, "nb13-blocked.xlsx")
    newer = _job(source, "nb13-newer.xlsx", datetime(2026, 8, 8, tzinfo=timezone.utc))
    session.add(newer)
    session.flush()
    assert sorted(keys)[-1] == keys[-1]  # NB13E sorts last, so it is in the last chunk
    foreign = FactCustomerSellthrough(
        source_key=keys[-1],
        tenant_id=TENANT,
        customer_id=customer,
        product_id=product,
        period_start_date=WEEK,
        period_type="weekly",
        period_grain="week",
        units_sold=Decimal("42"),
        site_label=_NB13_SITES[-1],
        import_job_id=newer.id,
        figure_import_jobs={"units_sold": newer.id},
    )
    session.add(foreign)
    session.flush()

    result = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert result.errors == []
    assert result.applied == 0
    assert result.superseded_rows == 0
    session.expire_all()
    stored = session.get(FactCustomerSellthrough, chain.id)
    assert stored is not None and Decimal(stored.units_sold) == Decimal("15")
    for key in keys[:-1]:
        assert _fact(session, key) is None
    kept = session.get(FactCustomerSellthrough, foreign.id)
    assert kept is not None and Decimal(kept.units_sold) == Decimal("42") and int(kept.import_job_id) == newer.id


def test_claimed_by_other_jobs_reads_fact_ids_in_chunks(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """NB1: the staging half of the claim check finds claims in every chunk of fact ids."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    monkeypatch.setattr(apply_mod, "_LOOKUP_CHUNK_SIZE", 2)
    source, customer, product, _other = _ids(session)
    keys = [_site_key(customer, product, site) for site in _NB13_SITES]
    if session.scalar(
        select(func.count()).select_from(FactCustomerSellthrough).where(FactCustomerSellthrough.source_key.in_(keys))
    ):
        pytest.skip("cip_test already holds a fixture site key for the fixture week")
    job = _job(source, "nb13-claims.xlsx", T0)
    other = _job(source, "nb13-claims-other.xlsx", datetime(2026, 8, 8, tzinfo=timezone.utc))
    session.add_all([job, other])
    session.flush()
    facts = []
    for site, key in zip(_NB13_SITES, keys):
        fact = _chain_fact(customer, product, job.id, "1")
        fact.source_key = key
        fact.site_label = site
        facts.append(fact)
    session.add_all(facts)
    session.flush()
    ids = sorted(int(f.id) for f in facts)
    session.add_all(
        [
            _staged(other.id, 1, customer, product, "1", ids[0], _NB13_SITES[0]),
            _staged(other.id, 2, customer, product, "1", ids[-1], _NB13_SITES[-1]),
            _staged(job.id, 1, customer, product, "1", ids[2], _NB13_SITES[2]),
        ]
    )
    session.flush()
    assert apply_mod._claimed_by_other_jobs(session, set(ids), job.id) == {ids[0], ids[-1]}


_NB3_SAMPLES = (
    None,
    "",
    " ",
    "\t",
    "\n\r",
    "\x0b\x0c",
    "\x1c\x1f",
    "\x85",
    "\u00a0",
    "\u1680",
    "\u2003",
    "\u2028\u2029",
    "\u202f\u205f",
    "\u3000",
    " \u00a0\t\u3000 ",
    "\u200b",  # zero-width space: not whitespace to Python, so it names a site on both sides
    "S1",
    " S1\u00a0",
    "\tG007\u3000",
)


def test_sql_blank_site_test_matches_python_strip(session: Session) -> None:
    """NB3: SQL ``btrim`` with the shared set strips exactly what Python ``strip()`` strips."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    for sample in _NB3_SAMPLES:
        sql_present = session.execute(select(apply_mod._site_text_present(literal(sample, type_=Text)))).scalar()
        assert bool(sql_present) == bool(str(sample or "").strip()), repr(sample)
        if sample is not None:
            stripped = session.execute(select(func.btrim(literal(sample, type_=Text), apply_mod._PY_WHITESPACE))).scalar()
            assert stripped == sample.strip(), repr(sample)


@pytest.mark.parametrize("label", ["\t", "\u00a0", "\u3000", " \u2003 "])
def test_whitespace_only_site_label_leaves_the_chain_fact_alone(session: Session, label: str) -> None:
    """NB3: a whitespace-only label is chain-only to both SQL and Python, so a re-apply neither
    re-keys nor retires the chain fact (before: SQL saw a site, Python did not, and the retire
    step moved the fact and its units aside)."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    job = _job(source, "nb3-blank.xlsx", T0)
    session.add(job)
    session.flush()
    chain = _chain_fact(customer, product, job.id, "9")
    session.add(chain)
    session.flush()
    line = _staged(job.id, 1, customer, product, "9", chain.id, label)
    session.add(line)
    session.flush()

    for _ in range(2):
        result = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
        assert result.errors == []
        assert result.applied == 0
        assert result.superseded_rows == 0
    session.expire_all()
    stored = session.get(FactCustomerSellthrough, chain.id)
    assert stored is not None and Decimal(stored.units_sold) == Decimal("9")
    again = session.get(ImportCustomerSellthroughStagingLine, line.id)
    assert again is not None and again.fact_sellthrough_row_id == chain.id
    assert (
        session.execute(
            text("select count(*) from fact_customer_sellthrough_superseded where tenant_id = :t"),
            {"t": TENANT},
        ).scalar()
        == 0
    )


def test_whitespace_label_with_location_token_rekeys_to_the_token(session: Session) -> None:
    """NB3: a blank label falls back to the location token on both sides, so the row re-keys to
    the token's site key and the chain fact moves aside once."""
    name = session.execute(text("select current_database()")).scalar()
    print(f"current_database={name}", flush=True)
    if name != "cip_test":
        pytest.skip("cip_test only")
    source, customer, product, _other = _ids(session)
    key = _site_key(customer, product, _NB13_SITES[0])
    if _fact(session, key) is not None:
        pytest.skip("cip_test already holds the fixture site key")
    job = _job(source, "nb3-token.xlsx", T0)
    session.add(job)
    session.flush()
    chain = _chain_fact(customer, product, job.id, "9")
    session.add(chain)
    session.flush()
    chain_id = int(chain.id)
    session.add(_staged(job.id, 1, customer, product, "9", chain_id, "\u00a0\t", raw_location_token=_NB13_SITES[0]))
    session.flush()

    first = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert first.errors == [] and first.applied == 1 and first.superseded_rows == 1
    session.expire_all()
    assert session.get(FactCustomerSellthrough, chain_id) is None
    row = _fact(session, key)
    assert row is not None and Decimal(row.units_sold) == Decimal("9") and row.site_label == _NB13_SITES[0]
    second = apply_customer_sellthrough_staging(session, job.id, recompute_stock_gap=False)
    assert second.errors == [] and second.applied == 0 and second.superseded_rows == 0
