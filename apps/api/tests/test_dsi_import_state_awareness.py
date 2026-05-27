"""Unit tests for DSI import intelligence state (no cip writes — mocked DB)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.models.ingestion import ImportJob
from app.services.imports.dsi_import_state_awareness import (
    DsiImportIntelligenceState,
    _build_banners,
    _layer_statuses,
    _tier_from_prior_count,
    check_dsi_import_state,
    persist_intelligence_state_on_job,
)


def test_tier_none_when_zero_prior_jobs() -> None:
    assert _tier_from_prior_count(0) == "none"


def test_tier_supervised_when_one_prior_job() -> None:
    assert _tier_from_prior_count(1) == "supervised"


def test_tier_automatic_when_two_or_more_prior_jobs() -> None:
    assert _tier_from_prior_count(2) == "automatic"
    assert _tier_from_prior_count(5) == "automatic"


def test_token_auto_resolution_inactive_when_no_prior_jobs() -> None:
    layers = _layer_statuses(
        prior_applied_job_count=0,
        has_shipment_evidence=True,
        has_cpor_data=True,
        velocity_weeks_available=0,
    )
    assert layers["token_auto_resolution"] == "inactive"


def test_token_auto_resolution_active_when_prior_jobs() -> None:
    layers = _layer_statuses(
        prior_applied_job_count=1,
        has_shipment_evidence=True,
        has_cpor_data=True,
        velocity_weeks_available=0,
    )
    assert layers["token_auto_resolution"] == "active"


def test_soh_reconciliation_degraded_without_shipment() -> None:
    layers = _layer_statuses(
        prior_applied_job_count=0,
        has_shipment_evidence=False,
        has_cpor_data=False,
        velocity_weeks_available=0,
    )
    assert layers["soh_reconciliation"] == "degraded"


def test_forecasting_inactive_initialising_active() -> None:
    assert (
        _layer_statuses(
            prior_applied_job_count=0,
            has_shipment_evidence=False,
            has_cpor_data=False,
            velocity_weeks_available=0,
        )["forecasting"]
        == "inactive"
    )
    assert (
        _layer_statuses(
            prior_applied_job_count=0,
            has_shipment_evidence=False,
            has_cpor_data=False,
            velocity_weeks_available=13,
        )["forecasting"]
        == "initialising"
    )
    assert (
        _layer_statuses(
            prior_applied_job_count=0,
            has_shipment_evidence=False,
            has_cpor_data=False,
            velocity_weeks_available=52,
        )["forecasting"]
        == "active"
    )


def test_banner_no_baseline_when_zero_prior_jobs() -> None:
    banners = _build_banners(
        prior_applied_job_count=0,
        has_shipment_evidence=False,
        has_cpor_data=False,
        velocity_weeks_available=0,
        auto_resolution_tier="none",
        detected_mode="weekly",
    )
    assert any("No baseline data found" in b["message"] for b in banners)


def test_banner_no_shipment_evidence() -> None:
    banners = _build_banners(
        prior_applied_job_count=1,
        has_shipment_evidence=False,
        has_cpor_data=True,
        velocity_weeks_available=0,
        auto_resolution_tier="supervised",
        detected_mode="weekly",
    )
    assert any("Shipment data unavailable" in b["message"] for b in banners)


def test_banner_supervised_first_weekly_after_historical() -> None:
    banners = _build_banners(
        prior_applied_job_count=1,
        has_shipment_evidence=True,
        has_cpor_data=True,
        velocity_weeks_available=2,
        auto_resolution_tier="supervised",
        detected_mode="weekly",
    )
    assert any("Prior steward decisions loaded" in b["message"] for b in banners)


@patch("app.services.imports.dsi_import_state_awareness._count_prior_applied_dsi_jobs")
@patch("app.services.imports.dsi_import_state_awareness._last_applied_period_end")
@patch("app.services.imports.dsi_import_state_awareness._has_shipment_evidence")
@patch("app.services.imports.dsi_import_state_awareness._has_cpor_data")
@patch("app.services.imports.dsi_import_state_awareness._velocity_weeks_available")
def test_check_dsi_import_state_writes_shape(
    mock_velocity: MagicMock,
    mock_cpor: MagicMock,
    mock_ship: MagicMock,
    mock_period: MagicMock,
    mock_prior: MagicMock,
) -> None:
    mock_prior.return_value = (2, 99)
    mock_period.return_value = date(2024, 6, 30)
    mock_ship.return_value = True
    mock_cpor.return_value = False
    mock_velocity.return_value = 13

    session = MagicMock()
    job = MagicMock(spec=ImportJob)
    job.id = 1
    job.source_id = 10
    job.source = MagicMock()
    job.source.id = 10
    job.staged_metadata = {"dsi_workflow_mode": "weekly"}
    session.get.return_value = job

    state = check_dsi_import_state(session, 1, distributor_id=5)
    assert state.auto_resolution_tier == "automatic"
    assert state.detected_mode == "weekly"
    assert state.has_cpor_data is False
    assert state.intelligence_layers["forecasting"] == "initialising"
    assert state.intelligence_layers["pricing_intelligence"] == "degraded"

    persist_intelligence_state_on_job(session, job, state)
    assert "intelligence_state" in (job.staged_metadata or {})
    intel = job.staged_metadata["intelligence_state"]
    assert intel["auto_resolution_tier"] == "automatic"
    assert intel["prior_applied_job_count"] == 2


def test_has_cpor_always_false_until_cpor_import_module_exists() -> None:
    from app.services.imports.dsi_import_state_awareness import _has_cpor_data

    session = MagicMock()
    assert _has_cpor_data(session, None) is False
    assert _has_cpor_data(session, 1) is False
    assert _has_cpor_data(session, 99) is False


@patch("app.services.imports.dsi_import_state_awareness._table_exists", return_value=False)
def test_velocity_zero_when_table_missing(mock_exists: MagicMock) -> None:
    from app.services.imports.dsi_import_state_awareness import _velocity_weeks_available

    session = MagicMock()
    assert _velocity_weeks_available(session, 1) == 0
