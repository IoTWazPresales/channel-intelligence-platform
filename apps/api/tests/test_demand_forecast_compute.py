"""Unit 15B — velocity tenant_id must never be NULL (mocked; no cip writes)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from app.services.demand_forecast.compute_from_history import compute_from_history
from app.services.demand_forecast.velocity_compute import (
    generate_velocity_demand_forecasts,
    resolve_forecast_tenant_id,
)


def test_resolve_forecast_tenant_id_never_none():
    assert resolve_forecast_tenant_id(None) == "default"
    assert resolve_forecast_tenant_id("") == "default"
    assert resolve_forecast_tenant_id("  ") == "default"
    assert resolve_forecast_tenant_id("acme") == "acme"


@patch("app.services.demand_forecast.velocity_compute._table_exists", return_value=True)
@patch("app.services.demand_forecast.velocity_compute.pg_insert")
def test_velocity_inserts_default_tenant_not_none(mock_insert: MagicMock, _exists: MagicMock):
    session = MagicMock()
    row = MagicMock()
    row.velocity_52wk = 10
    row.seasonal_index = 1
    row.velocity_4wk = None
    row.model_confidence = "high"
    row.computed_through_date = date(2026, 1, 1)
    row.distributor_id = 1
    row.product_id = 2
    row.customer_id = 3
    session.scalars.return_value.all.return_value = [row]
    ov = MagicMock()
    ov.all.return_value = []
    ins = MagicMock()
    ins.rowcount = 1
    session.execute.side_effect = [ov, ins]

    chain = MagicMock()
    mock_insert.return_value.values.return_value = chain
    chain.on_conflict_do_update.return_value = chain

    generate_velocity_demand_forecasts(session, weeks_ahead=1)

    kwargs = mock_insert.return_value.values.call_args.kwargs
    assert kwargs["tenant_id"] == "default"
    assert kwargs["tenant_id"] is not None
    assert kwargs["method"] == "velocity"
    assert kwargs["velocity_basis"] == "52wk*seasonal"


@patch("app.services.demand_forecast.compute_from_history.generate_analogue_demand_forecasts")
@patch("app.services.demand_forecast.compute_from_history.generate_velocity_demand_forecasts")
def test_compute_from_history_passes_tenant_and_skip_overrides(
    mock_vel: MagicMock, mock_an: MagicMock
):
    mock_vel.return_value = {"upserted": 2, "skipped_override": 1, "considered": 3, "skipped_no_velocity": 0}
    mock_an.return_value = {"upserted": 1, "skipped_override": 0, "considered": 1}
    session = MagicMock()
    out = compute_from_history(session, tenant_id=None, weeks_ahead=13)
    assert out["tenant_id"] == "default"
    assert out["skip_overrides"] is True
    assert out["never_merges_actuals"] is True
    assert out["contract_table"] == "fact_demand_forecast"
    assert mock_vel.call_args.kwargs["tenant_id"] == "default"
    assert mock_vel.call_args.kwargs["skip_overrides"] is True
    assert mock_an.call_args.kwargs["tenant_id"] == "default"
    assert mock_an.call_args.kwargs["skip_overrides"] is True
    # Orchestrator must not touch sell-out / inventory tables
    session.execute.assert_not_called()
