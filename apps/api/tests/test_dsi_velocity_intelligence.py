"""DSI velocity intelligence unit tests (mocked DB — no cip writes)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.imports import dsi_velocity_intelligence as vel


def _txn_rows(
    *,
    anchor: date,
    units_per_day: Decimal = Decimal("7"),
    span_days: int = 400,
) -> list[tuple[date, Decimal]]:
    rows: list[tuple[date, Decimal]] = []
    for offset in range(span_days):
        d = anchor - timedelta(days=offset)
        rows.append((d, units_per_day))
    return rows


def test_velocity_4wk_sum_last_28_days_divided_by_4() -> None:
    anchor = date(2024, 6, 30)
    rows = _txn_rows(anchor=anchor, units_per_day=Decimal("4"), span_days=30)
    total = vel._sum_units_in_window(rows, anchor=anchor, window_days=28)
    assert total == Decimal("112")
    assert total / Decimal("4") == Decimal("28")


def test_velocity_13wk_uses_91_day_window() -> None:
    anchor = date(2024, 12, 31)
    rows = _txn_rows(anchor=anchor, units_per_day=Decimal("1"), span_days=100)
    total = vel._sum_units_in_window(rows, anchor=anchor, window_days=91)
    assert total == Decimal("91")
    assert total / Decimal("13") == Decimal("7")


def test_velocity_52wk_uses_364_day_window() -> None:
    anchor = date(2024, 12, 31)
    rows = _txn_rows(anchor=anchor, units_per_day=Decimal("2"), span_days=370)
    total = vel._sum_units_in_window(rows, anchor=anchor, window_days=364)
    assert total == Decimal("728")
    assert total / Decimal("52") == Decimal("14")


def test_model_confidence_high_at_52_distinct_weeks() -> None:
    anchor = date(2024, 12, 31)
    rows: list[tuple[date, Decimal]] = []
    for week in range(52):
        rows.append((anchor - timedelta(days=week * 7), Decimal("1")))
    assert vel._distinct_iso_weeks(rows) >= 52
    assert vel._model_confidence(vel._distinct_iso_weeks(rows)) == "high"


def test_model_confidence_medium_between_26_and_51_weeks() -> None:
    anchor = date(2024, 12, 31)
    rows = [(anchor - timedelta(days=week * 7), Decimal("1")) for week in range(30)]
    weeks = vel._distinct_iso_weeks(rows)
    assert 26 <= weeks < 52
    assert vel._model_confidence(weeks) == "medium"


def test_model_confidence_low_below_26_weeks() -> None:
    rows = [(date(2024, 6, 1), Decimal("1")), (date(2024, 6, 8), Decimal("1"))]
    weeks = vel._distinct_iso_weeks(rows)
    assert weeks < 26
    assert vel._model_confidence(weeks) == "low"


def test_seasonal_index_one_when_fewer_than_two_calendar_years() -> None:
    rows = [
        (date(2024, 1, 1), Decimal("10")),
        (date(2024, 2, 1), Decimal("20")),
    ]
    assert vel._seasonal_index(rows) == Decimal("1.0")


def test_upsert_updates_measures_not_identity_columns() -> None:
    session = MagicMock()
    with patch.object(vel, "pg_insert") as mock_pg_insert:
        ins = MagicMock()
        mock_pg_insert.return_value = ins
        ins.values.return_value = ins
        excluded = MagicMock()
        excluded.velocity_4wk = "excluded.velocity_4wk"
        ins.excluded = excluded
        ins.on_conflict_do_update.return_value = "stmt"
        vel._upsert_velocity_row(
            session,
            distributor_id=1,
            product_id=2,
            customer_id=3,
            computed_through_date=date(2024, 6, 30),
            velocity_4wk=Decimal("1"),
            velocity_13wk=Decimal("2"),
            velocity_52wk=Decimal("3"),
            seasonal_index=Decimal("1.0"),
            model_confidence="medium",
            import_job_id=99,
        )
        ins.on_conflict_do_update.assert_called_once()
        kwargs = ins.on_conflict_do_update.call_args.kwargs
        assert "source_key" in str(kwargs.get("index_elements", "")) or kwargs.get("index_elements")
        set_cols = kwargs["set_"]
        assert "velocity_4wk" in set_cols
        assert "distributor_id" not in set_cols
        assert "product_id" not in set_cols
        assert "customer_id" not in set_cols


@patch("app.services.imports.dsi_velocity_intelligence._table_exists", return_value=True)
@patch("app.services.imports.dsi_velocity_intelligence._upsert_velocity_row")
def test_product_with_zero_velocity_52wk_still_upserts_row(
    mock_upsert: MagicMock,
    _mock_table: MagicMock,
) -> None:
    anchor = date(2024, 6, 30)
    session = MagicMock()
    session.scalar.return_value = anchor
    session.execute.return_value.all.return_value = [
        (10, 20, anchor, Decimal("0")),
    ]
    count = vel.compute_distributor_velocity(session, 5, 1)
    assert count == 1
    mock_upsert.assert_called_once()
    assert mock_upsert.call_args.kwargs["velocity_52wk"] is None

