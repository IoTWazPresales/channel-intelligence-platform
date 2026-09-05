"""Unit tests for booked FX lifecycle — no database."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.cpor.fx_rate import (
    SOURCE_FRANKFURTER,
    SOURCE_LAST_KNOWN,
    SOURCE_OPERATOR,
    apply_create_fx,
    book_on_approve,
    book_rate,
    confirm_backfill_suggestion,
    parse_frankfurter_payload,
    set_proposed,
)


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


def test_book_on_approve_prefers_override_then_proposed():
    case = _case(fx_proposed_rate=18.1)
    booked = book_on_approve(case, actor="pm", override=18.3)
    assert booked == 18.3
    assert float(case.roe_snapshot) == 18.3
    assert float(case.fx_proposed_rate) == 18.1


def test_book_on_approve_without_rate_is_noop():
    case = _case()
    assert book_on_approve(case, actor="pm", override=None) is None
    assert case.roe_snapshot is None
    assert case.fx_declared_at is None


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


def test_apply_create_fx_does_not_declare_suggestion():
    case = _case(fx_mode=None)
    session = MagicMock()
    quote = SimpleNamespace(rate=18.22, is_fallback=False, source=SOURCE_FRANKFURTER)
    with patch("app.services.cpor.fx_rate.ensure_today_rate", return_value=quote):
        apply_create_fx(session, case, actor="warren", proposed_override=None, explicit_roe=None)
    assert case.fx_mode == "booked"
    assert float(case.fx_proposed_rate) == 18.22
    assert case.roe_snapshot is None
    assert case.fx_declared_at is None


def test_apply_create_fx_operator_override_source():
    case = _case()
    session = MagicMock()
    quote = SimpleNamespace(rate=18.22, is_fallback=False, source=SOURCE_FRANKFURTER)
    with patch("app.services.cpor.fx_rate.ensure_today_rate", return_value=quote):
        apply_create_fx(session, case, actor="warren", proposed_override=18.5, explicit_roe=None)
    assert float(case.fx_proposed_rate) == 18.5
    assert case.fx_proposed_source == SOURCE_OPERATOR
    assert case.roe_snapshot is None


def test_apply_create_fx_explicit_roe_stays_declared():
    case = _case(roe_snapshot=18.49)
    session = MagicMock()
    quote = SimpleNamespace(rate=18.22, is_fallback=False, source=SOURCE_FRANKFURTER)
    with patch("app.services.cpor.fx_rate.ensure_today_rate", return_value=quote):
        apply_create_fx(session, case, actor="import", proposed_override=None, explicit_roe=18.49)
    assert float(case.roe_snapshot) == 18.49
    assert case.fx_declared_by == "import"
    assert case.fx_proposed_rate is not None


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
