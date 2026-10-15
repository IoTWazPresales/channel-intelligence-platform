"""N-0083: the FX table is written and read by the app role, and a case rate is chosen from the
stored rate for the case's own date (or an audited override) and fixed at first approval.

One rolled-back transaction; cip_test only.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.cpor import CporCase, CporCaseEvent
from app.models.dimensions import DimCustomer
from app.models.fx_rate import FxDailyRate
from app.services.cpor import fx_rate
from app.services.cpor.fx_rate import (
    BOOKED_KEPT,
    BOOKED_OVERRIDE,
    BOOKED_STORED,
    FxOverrideReasonRequired,
    FxRateFixed,
    apply_create_fx,
    book_on_approve,
    ensure_rate_for_date,
    rate_for_case_date,
)

DAY = date(2031, 3, 5)  # Wednesday; no real row exists this far ahead
TODAY = date(2031, 6, 30)
NOW = datetime(2031, 6, 30, 8, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        if conn.execute(text("select current_database()")).scalar() != "cip_test":
            pytest.skip("cip_test only")
        if not conn.execute(
            text(
                "select 1 from information_schema.columns "
                "where table_name = 'cpor_case' and column_name = 'fx_booked_source'"
            )
        ).scalar():
            pytest.skip("20261015_0039 is not applied")
        conn.rollback()
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
    engine.dispose()


def _rate(db: Session, rate_date: date, rate: float, *, fallback: bool = False) -> FxDailyRate:
    row = FxDailyRate(
        rate_date=rate_date,
        quote_pair="USDZAR",
        rate=rate,
        source="frankfurter.ecb",
        fetched_at=NOW,
        is_fallback=fallback,
    )
    db.add(row)
    db.flush()
    return row


def _case(db: Session, window_start: date, **kw) -> CporCase:
    customer = db.scalar(select(DimCustomer.id).order_by(DimCustomer.id).limit(1))
    if customer is None:
        pytest.skip("cip_test needs a customer")
    case = CporCase(
        case_code=f"N0083-{window_start.isoformat()}-{kw.pop('suffix', 'a')}",
        customer_id=int(customer),
        promotion_type="Price Drop",
        window_start=window_start,
        window_end=window_start + timedelta(days=30),
        status="proposed",
        **kw,
    )
    db.add(case)
    db.flush()
    return case


def _no_fetch(*_a, **_k):
    raise AssertionError("a stored rate must not be fetched again")


def test_the_app_role_can_read_and_write_the_rate_table(db):
    assert db.scalar(text("select has_table_privilege(current_user, 'fx_daily_rate', 'INSERT')"))
    assert db.scalar(text("select has_table_privilege(current_user, 'fx_daily_rate', 'UPDATE')"))
    assert db.scalar(text("select has_table_privilege(current_user, 'fx_daily_rate', 'SELECT')"))
    assert db.scalar(text("select has_sequence_privilege(current_user, 'fx_daily_rate_id_seq', 'USAGE')"))


def test_a_fetched_rate_is_stored_and_a_later_fetch_updates_it(db):
    with patch.object(fx_rate, "fetch_frankfurter", return_value=(DAY, 18.40)):
        first = ensure_rate_for_date(db, DAY)
    assert first.persisted and first.rate == 18.40 and first.rate_date == DAY
    row = db.scalar(select(FxDailyRate).where(FxDailyRate.rate_date == DAY))
    assert float(row.rate) == 18.40 and row.source == "frankfurter.ecb" and row.is_fallback is False
    with patch.object(fx_rate, "fetch_frankfurter", return_value=(DAY, 18.55)):
        ensure_rate_for_date(db, DAY)
    rows = db.scalars(select(FxDailyRate).where(FxDailyRate.rate_date == DAY)).all()
    assert len(rows) == 1 and float(rows[0].rate) == 18.55


def test_a_failed_fetch_gives_no_rate_and_stores_nothing(db):
    import urllib.error

    with patch.object(fx_rate, "fetch_frankfurter", side_effect=urllib.error.URLError("down")):
        quote = ensure_rate_for_date(db, DAY)
    assert quote.rate is None and quote.fetch_failed and not quote.live
    assert db.scalar(select(FxDailyRate).where(FxDailyRate.rate_date == DAY)) is None


def test_the_poller_stores_todays_rate(db):
    @contextmanager
    def session_local():
        yield db

    from app.services.cpor import fx_rate_poller

    with patch("app.db.session_sync.SessionLocal", session_local), patch.object(
        fx_rate, "_utc_today", return_value=DAY
    ), patch.object(fx_rate, "fetch_frankfurter", return_value=(DAY, 18.31)):
        out = fx_rate_poller.fetch_daily_fx_rate_safe(reason="test")
    assert out["rate"] == 18.31 and out["persisted"] is True
    assert float(db.scalar(select(FxDailyRate.rate).where(FxDailyRate.rate_date == DAY))) == 18.31


def test_a_stored_rate_for_the_case_date_is_used_without_a_fetch(db):
    _rate(db, DAY, 18.10)
    with patch.object(fx_rate, "fetch_frankfurter", _no_fetch):
        quote = rate_for_case_date(db, DAY, today=TODAY)
    assert quote.rate == 18.10 and quote.rate_date == DAY and quote.live


def test_a_weekend_case_date_uses_the_friday_rate(db):
    friday = date(2031, 3, 7)
    _rate(db, friday, 18.20)
    with patch.object(fx_rate, "fetch_frankfurter", _no_fetch):
        quote = rate_for_case_date(db, date(2031, 3, 9), today=TODAY)
    assert quote.rate == 18.20 and quote.rate_date == friday


def test_an_older_stored_rate_is_not_passed_off_as_the_rate_for_the_date(db):
    _rate(db, DAY, 18.10)
    later = DAY + timedelta(days=20)
    with patch.object(fx_rate, "fetch_frankfurter", return_value=(later, 19.00)):
        quote = rate_for_case_date(db, later, today=TODAY)
    assert quote.rate == 19.00 and quote.rate_date == later


def test_a_fallback_row_is_not_used(db):
    _rate(db, DAY, 18.10, fallback=True)
    with patch.object(fx_rate, "fetch_frankfurter", return_value=(DAY, 18.60)):
        quote = rate_for_case_date(db, DAY, today=TODAY)
    assert quote.rate == 18.60


def test_create_books_the_rate_stored_for_the_window_start(db):
    _rate(db, DAY, 18.10)
    case = _case(db, DAY, suffix="create")
    with patch.object(fx_rate, "_utc_today", return_value=TODAY), patch.object(
        fx_rate, "fetch_frankfurter", _no_fetch
    ):
        apply_create_fx(db, case, actor="pm", proposed_override=None, explicit_roe=None)
    db.flush()
    assert float(case.roe_snapshot) == 18.10 and case.fx_mode == "booked"
    assert case.fx_booked_source == BOOKED_STORED and case.fx_booked_rate_date == DAY
    assert float(case.fx_proposed_rate) == 18.10


def test_approval_fixes_the_stored_rate_for_the_case_date_and_records_it(db):
    _rate(db, DAY, 18.10)
    _rate(db, TODAY, 19.90)  # today's rate must not leak into a case dated in March
    case = _case(db, DAY, suffix="approve")
    out = book_on_approve(db, case, actor="pm", override=None, today=TODAY)
    db.flush()
    assert out.source == BOOKED_STORED and out.rate == 18.10 and out.rate_date == DAY
    assert float(case.roe_snapshot) == 18.10
    assert case.fx_booked_source == BOOKED_STORED and case.fx_booked_rate_date == DAY
    assert case.fx_override_reason is None


def test_a_manual_override_needs_a_reason_and_is_audited_on_the_case(db):
    _rate(db, DAY, 18.10)
    case = _case(db, DAY, suffix="override")
    with pytest.raises(FxOverrideReasonRequired):
        book_on_approve(db, case, actor="pm", override=17.80, reason="", today=TODAY)
    out = book_on_approve(db, case, actor="pm", override=17.80, reason="Hedge contract rate", today=TODAY)
    db.flush()
    assert out.source == BOOKED_OVERRIDE and out.stored_rate == 18.10
    assert float(case.roe_snapshot) == 17.80 and case.fx_override_reason == "Hedge contract rate"
    assert case.fx_booked_source == BOOKED_OVERRIDE and case.fx_booked_rate_date is None
    assert float(case.fx_proposed_rate) == 18.10  # proposed and booked stay apart
    assert case.fx_declared_by == "pm" and case.fx_declared_at is not None


def test_the_rate_is_never_revisited_after_the_first_approval(db):
    _rate(db, DAY, 18.10)
    case = _case(db, DAY, suffix="fixed")
    book_on_approve(db, case, actor="pm", override=None, today=TODAY)
    db.add(CporCaseEvent(case_id=case.id, event_type="transition_approve", actor="pm", payload_json={}))
    db.flush()
    # the table is corrected afterwards; the booked case does not move
    db.execute(text("update fx_daily_rate set rate = 18.90 where rate_date = :d"), {"d": DAY})
    out = book_on_approve(db, case, actor="pm", override=None, today=TODAY)
    assert out.source == BOOKED_KEPT and float(case.roe_snapshot) == 18.10
    with pytest.raises(FxRateFixed):
        book_on_approve(db, case, actor="pm", override=19.5, reason="late", today=TODAY)
    assert float(case.roe_snapshot) == 18.10


def test_approval_with_no_stored_rate_and_no_fetch_does_not_block(db):
    import urllib.error

    case = _case(db, DAY, suffix="norate")
    with patch.object(fx_rate, "fetch_frankfurter", side_effect=urllib.error.URLError("down")):
        out = book_on_approve(db, case, actor="pm", override=None, today=TODAY)
    assert out.rate is None and case.roe_snapshot is None
