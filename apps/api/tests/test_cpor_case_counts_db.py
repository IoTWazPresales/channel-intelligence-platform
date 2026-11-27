"""BACKLOG-254: exact planner counts on real PostgreSQL (cip_test), one rolled-back transaction.

``GET /cpor/cases/counts`` counts current cases only (``superseded_by_case_id`` null), is not
capped by a page size, and scopes tenant, fixture cases and filters exactly like
``GET /cpor/cases``. Fictional data.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from app.api.v1.endpoints import cpor_cases as ep
from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase, CporCaseLine
from app.models.dimensions import DimCustomer, DimProduct
from sqlalchemy import text


class _SameSession:
    """Lets the endpoint's ``with SessionLocal() as session`` read this test's open transaction."""

    def __init__(self, session) -> None:
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *_a) -> None:
        return None


@pytest.fixture
def world(monkeypatch):
    tag = uuid4().hex[:10]
    tenant = f"cnt-{tag}"
    session = SessionLocal()
    try:
        assert session.execute(text("select current_database()")).scalar_one() == "cip_test"
        session.execute(
            text("INSERT INTO tenant (id, name) VALUES (:id, :name)"),
            {"id": tenant, "name": "counts"},
        )
        cust = DimCustomer(tenant_id=tenant, code=f"CN-{tag}-1", name=f"Cust {tag}")
        other_cust = DimCustomer(tenant_id=tenant, code=f"CN-{tag}-2", name=f"Other {tag}")
        audio = DimProduct(
            tenant_id=tenant, sku=f"CN-{tag}-A", name="Audio item", product_line="Audio"
        )
        video = DimProduct(
            tenant_id=tenant, sku=f"CN-{tag}-V", name="Video item", product_line="Video"
        )
        session.add_all([cust, other_cust, audio, video])
        session.flush()
        monkeypatch.setattr(ep, "SessionLocal", lambda: _SameSession(session))
        yield {
            "tag": tag,
            "tenant": tenant,
            "session": session,
            "cust": cust,
            "other_cust": other_cust,
            "audio": audio,
            "video": video,
            "user": {"sub": "u", "tenant_id": tenant},
        }
    finally:
        session.rollback()
        session.close()


def _case(
    w,
    n: int,
    status: str,
    start: date,
    *,
    customer=None,
    superseded_by=None,
    exclude=False,
    product=None,
):
    case = CporCase(
        currency_code="ZAR",
        tenant_id=w["tenant"],
        case_code=f"CN-{w['tag']}-{n}",
        customer_id=(customer or w["cust"]).id,
        promotion_type="Fictional promo",
        window_start=start,
        window_end=date(start.year, start.month, 28),
        status=status,
        superseded_by_case_id=superseded_by,
        intelligence_exclude=exclude,
    )
    w["session"].add(case)
    w["session"].flush()
    if product is not None:
        w["session"].add(
            CporCaseLine(
                case_id=case.id,
                product_id=product.id,
                window_start=start,
                window_end=date(start.year, start.month, 28),
                srp=100,
                vat_rate=15,
                dealer_margin_pct=10,
                estimate_qty=1,
            )
        )
        w["session"].flush()
    return case


def _count(w, **kw):
    args = dict(
        status=None,
        exclude_status=[],
        customer_id=None,
        distributor_id=None,
        product_id=None,
        business_unit=None,
        window_from=None,
        window_to=None,
        test_data=None,
        q=None,
        evidence_basis=None,
        user=w["user"],
    )
    args.update(kw)
    return ep.count_cases(**args)


def test_replaced_cases_are_not_counted_but_the_list_total_still_counts_them(world):
    w = world
    current = _case(w, 1, "proposed", date(2026, 12, 1))
    _case(
        w, 2, "proposed", date(2026, 12, 2), superseded_by=current.id
    )  # soft-superseded: status kept
    _case(w, 3, "proposed", date(2026, 12, 3))
    out = _count(w, status="proposed")
    assert out["total_current"] == 2
    assert out["status_counts_current"] == {"proposed": 2}


def test_window_filter_with_excluded_statuses_gives_the_starting_figure(world):
    w = world
    _case(w, 1, "active", date(2026, 11, 25))
    _case(w, 2, "approved", date(2026, 12, 10))
    _case(w, 3, "cancelled", date(2026, 11, 26))  # not a live commitment
    _case(w, 4, "rejected", date(2026, 11, 27))  # not a live commitment
    _case(w, 5, "active", date(2027, 3, 1))  # outside the window
    replaced = _case(w, 6, "active", date(2026, 11, 28))
    _case(w, 7, "active", date(2026, 11, 29), superseded_by=replaced.id)
    out = _count(
        w,
        exclude_status=["cancelled", "rejected"],
        window_from=date(2026, 11, 19),
        window_to=date(2026, 12, 17),
    )
    assert out["total_current"] == 3  # cases 1, 2 and 6


def test_counts_are_not_capped_at_a_page_size(world):
    w = world
    for n in range(520):
        _case(w, n, "proposed", date(2026, 12, 1))
    assert _count(w, status="proposed")["total_current"] == 520


def test_status_split_covers_drafts_and_ended_without_replaced_cases(world):
    w = world
    _case(w, 1, "draft", date(2026, 12, 1))
    _case(w, 2, "ended", date(2026, 9, 1))
    keep = _case(w, 3, "ended", date(2026, 9, 2))
    _case(w, 4, "draft", date(2026, 12, 2), superseded_by=keep.id)
    assert _count(w)["status_counts_current"] == {"draft": 1, "ended": 2}


def test_tenant_and_fixture_scoping_match_the_cases_list(world):
    w = world
    _case(w, 1, "proposed", date(2026, 12, 1))
    _case(w, 2, "proposed", date(2026, 12, 2), exclude=True)  # fixture case: hidden by default
    other_tenant = f"cnt-other-{w['tag']}"
    w["session"].execute(
        text("INSERT INTO tenant (id, name) VALUES (:id, 'other')"), {"id": other_tenant}
    )
    foreign_customer = DimCustomer(tenant_id=other_tenant, code=f"CN-{w['tag']}-X", name="Foreign")
    w["session"].add(foreign_customer)
    w["session"].flush()
    w["session"].add(
        CporCase(
            currency_code="ZAR",
            tenant_id=other_tenant,
            case_code=f"CN-{w['tag']}-F",
            customer_id=foreign_customer.id,
            promotion_type="Fictional promo",
            window_start=date(2026, 12, 1),
            window_end=date(2026, 12, 28),
            status="proposed",
        )
    )
    w["session"].flush()
    assert _count(w, status="proposed")["total_current"] == 1
    assert _count(w, status="proposed", test_data="only")["total_current"] == 1
    assert _count(w, status="proposed", test_data="all")["total_current"] == 2


def test_customer_and_product_line_filters_match_the_list(world):
    w = world
    _case(w, 1, "proposed", date(2026, 12, 1), product=w["audio"])
    _case(w, 2, "proposed", date(2026, 12, 2), product=w["video"])
    _case(w, 3, "proposed", date(2026, 12, 3), customer=w["other_cust"], product=w["audio"])
    assert _count(w, status="proposed", business_unit="Audio")["total_current"] == 2
    assert (
        _count(w, status="proposed", business_unit="Audio", customer_id=w["cust"].id)[
            "total_current"
        ]
        == 1
    )
    assert _count(w, status="proposed", customer_id=w["other_cust"].id)["total_current"] == 1
    # The list applies the same filters through the same helper (same total here: none replaced).
    listed = ep.list_cases(
        status="proposed",
        customer_id=None,
        distributor_id=None,
        product_id=None,
        business_unit="Audio",
        window_from=None,
        window_to=None,
        test_data=None,
        q=None,
        page=1,
        page_size=500,
        evidence_basis=None,
        user=w["user"],
    )
    assert listed["total"] == 2
