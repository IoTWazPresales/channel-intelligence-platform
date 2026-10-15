"""N-0095: every customer resolver follows ``merged_into_customer_id`` to the keeper.

A merged record (the loser) is reached three ways: its name, its code, and an approved alias that
was left pointing at it. Each resolver must answer with the keeper for all three.

One rolled-back transaction; cip_test only.
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.models.ingestion import ImportJob
from app.models.shipment_evidence import ShipmentEvidenceLine


@pytest.fixture
def db():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        conn.rollback()
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
    engine.dispose()


@pytest.fixture
def merged(db: Session) -> dict:
    t = secrets.token_hex(4)
    keeper = DimCustomer(code=f"CUST-N0095R-{t}", name=f"Gamma{t} Keeper", customer_status="active")
    db.add(keeper)
    db.flush()
    loser = DimCustomer(
        code=f"TMP-CUST-N0095R-{t}",
        name=f"Gamma{t} Old Name",
        customer_status="merged",
        merged_into_customer_id=keeper.id,
    )
    db.add(loser)
    db.flush()
    alias_token = f"gamma{t} alias"
    db.add(
        CustomerSourceTokenAlias(
            customer_id=loser.id, raw_token=alias_token, normalized_token=alias_token, status="approved"
        )
    )
    db.commit()
    return {"keeper": keeper.id, "loser": loser.id, "name": loser.name, "code": loser.code, "alias": alias_token}


def test_dsi_resolver_follows_merge(db: Session, merged: dict) -> None:
    from app.services.imports.distributor_sales_inventory import _resolve_customer

    for token in (merged["name"], merged["code"], merged["alias"]):
        cid, diagnostics = _resolve_customer(
            db, source_id=None, distributor_id=None, customer_raw=token,
            dealer_group_raw=None, channel_raw=None, open_flag_raw=None,
        )
        assert cid == merged["keeper"], (token, diagnostics)


def test_dsi_resolution_cache_follows_merge(db: Session, merged: dict) -> None:
    from app.services.imports.distributor_sales_inventory import (
        _build_resolution_cache,
        _resolve_customer_from_cache,
    )

    cache = _build_resolution_cache(db, None)
    for token in (merged["name"], merged["code"], merged["alias"]):
        cid, diagnostics = _resolve_customer_from_cache(
            source_id=None, distributor_id=None, customer_raw=token,
            dealer_group_raw=None, channel_raw=None, open_flag_raw=None, res_cache=cache,
        )
        assert cid == merged["keeper"], (token, diagnostics)


def test_shipment_resolver_follows_merge(db: Session, merged: dict) -> None:
    from app.services.imports.shipment_resolved_entities import (
        apply_resolved_entities_to_line,
        resolve_shipment_customer_id_from_token,
    )

    assert resolve_shipment_customer_id_from_token(db, merged["alias"], None) == merged["keeper"]
    stamped = ShipmentEvidenceLine(customer_id=merged["loser"], distributor_id=1, raw_source_row={})
    apply_resolved_entities_to_line(stamped, db, None)
    assert stamped.resolved_customer_id == merged["keeper"]
    token_only = ShipmentEvidenceLine(customer_dealer_token=merged["alias"], distributor_id=1, raw_source_row={})
    apply_resolved_entities_to_line(token_only, db, None)
    assert token_only.resolved_customer_id == merged["keeper"]


def test_lineup_resolver_follows_merge(db: Session, merged: dict) -> None:
    from app.services.commercial_planner.lineup_case_parser import _build_customer_map
    from app.services.commercial_planner.lineup_customer_alias_resolution import (
        load_approved_customer_alias_id_by_token_sync,
        resolve_lineup_customer_id_from_token,
    )

    customers = list(db.scalars(select(DimCustomer)).all())
    customer_map = _build_customer_map(customers)
    alias_map = load_approved_customer_alias_id_by_token_sync(db)
    by_id = {int(c.id): c for c in customers}
    for token in (merged["name"], merged["code"], merged["alias"]):
        cid = resolve_lineup_customer_id_from_token(
            token, customer_map=customer_map, customer_alias_map=alias_map, customers_by_id=by_id
        )
        assert cid == merged["keeper"], token


def test_sellthrough_resolver_follows_merge(db: Session, merged: dict) -> None:
    from app.services.imports.customer_sell_through import resolve_customer_id_for_job

    job = ImportJob(staged_metadata={"customer_id": merged["loser"]})
    assert resolve_customer_id_for_job(db, job) == merged["keeper"]
