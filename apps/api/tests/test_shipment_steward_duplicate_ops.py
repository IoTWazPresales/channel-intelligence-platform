"""Shipment steward duplicate-review ops (customer tokens)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.imports.dsi_customer_intelligence import (
    build_duplicate_review_record,
    duplicate_review_decision,
)
from app.services.imports.shipment_evidence_steward_ops import ShipmentStewardOpError
from app.services.imports.shipment_steward_duplicate_ops import (
    execute_acknowledge_shipment_duplicate_different_entity,
    execute_acknowledge_shipment_duplicate_same_entity,
)


def _cand(
    *,
    ctx: dict,
    status: str = "needs_review",
    cand_id: int = 1,
    normalized_key: str = "acme",
    entity_type: str = "shipment_customer_token",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=cand_id,
        import_job_id=10,
        entity_type=entity_type,
        normalized_key=normalized_key,
        status=status,
        context=ctx,
        match_reason=None,
    )


def test_different_entity_stamps_review_and_acknowledged_unique() -> None:
    peer = _cand(ctx={}, cand_id=2, normalized_key="acme2")
    cand = _cand(ctx={"possible_duplicate_of": ["acme2"]})
    session = MagicMock()
    session.scalar.return_value = peer

    out = execute_acknowledge_shipment_duplicate_different_entity(
        session, cand, peer_normalized_key="acme2"
    )

    assert out["ok"] is True
    assert cand.status == "acknowledged_unique"
    assert duplicate_review_decision(cand.context) == "different_entity"
    assert cand.context["duplicate_review"]["paired_normalized_key"] == "acme2"
    session.commit.assert_called_once()


def test_same_entity_stamps_review_keeps_status() -> None:
    peer = _cand(ctx={}, cand_id=2, normalized_key="acme2")
    cand = _cand(ctx={"possible_duplicate_of": [{"normalized_key": "acme2", "similarity_score": 0.9}]})
    session = MagicMock()
    session.scalar.return_value = peer

    out = execute_acknowledge_shipment_duplicate_same_entity(session, cand, peer_normalized_key="acme2")

    assert out["ok"] is True
    assert cand.status == "needs_review"
    assert duplicate_review_decision(cand.context) == "same_entity"
    session.commit.assert_called_once()


def test_rejects_when_already_reviewed() -> None:
    cand = _cand(
        ctx={
            "possible_duplicate_of": ["acme2"],
            "duplicate_review": build_duplicate_review_record(
                decision="different_entity",
                paired_normalized_key="acme2",
                similarity_score=None,
            ),
        },
        status="acknowledged_unique",
    )
    session = MagicMock()
    with pytest.raises(ShipmentStewardOpError, match="already recorded"):
        execute_acknowledge_shipment_duplicate_different_entity(
            session, cand, peer_normalized_key="acme2"
        )


def test_rejects_non_customer_entity() -> None:
    cand = _cand(ctx={"possible_duplicate_of": ["x"]}, entity_type="shipment_distributor")
    session = MagicMock()
    with pytest.raises(ShipmentStewardOpError, match="Not shipment_customer_token"):
        execute_acknowledge_shipment_duplicate_same_entity(session, cand, peer_normalized_key="x")
