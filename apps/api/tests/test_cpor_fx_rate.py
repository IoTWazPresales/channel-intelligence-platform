"""Unit tests for booked FX lifecycle — no database."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.cpor.fx_rate import (
    BOOKED_EXISTING,
    BOOKED_KEPT,
    BOOKED_OVERRIDE,
    BOOKED_STORED,
    SOURCE_FRANKFURTER,
    SOURCE_LAST_KNOWN,
    SOURCE_OPERATOR,
    FxOverrideReasonRequired,
    FxRateFixed,
    RateQuote,
    apply_create_fx,
    approval_date,
    book_on_approve,
    book_rate,
    case_rate_date,
    confirm_backfill_suggestion,
    declare_fx_mode,
    parse_frankfurter_payload,
    set_proposed,
)

STORED_DATE = date(2026, 9, 1)


def test_parse_frankfurter_payload():
    published, rate = parse_frankfurter_payload(
        {"amount": 1.0, "base": "USD", "date": "2026-09-04", "rates": {"ZAR": 18.12}}
    )
    assert published == date(2026, 9, 4)
    assert abs(rate - 18.12) < 1e-9


def _case(**kwargs):
    defaults = dict(
        status="draft",
        roe_snapshot=None,
        fx_mode="booked",
        fx_declared_at=None,
        fx_declared_by=None,
        fx_proposed_rate=None,
        fx_proposed_at=None,
        fx_proposed_by=None,
        fx_proposed_source=None,
        fx_booked_source=None,
        fx_booked_rate_date=None,
        fx_override_reason=None,
        id=7,
        window_start=date(2026, 9, 1),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_set_proposed_does_not_touch_booked_columns():
    case = _case(roe_snapshot=18.5, fx_declared_by="import")
    assert set_proposed(case, 19.1, "warren", source=SOURCE_OPERATOR) is True
    assert float(case.fx_proposed_rate) == 19.1
    assert case.fx_proposed_by == "warren"
    assert case.fx_proposed_source == SOURCE_OPERATOR
    assert float(case.roe_snapshot) == 18.5
    assert case.fx_declared_by == "import"


def test_book_rate_does_not_overwrite_proposed():
    case = _case()
    set_proposed(case, 18.0, "create", source=SOURCE_FRANKFURTER)
    proposed_at = case.fx_proposed_at
    assert book_rate(case, 18.4, "pm") is True
    assert float(case.roe_snapshot) == 18.4
    assert case.fx_declared_by == "pm"
    assert float(case.fx_proposed_rate) == 18.0
    assert case.fx_proposed_by == "create"
    assert case.fx_proposed_at == proposed_at
    assert case.fx_mode == "booked"


def _stored(rate=18.22, rate_date=STORED_DATE):
    return RateQuote(rate=rate, rate_date=rate_date, source=SOURCE_FRANKFURTER, is_fallback=False)


def _failed():
    return RateQuote(None, None, "fetch_failed", True, fetch_failed=True)


def _approve(case, *, override=None, reason=None, quote=None, prior=False):
    quote = quote if quote is not None else _stored()
    with patch("app.services.cpor.fx_rate.rate_for_case_date", return_value=quote), patch(
        "app.services.cpor.fx_rate.has_prior_approval", return_value=prior
    ):
        return book_on_approve(
            MagicMock(), case, actor="pm", override=override, reason=reason, today=date(2026, 10, 15)
        )


def test_book_on_approve_books_the_stored_rate_for_the_case_date():
    case = _case(fx_proposed_rate=18.1)
    out = _approve(case)
    assert out.rate == 18.22 and out.source == BOOKED_STORED and out.rate_date == STORED_DATE
    assert float(case.roe_snapshot) == 18.22
    assert case.fx_booked_source == BOOKED_STORED and case.fx_booked_rate_date == STORED_DATE
    assert case.fx_override_reason is None
    assert float(case.fx_proposed_rate) == 18.1  # proposed kept apart from booked


def test_book_on_approve_override_needs_a_reason():
    case = _case(fx_proposed_rate=18.1)
    with pytest.raises(FxOverrideReasonRequired):
        _approve(case, override=18.3, reason="  ")
    assert case.roe_snapshot is None


def test_book_on_approve_override_is_recorded_as_manual_with_its_reason():
    case = _case()
    out = _approve(case, override=18.3, reason="Treasury forward rate")
    assert out.source == BOOKED_OVERRIDE and out.reason == "Treasury forward rate"
    assert out.stored_rate == 18.22 and out.stored_rate_date == STORED_DATE
    assert float(case.roe_snapshot) == 18.3
    assert case.fx_booked_source == BOOKED_OVERRIDE
    assert case.fx_override_reason == "Treasury forward rate"
    assert float(case.fx_proposed_rate) == 18.22  # proposed holds the stored rate, booked the override


def test_book_on_approve_override_equal_to_stored_is_not_an_override():
    case = _case()
    out = _approve(case, override=18.22)
    assert out.source == BOOKED_STORED and case.fx_override_reason is None


def test_book_on_approve_keeps_a_rate_the_operator_chose_at_create():
    case = _case(
        roe_snapshot=18.5,
        fx_booked_source=BOOKED_OVERRIDE,
        fx_override_reason="Rate entered when the case was created",
    )
    out = _approve(case)
    assert out.source == BOOKED_OVERRIDE and float(case.roe_snapshot) == 18.5


def test_book_on_approve_keeps_a_legacy_rate():
    case = _case(roe_snapshot=16.5)
    out = _approve(case)
    assert out.source == BOOKED_EXISTING and float(case.roe_snapshot) == 16.5


def test_book_on_approve_replaces_a_draft_stored_rate_with_the_rate_for_the_date():
    case = _case(roe_snapshot=18.0, fx_booked_source=BOOKED_STORED, fx_booked_rate_date=date(2026, 8, 20))
    out = _approve(case)
    assert float(case.roe_snapshot) == 18.22 and out.source == BOOKED_STORED


def test_book_on_approve_without_any_rate_is_noop_and_does_not_block():
    case = _case()
    out = _approve(case, quote=_failed())
    assert out.rate is None and "no_rate" in out.notes
    assert case.roe_snapshot is None and case.fx_declared_at is None


def test_book_on_approve_falls_back_to_a_proposed_rate_as_an_override():
    case = _case(fx_proposed_rate=18.1, fx_proposed_by="warren")
    out = _approve(case, quote=_failed())
    assert out.source == BOOKED_OVERRIDE and float(case.roe_snapshot) == 18.1
    assert "warren" in (case.fx_override_reason or "")


def test_reapproval_keeps_the_fixed_rate():
    case = _case(roe_snapshot=18.22, fx_booked_source=BOOKED_STORED, fx_booked_rate_date=STORED_DATE)
    out = _approve(case, prior=True, quote=_stored(19.5))
    assert out.source == BOOKED_KEPT and float(case.roe_snapshot) == 18.22


def test_reapproval_refuses_a_different_rate():
    case = _case(roe_snapshot=18.22, fx_booked_source=BOOKED_STORED)
    with pytest.raises(FxRateFixed):
        _approve(case, prior=True, override=19.0, reason="because")
    assert float(case.roe_snapshot) == 18.22


def test_case_rate_date_is_the_approval_date_never_the_window_start():
    # D-0093: the FX date is the approval date. Not the window start, past or future.
    today = date(2026, 10, 15)
    assert case_rate_date(today) == today


def test_book_on_approve_asks_for_the_rate_on_the_approval_date_not_the_window_start():
    today = date(2026, 10, 15)
    case = _case(window_start=date(2026, 9, 1))
    with patch("app.services.cpor.fx_rate.rate_for_case_date", return_value=_stored()) as ask, patch(
        "app.services.cpor.fx_rate.has_prior_approval", return_value=False
    ):
        book_on_approve(MagicMock(), case, actor="pm", override=None, today=today)
    assert ask.call_args.args[1] == today
    assert case.window_start == date(2026, 9, 1)


def test_apply_create_fx_asks_for_the_rate_on_todays_date_not_the_window_start():
    today = date(2026, 10, 15)
    case = _case(fx_mode=None, window_start=date(2026, 9, 1))
    with patch("app.services.cpor.fx_rate._utc_today", return_value=today), patch(
        "app.services.cpor.fx_rate.rate_for_case_date", return_value=_stored()
    ) as ask:
        apply_create_fx(MagicMock(), case, actor="pm", proposed_override=None, explicit_roe=None)
    assert ask.call_args.args[1] == today


def test_approval_date_of_an_unapproved_case_is_today_whatever_its_window():
    today = date(2026, 10, 15)
    for window in (date(2026, 9, 1), date(2026, 12, 1), None):
        case = _case(status="proposed", window_start=window)
        assert approval_date(MagicMock(), case, today) == today


def test_approval_date_of_an_approved_case_is_its_first_approval_event_not_its_window():
    today = date(2026, 10, 15)
    session = MagicMock()
    session.scalar.return_value = datetime(2026, 9, 10, 23, 30, tzinfo=timezone.utc)
    case = _case(status="ended", window_start=date(2026, 8, 1))
    assert approval_date(session, case, today) == date(2026, 9, 10)
    session.scalar.return_value = None
    case.decided_at = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
    assert approval_date(session, case, today) == date(2026, 9, 12)


def test_confirm_backfill_draft_does_not_book():
    case = _case(status="draft")
    out = confirm_backfill_suggestion(case, 17.9, "warren", source=SOURCE_LAST_KNOWN)
    assert out["ok"] is True
    assert out["booked"] is False
    assert float(case.fx_proposed_rate) == 17.9
    assert case.roe_snapshot is None


def test_confirm_backfill_ended_books_and_keeps_proposed():
    case = _case(status="ended")
    out = confirm_backfill_suggestion(case, 17.4, "warren")
    assert out["ok"] is True
    assert out["booked"] is True
    assert float(case.fx_proposed_rate) == 17.4
    assert float(case.roe_snapshot) == 17.4
    assert case.fx_declared_by == "warren"


def test_confirm_backfill_ended_preserves_existing_proposed():
    case = _case(status="ended", fx_proposed_rate=16.0, fx_proposed_by="create")
    out = confirm_backfill_suggestion(case, 17.4, "warren")
    assert out["ok"] is True
    assert float(case.fx_proposed_rate) == 16.0
    assert case.fx_proposed_by == "create"
    assert float(case.roe_snapshot) == 17.4


def test_confirm_already_declared_refuses():
    case = _case(status="ended", roe_snapshot=18.0)
    out = confirm_backfill_suggestion(case, 19.0, "warren")
    assert out["ok"] is False
    assert out["reason"] == "already_declared"
    assert float(case.roe_snapshot) == 18.0


def _create(case, quote, *, override=None, explicit=None, actor="warren"):
    with patch("app.services.cpor.fx_rate.rate_for_case_date", return_value=quote):
        apply_create_fx(MagicMock(), case, actor=actor, proposed_override=override, explicit_roe=explicit)


def test_apply_create_fx_books_the_stored_rate_for_the_case_date():
    case = _case(fx_mode=None)
    _create(case, _stored())
    assert case.fx_mode == "booked"
    assert float(case.fx_proposed_rate) == 18.22
    assert float(case.roe_snapshot) == 18.22
    assert case.fx_booked_source == BOOKED_STORED and case.fx_booked_rate_date == STORED_DATE
    assert case.fx_declared_by == "warren"


def test_apply_create_fx_a_different_rate_is_a_manual_override():
    case = _case(fx_mode=None)
    _create(case, _stored(), override=18.5)
    assert float(case.fx_proposed_rate) == 18.22  # proposed keeps the stored rate
    assert case.fx_proposed_source == SOURCE_FRANKFURTER
    assert float(case.roe_snapshot) == 18.5
    assert case.fx_booked_source == BOOKED_OVERRIDE and case.fx_override_reason


def test_apply_create_fx_the_stored_rate_typed_back_is_not_an_override():
    case = _case(fx_mode=None)
    _create(case, _stored(), override=18.22)
    assert case.fx_booked_source == BOOKED_STORED and case.fx_override_reason is None


def test_apply_create_fx_fetch_fail_stays_unbooked_without_last_known():
    case = _case(fx_mode="booked", roe_snapshot=None)
    _create(case, RateQuote(18.01, None, SOURCE_LAST_KNOWN, True, fetch_failed=True))
    assert case.roe_snapshot is None
    assert case.fx_mode is None
    assert case.fx_proposed_rate is None
    assert case.fx_proposed_source == "fetch_failed"
    assert case.fx_booked_source is None


def test_apply_create_fx_operator_rate_with_no_stored_rate_is_an_override():
    case = _case(fx_mode=None)
    _create(case, _failed(), override=18.5)
    assert float(case.roe_snapshot) == 18.5
    assert case.fx_booked_source == BOOKED_OVERRIDE
    assert float(case.fx_proposed_rate) == 18.5 and case.fx_proposed_source == SOURCE_OPERATOR


def test_apply_create_fx_explicit_roe_stays_declared():
    case = _case(roe_snapshot=18.49)
    _create(case, _stored(), explicit=18.49, actor="import")
    assert float(case.roe_snapshot) == 18.49
    assert case.fx_declared_by == "import"
    assert float(case.fx_proposed_rate) == 18.22
    assert case.fx_booked_source == BOOKED_OVERRIDE


def test_daily_fx_beat_entry_is_crontab():
    from celery.schedules import crontab

    from app.worker.celery_app import build_beat_schedule

    spec = build_beat_schedule()["cpor-fetch-daily-fx-rate"]
    assert spec["task"] == "cpor.fetch_daily_fx_rate"
    assert isinstance(spec["schedule"], crontab)


def test_fx_rate_poll_disabled_under_pytest():
    from app.services.cpor.fx_rate_poller import fx_rate_poll_enabled

    assert fx_rate_poll_enabled() is False


def test_fx_today_endpoint_mocked():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.services.cpor.fx_rate import RateQuote

    quote = RateQuote(
        rate=18.22,
        rate_date=date(2026, 9, 4),
        source="frankfurter.ecb",
        is_fallback=False,
    )
    session = MagicMock()
    client = TestClient(app)
    with patch("app.api.v1.endpoints.cpor_fx.SessionLocal") as SL:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        with patch("app.api.v1.endpoints.cpor_fx.ensure_today_rate", return_value=quote):
            r = client.get("/api/v1/cpor/fx/rates/today")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rate"] == 18.22
    assert body["source"] == "frankfurter.ecb"
    assert body["is_fallback"] is False
    session.commit.assert_called_once()


def test_declare_fx_mode_does_not_touch_rate():
    case = _case(roe_snapshot=16.5, fx_mode=None, fx_declared_at=None, fx_declared_by="import")
    out = declare_fx_mode(case, "booked", "warren")
    assert out["ok"] is True
    assert out["skipped"] is False
    assert case.fx_mode == "booked"
    assert float(case.roe_snapshot) == 16.5
    assert case.fx_declared_by == "warren"


def test_declare_fx_mode_refuses_without_rate():
    case = _case(roe_snapshot=None, fx_mode=None)
    out = declare_fx_mode(case, "booked", "warren")
    assert out["ok"] is False
    assert out["reason"] == "rate_missing"
    assert case.fx_mode is None


def test_declare_fx_mode_skips_when_already_booked():
    case = _case(roe_snapshot=18.0, fx_mode="booked")
    out = declare_fx_mode(case, "booked", "warren")
    assert out["ok"] is True
    assert out["skipped"] is True
    assert case.fx_declared_by is None


def test_declare_mode_endpoint_requires_confirm():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    r = client.post("/api/v1/cpor/fx/declare-mode", json={"confirm": False, "mode": "booked"})
    assert r.status_code == 400
    assert "never auto" in r.json()["detail"]


def _approve_request(book, body=None):
    """POST approve with the session and side effects mocked. Returns (response, case, record_event)."""
    from fastapi.testclient import TestClient

    from app.main import app

    case = SimpleNamespace(
        id=10,
        tenant_id=None,
        status="proposed",
        workflow_status="pending_approval",
        customer_id=1,
        case_code="X",
        export_version=1,
        needs_reapproval=False,
        roe_snapshot=None,
        fx_mode="booked",
        window_start=date(2026, 9, 1),
        last_comment=None,
        submitted_at=None,
        decided_at=None,
        decided_by=None,
    )
    session = MagicMock()
    session.get = MagicMock(return_value=case)
    ep = "app.api.v1.endpoints.cpor_cases"
    br = "app.services.cpor.budget_reapproval"
    with patch(f"{ep}.SessionLocal") as SL, patch(f"{ep}._record_event") as record, patch(
        f"{ep}._run_drift_check", return_value=[]
    ), patch(f"{ep}.book_on_approve", book), patch(f"{ep}._case_json", return_value={}), patch(
        f"{ep}._products_map", return_value={}
    ), patch(f"{ep}.tenant_profile_hard_enforce", return_value=False), patch(
        f"{br}.evaluate_money_position", return_value={}
    ), patch(f"{br}.apply_reapproval_flag"):
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        r = TestClient(app).post(
            "/api/v1/cpor/cases/10/transition", json={"action": "approve", **(body or {})}
        )
    return r, case, record, session


def test_approve_records_how_the_rate_was_booked():
    from app.services.cpor.fx_rate import BookOutcome

    book = MagicMock(
        return_value=BookOutcome(rate=18.22, source=BOOKED_STORED, rate_date=STORED_DATE, stored_rate=18.22, stored_rate_date=STORED_DATE)
    )
    r, _case_obj, record, _session = _approve_request(book)
    assert r.status_code == 200, r.text
    events = [c.kwargs for c in record.call_args_list]
    booked = [e for e in events if e["event_type"] == "fx_booked"]
    assert len(booked) == 1
    assert booked[0]["payload"]["source"] == BOOKED_STORED
    assert booked[0]["payload"]["rate"] == 18.22
    assert booked[0]["payload"]["rate_date"] == STORED_DATE.isoformat()


def test_approve_with_an_override_and_no_reason_is_refused():
    book = MagicMock(side_effect=FxOverrideReasonRequired("needs a reason"))
    r, _case_obj, record, _session = _approve_request(book, {"fx_rate": 17.5})
    assert r.status_code == 400 and "reason" in r.json()["detail"]
    assert not [c for c in record.call_args_list if c.kwargs["event_type"] == "transition_approve"]


def test_approve_passes_the_reason_through():
    from app.services.cpor.fx_rate import BookOutcome

    book = MagicMock(return_value=BookOutcome(rate=17.5, source=BOOKED_OVERRIDE, reason="hedge"))
    r, _case_obj, _record, _session = _approve_request(book, {"fx_rate": 17.5, "fx_rate_reason": "hedge"})
    assert r.status_code == 200, r.text
    assert book.call_args.kwargs["override"] == 17.5 and book.call_args.kwargs["reason"] == "hedge"


def test_reapproval_with_a_new_rate_is_refused_as_fixed():
    book = MagicMock(side_effect=FxRateFixed("fixed at first approval"))
    r, _case_obj, _record, _session = _approve_request(book, {"fx_rate": 19.0, "fx_rate_reason": "late"})
    assert r.status_code == 409
