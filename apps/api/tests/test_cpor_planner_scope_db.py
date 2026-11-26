"""Step 2 (N-0122): the planner's default scope on real PostgreSQL (cip_test), one rolled-back transaction.

Warren (standing rules): "The promotion planner shows customer promotions, never sell-out." and "The planner
never shows closed, settled or ended cases (or old years) by default."
``promotion_family=customer_sell_through`` keeps Sell-Through PP only; ``open_only`` keeps draft/proposed/
approved/active, current (not replaced) cases whose window has not ended. List and counts share one helper.
Fictional data only.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from app.api.v1.endpoints import cpor_cases as ep
from app.db.session_sync import SessionLocal
from app.models.cpor import CporCase
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from fastapi import HTTPException
from sqlalchemy import text

TODAY = date.today()
FUTURE_START = date(TODAY.year + 1, 1, 5)
FUTURE_END = date(TODAY.year + 1, 1, 25)
PAST_START = date(TODAY.year - 1, 3, 1)
PAST_END = date(TODAY.year - 1, 3, 20)


class _SameSession:
    def __init__(self, session) -> None:
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *_a) -> None:
        return None


@pytest.fixture
def world(monkeypatch):
    tag = uuid4().hex[:10]
    tenant = f"scope-{tag}"
    session = SessionLocal()
    try:
        assert session.execute(text("select current_database()")).scalar_one() == "cip_test"
        session.execute(text("INSERT INTO tenant (id, name) VALUES (:id, :name)"), {"id": tenant, "name": "scope"})
        reporting = DimCustomer(tenant_id=tenant, code=f"SC-{tag}-R", name=f"Reporting {tag}")
        silent = DimCustomer(tenant_id=tenant, code=f"SC-{tag}-S", name=f"Silent {tag}")
        session.add_all([reporting, silent])
        session.flush()
        session.add(CustomerReportConfig(customer_id=reporting.id, reports_expected=True))
        session.flush()
        monkeypatch.setattr(ep, "SessionLocal", lambda: _SameSession(session))
        yield {"tag": tag, "tenant": tenant, "session": session, "reporting": reporting, "silent": silent,
               "user": {"sub": "u", "tenant_id": tenant}}
    finally:
        session.rollback()
        session.close()


def _case(w, n, promotion_type, status, start, end, *, customer=None, superseded_by=None):
    case = CporCase(
        tenant_id=w["tenant"],
        case_code=f"SC-{w['tag']}-{n}",
        customer_id=(customer or w["reporting"]).id,
        promotion_type=promotion_type,
        window_start=start,
        window_end=end,
        status=status,
        superseded_by_case_id=superseded_by,
    )
    w["session"].add(case)
    w["session"].flush()
    return case


def _seed(w):
    """One case per rule; the comment says whether the planner's default view keeps it."""
    out = {}
    out["open_st"] = _case(w, 1, "Sell-Through PP", "approved", FUTURE_START, FUTURE_END)  # kept
    out["live_st"] = _case(w, 2, "Sell-Through PP", "active", PAST_START, date(TODAY.year + 1, 2, 1))  # kept (open, started earlier)
    out["no_end_st"] = _case(w, 3, "Sell-Through PP", "draft", PAST_START, TODAY)  # kept (ends today: still open)
    out["ended_st"] = _case(w, 4, "Sell-Through PP", "ended", PAST_START, PAST_END)  # history only
    out["settled_st"] = _case(w, 5, "Sell-Through PP", "settled", PAST_START, PAST_END)  # history only
    out["cancel_st"] = _case(w, 6, "Sell-Through PP", "cancelled", FUTURE_START, FUTURE_END)  # history only
    out["stale_draft_st"] = _case(w, 7, "Sell-Through PP", "draft", PAST_START, PAST_END)  # window ended: history only
    replacement = out["open_st"]
    out["replaced_st"] = _case(w, 8, "Sell-Through PP", "proposed", FUTURE_START, FUTURE_END, superseded_by=replacement.id)
    out["sellout_open"] = _case(w, 9, "Sell out PP", "approved", FUTURE_START, FUTURE_END)  # never on the planner
    out["sellout_ended"] = _case(w, 10, "Sell out PP", "ended", PAST_START, PAST_END)  # never on the planner
    out["stock_open"] = _case(w, 11, "Stock PP (In-Direct)", "approved", FUTURE_START, FUTURE_END)  # off (B3)
    out["silent_open_st"] = _case(w, 12, "Sell-Through PP", "approved", FUTURE_START, FUTURE_END, customer=w["silent"])
    return out


def _list(w, **kw):
    args = dict(
        status=None, customer_id=None, distributor_id=None, product_id=None, business_unit=None,
        window_from=None, window_to=None, test_data=None, q=None, page=1, page_size=500,
        evidence_basis=None, reporting_only=True, official_promotion_types=False, user=w["user"],
    )
    args.update(kw)
    return ep.list_cases(**args)


def _count(w, **kw):
    args = dict(
        status=None, exclude_status=[], customer_id=None, distributor_id=None, product_id=None,
        business_unit=None, window_from=None, window_to=None, test_data=None, q=None,
        evidence_basis=None, reporting_only=True, user=w["user"],
    )
    args.update(kw)
    return ep.count_cases(**args)


def _codes(page) -> set[str]:
    return {r["case_code"] for r in page["items"]}


def test_default_planner_scope_lists_open_customer_sell_through_only(world):
    w = world
    c = _seed(w)
    page = _list(w, promotion_family="customer_sell_through", open_only=True)
    assert _codes(page) == {c["open_st"].case_code, c["live_st"].case_code, c["no_end_st"].case_code}
    assert all(r["promotion_type"] == "Sell-Through PP" for r in page["items"])
    assert page["total"] == 3


def test_history_keeps_the_family_and_adds_the_closed_cases(world):
    w = world
    c = _seed(w)
    page = _list(w, promotion_family="customer_sell_through", open_only=False)
    expected = {c[k].case_code for k in (
        "open_st", "live_st", "no_end_st", "ended_st", "settled_st", "cancel_st", "stale_draft_st", "replaced_st",
    )}
    assert _codes(page) == expected
    assert not any(r["promotion_type"] == "Sell out PP" for r in page["items"])
    # Status chips on a family-scoped list count that family's book only (no sell-out, no Stock PP).
    assert sum(page["status_counts"].values()) == len(expected)


def test_counts_use_the_same_scope_as_the_list(world):
    w = world
    c = _seed(w)
    open_counts = _count(w, promotion_family="customer_sell_through", open_only=True)
    assert open_counts["total_current"] == 3
    assert open_counts["status_counts_current"] == {"approved": 1, "active": 1, "draft": 1}
    book = _count(w, promotion_family="customer_sell_through", open_only=False)
    # Current cases only: the replaced one is left out of the counts (the list total keeps it).
    assert book["total_current"] == 7
    assert book["status_counts_current"]["ended"] == 1
    # The two sell-out cases are counted only under their own family.
    assert _count(w, promotion_family="distributor_sell_out")["total_current"] == 2
    assert c["sellout_open"].status == "approved"


def test_sell_out_family_still_reads_the_sell_out_cases(world):
    w = world
    c = _seed(w)
    page = _list(w, promotion_family="distributor_sell_out", open_only=False)
    assert _codes(page) == {c["sellout_open"].case_code, c["sellout_ended"].case_code}


def test_no_family_keeps_the_existing_behaviour(world):
    w = world
    _seed(w)
    page = _list(w)
    # Reporting customer only, every type, every status (replaced included in the list total), as before.
    assert page["total"] == 11


def test_unknown_family_is_a_400_on_list_and_counts(world):
    w = world
    with pytest.raises(HTTPException) as e1:
        _list(w, promotion_family="nope")
    with pytest.raises(HTTPException) as e2:
        _count(w, promotion_family="nope")
    assert e1.value.status_code == e2.value.status_code == 400
