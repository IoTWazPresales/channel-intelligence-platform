"""Weekly DSI auto-resolution tier behaviour (mocked DB)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.models.ingestion import ImportJob
from app.services.imports.dsi_customer_intelligence import HistoricalCustomerResolution
from app.services.imports.dsi_weekly_auto_resolution import (
    EntityAutoResolutionResult,
    check_customer_auto_resolution_at_validate,
    intelligence_tier_from_job,
    weekly_auto_resolution_active,
)


def _weekly_job(*, tier: str = "supervised") -> MagicMock:
    job = MagicMock(spec=ImportJob)
    job.id = 100
    job.staged_metadata = {
        "dsi_workflow_mode": "weekly",
        "intelligence_state": {"auto_resolution_tier": tier},
    }
    return job


def _historical_job() -> MagicMock:
    job = MagicMock(spec=ImportJob)
    job.id = 101
    job.staged_metadata = {
        "dsi_workflow_mode": "historical",
        "dsi_historical_product_eligibility_relaxed": True,
        "intelligence_state": {"auto_resolution_tier": "automatic"},
    }
    return job


def test_weekly_auto_inactive_for_historical_mode() -> None:
    assert weekly_auto_resolution_active(_historical_job()) is False


def test_tier_none_from_intelligence_state() -> None:
    job = _weekly_job(tier="none")
    assert intelligence_tier_from_job(job) == "none"


@patch("app.services.imports.dsi_weekly_auto_resolution.lookup_historical_customer_resolution")
def test_tier_none_returns_no_auto(mock_lookup: MagicMock) -> None:
    mock_lookup.return_value = None
    job = _weekly_job(tier="none")
    session = MagicMock()
    out = check_customer_auto_resolution_at_validate(
        session,
        job=job,
        source_definition_id=1,
        distributor_id=5,
        normalized_key="acme",
        customer_raw="Acme",
        dealer_group_raw=None,
        historical_index={},
    )
    assert out.outcome == "none"


@patch("app.services.imports.dsi_weekly_auto_resolution.lookup_historical_customer_resolution")
def test_tier_supervised_does_not_auto_resolve_at_validate(mock_lookup: MagicMock) -> None:
    mock_lookup.return_value = HistoricalCustomerResolution(
        customer_id=42,
        import_job_id=9,
        match_reason="steward_map_existing_customer",
        confidence=0.94,
        resolution_kind="historical_steward",
    )
    job = _weekly_job(tier="supervised")
    session = MagicMock()
    out = check_customer_auto_resolution_at_validate(
        session,
        job=job,
        source_definition_id=1,
        distributor_id=5,
        normalized_key="acme",
        customer_raw="Acme",
        dealer_group_raw=None,
        historical_index={(5, "acme"): mock_lookup.return_value},
    )
    assert out.outcome == "none"


@patch("app.services.imports.dsi_weekly_auto_resolution._prior_resolved_entity_ids")
@patch("app.services.imports.dsi_weekly_auto_resolution.lookup_historical_customer_resolution")
def test_tier_automatic_consistent_prior_resolves(
    mock_lookup: MagicMock,
    mock_priors: MagicMock,
) -> None:
    mock_lookup.return_value = HistoricalCustomerResolution(
        customer_id=42,
        import_job_id=9,
        match_reason="steward_map_existing_customer",
        confidence=0.94,
        resolution_kind="historical_steward",
    )
    mock_priors.return_value = [(8, 42, 5), (7, 42, 5)]
    job = _weekly_job(tier="automatic")
    session = MagicMock()
    out = check_customer_auto_resolution_at_validate(
        session,
        job=job,
        source_definition_id=1,
        distributor_id=5,
        normalized_key="acme",
        customer_raw="Acme",
        dealer_group_raw=None,
        historical_index={(5, "acme"): mock_lookup.return_value},
    )
    assert out.outcome == "resolved"
    assert out.entity_id == 42


@patch("app.services.imports.dsi_weekly_auto_resolution._prior_resolved_entity_ids")
@patch("app.services.imports.dsi_weekly_auto_resolution.lookup_historical_customer_resolution")
def test_tier_automatic_inconsistent_prior_conflicts(
    mock_lookup: MagicMock,
    mock_priors: MagicMock,
) -> None:
    mock_lookup.return_value = HistoricalCustomerResolution(
        customer_id=42,
        import_job_id=9,
        match_reason="steward_map_existing_customer",
        confidence=0.94,
        resolution_kind="historical_steward",
    )
    mock_priors.return_value = [(8, 42, 5), (7, 99, 5)]
    job = _weekly_job(tier="automatic")
    session = MagicMock()
    out = check_customer_auto_resolution_at_validate(
        session,
        job=job,
        source_definition_id=1,
        distributor_id=5,
        normalized_key="acme",
        customer_raw="Acme",
        dealer_group_raw=None,
        historical_index={(5, "acme"): mock_lookup.return_value},
    )
    assert out.outcome == "conflict"
    assert out.conflict_prior is not None


def test_distributor_scoped_lookup_precedence() -> None:
    from app.services.imports.dsi_customer_intelligence import lookup_historical_customer_resolution

    index = {
        (5, "token"): HistoricalCustomerResolution(
            customer_id=1,
            import_job_id=1,
            match_reason=None,
            confidence=0.9,
            resolution_kind="historical_steward",
        ),
        (None, "token"): HistoricalCustomerResolution(
            customer_id=2,
            import_job_id=2,
            match_reason=None,
            confidence=0.8,
            resolution_kind="historical_steward",
        ),
    }
    hit = lookup_historical_customer_resolution(
        index,
        distributor_id=5,
        normalized_key="token",
        customer_raw=None,
        dealer_group_raw=None,
    )
    assert hit is not None
    assert hit.customer_id == 1
