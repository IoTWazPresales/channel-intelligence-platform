"""Addable Sell-through filters (Warren 2026-10-19): product fields, Product Master specs, customer
fields and store, offered from the values that exist and resolved to products, customers and stores.
One rolled-back transaction; cip_test only."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimProduct
from app.models.fact_customer_sellthrough import FactCustomerSellthrough
from app.services.business_calendar import BusinessCalendar
from app.services.channel_intelligence.sell_through_dimensions import (
    available_dimensions,
    resolve_dimension_filters,
)
from app.services.channel_intelligence.sell_through_overview import OverviewFilters, build_overview

TENANT = "st-dims-test"


@pytest.fixture
def session():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        conn.rollback()
        outer = conn.begin()
        db = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield db
        finally:
            db.close()
            outer.rollback()
    engine.dispose()


def _seed(db: Session):
    c1 = DimCustomer(code="STD-C1", name="Dims One", is_key_account=True)
    c2 = DimCustomer(code="STD-C2", name="Dims Two", is_key_account=False)
    db.add_all([c1, c2])
    p16 = DimProduct(sku="STD-16", name="P16", business_unit="NB", specs_json={"RAM": "16GB", "CPU": "i5"})
    p32 = DimProduct(sku="STD-32", name="P32", business_unit="NB", specs_json={"import_staging": {"RAM": "32GB", "CPU": "i7"}})
    p8 = DimProduct(sku="STD-8", name="P8", business_unit="Gaming", specs_json={"RAM": "8GB", "CPU": "i5"})
    db.add_all([p16, p32, p8])
    db.flush()
    n = 0
    for c, site in ((c1, "North"), (c2, "South")):
        for p in (p16, p32, p8):
            n += 1
            db.add(
                FactCustomerSellthrough(
                    source_key=f"st-dims-{n}", tenant_id=TENANT, customer_id=c.id, product_id=p.id,
                    period_start_date=date(2026, 10, 5), period_type="weekly", period_grain="week",
                    units_sold=10, site_label=site,
                )
            )
    db.flush()
    return c1, c2, p16, p32, p8


def test_dimensions_offered_from_data(session: Session):
    _c1, _c2, *_ = _seed(session)
    dims = {d["key"]: d for d in available_dimensions(session, TENANT)}
    assert dims["spec:RAM"]["values"] == ["8GB", "16GB", "32GB"]  # natural order, nested specs included
    assert dims["prod:business_unit"]["values"] == ["Gaming", "NB"]
    assert dims["site"]["values"] == ["North", "South"]
    assert dims["cust:key_account"]["values"] == ["Yes", "No"]


def test_filters_resolve_and_apply(session: Session):
    c1, _c2, p16, p32, p8 = _seed(session)
    prods, custs, sites = resolve_dimension_filters(
        session, TENANT, {"spec:RAM": ["16GB", "32GB"], "prod:business_unit": ["NB"], "cust:key_account": ["Yes"], "site": ["North"]}
    )
    assert prods == {p16.id, p32.id} and p8.id not in prods
    assert custs == {c1.id}
    assert sites == ["North"]
    f = OverviewFilters(
        date_from=date(2026, 10, 5), date_to=date(2026, 10, 11), tenant_id=TENANT,
        customer_ids=sorted(custs), product_ids=sorted(prods), sites=sites,
    )
    out = build_overview(session, f, BusinessCalendar(), today=date(2026, 10, 19), vat_rate=0.15)
    assert out["kpis"]["units"] == pytest.approx(20)


def test_too_many_or_unknown_filters_refused(session: Session):
    _seed(session)
    with pytest.raises(ValueError):
        resolve_dimension_filters(session, TENANT, {f"spec:x{i}": ["a"] for i in range(7)})
    with pytest.raises(ValueError):
        resolve_dimension_filters(session, TENANT, {"prod:nope": ["a"]})
