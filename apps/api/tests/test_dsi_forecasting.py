"""DSI forecasting unit tests (mocked DB — no cip writes)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from app.services.imports import dsi_forecasting as fc


def _velocity_row(
    *,
    product_id: int,
    velocity_52wk: float,
    velocity_4wk: float | None,
    seasonal_index: float = 1.0,
    model_confidence: str = "high",
    computed_through_date: date | None = None,
) -> MagicMock:
    row = MagicMock()
    row.product_id = product_id
    row.velocity_52wk = velocity_52wk
    row.velocity_4wk = velocity_4wk
    row.seasonal_index = seasonal_index
    row.model_confidence = model_confidence
    row.computed_through_date = computed_through_date or date(2024, 6, 30)
    return row


@patch("app.services.imports.dsi_forecasting._table_exists", return_value=True)
@patch("app.services.imports.dsi_forecasting._upsert_forecast_row")
def test_forecast_units_equals_velocity_52wk_times_seasonal(
    mock_upsert: MagicMock,
    _mock_table: MagicMock,
) -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = [
        _velocity_row(product_id=1, velocity_52wk=10.0, velocity_4wk=10.0, seasonal_index=1.5),
    ]
    fc.generate_distributor_forecasts(session, 5, 1, weeks_ahead=1)
    assert mock_upsert.call_count == 1
    assert mock_upsert.call_args.kwargs["forecast_units"] == Decimal("15")


@patch("app.services.imports.dsi_forecasting._table_exists", return_value=True)
@patch("app.services.imports.dsi_forecasting._upsert_forecast_row")
def test_weeks_ahead_13_produces_13_rows_per_product(
    mock_upsert: MagicMock,
    _mock_table: MagicMock,
) -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = [
        _velocity_row(product_id=7, velocity_52wk=5.0, velocity_4wk=5.0),
    ]
    count = fc.generate_distributor_forecasts(session, 5, 1, weeks_ahead=13)
    assert count == 13
    assert mock_upsert.call_count == 13


@patch("app.services.imports.dsi_forecasting._table_exists", return_value=True)
@patch("app.services.imports.dsi_forecasting._upsert_forecast_row")
def test_product_with_zero_velocity_52wk_skipped(
    mock_upsert: MagicMock,
    _mock_table: MagicMock,
) -> None:
    session = MagicMock()
    row_zero = _velocity_row(product_id=1, velocity_52wk=0.0, velocity_4wk=1.0)
    row_ok = _velocity_row(product_id=2, velocity_52wk=10.0, velocity_4wk=9.0)
    session.scalars.return_value.all.return_value = [row_zero, row_ok]
    count = fc.generate_distributor_forecasts(session, 5, 1, weeks_ahead=13)
    assert count == 13
    assert mock_upsert.call_count == 13
    for call in mock_upsert.call_args_list:
        assert call.kwargs["product_id"] == 2


@patch("app.services.imports.dsi_forecasting._table_exists", return_value=True)
def test_low_confidence_rows_excluded_from_input(_mock_table: MagicMock) -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = []
    count = fc.generate_distributor_forecasts(session, 5, 1)
    assert count == 0
    session.scalars.assert_called_once()


@patch("app.services.imports.dsi_forecasting._table_exists", return_value=True)
@patch("app.services.imports.dsi_forecasting._upsert_forecast_row")
def test_upper_and_lower_bands_from_4wk_52wk_ratio(
    mock_upsert: MagicMock,
    _mock_table: MagicMock,
) -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = [
        _velocity_row(product_id=1, velocity_52wk=10.0, velocity_4wk=12.0, seasonal_index=1.0),
    ]
    fc.generate_distributor_forecasts(session, 5, 1, weeks_ahead=1)
    forecast_units = Decimal("10")
    variance_pct = abs(Decimal("12") - Decimal("10")) / Decimal("10")
    assert mock_upsert.call_args.kwargs["upper_band"] == forecast_units * (Decimal("1") + variance_pct)
    assert mock_upsert.call_args.kwargs["lower_band"] == forecast_units * (Decimal("1") - variance_pct)


@patch("app.services.imports.dsi_forecasting._table_exists", return_value=True)
@patch("app.services.imports.dsi_forecasting._upsert_forecast_row")
def test_lower_band_never_negative(
    mock_upsert: MagicMock,
    _mock_table: MagicMock,
) -> None:
    session = MagicMock()
    session.scalars.return_value.all.return_value = [
        _velocity_row(product_id=1, velocity_52wk=2.0, velocity_4wk=20.0, seasonal_index=1.0),
    ]
    fc.generate_distributor_forecasts(session, 5, 1, weeks_ahead=1)
    assert mock_upsert.call_args.kwargs["lower_band"] >= 0


def test_upsert_updates_measures_not_forecast_date() -> None:
    session = MagicMock()
    with patch.object(fc, "pg_insert") as mock_pg_insert:
        ins = MagicMock()
        mock_pg_insert.return_value = ins
        ins.values.return_value = ins
        ins.excluded = MagicMock()
        ins.on_conflict_do_update.return_value = "stmt"
        fc._upsert_forecast_row(
            session,
            distributor_id=1,
            product_id=2,
            forecast_date=date(2024, 7, 7),
            forecast_units=Decimal("5"),
            upper_band=Decimal("6"),
            lower_band=Decimal("4"),
            confidence_level="high",
            velocity_basis="52wk*seasonal",
            import_job_id=9,
        )
        kwargs = ins.on_conflict_do_update.call_args.kwargs
        set_cols = kwargs["set_"]
        assert "forecast_units" in set_cols
        assert "forecast_date" not in set_cols
        assert "distributor_id" not in set_cols
        assert "product_id" not in set_cols
