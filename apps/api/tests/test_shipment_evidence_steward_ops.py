"""Unit tests for shipment steward batching helpers (no database I/O)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.imports.shipment_evidence_steward_ops import (
    ShipmentStewardOpError,
    _verify_line_scope,
)


def test_verify_line_scope_uses_set_query_not_per_line_get() -> None:
    db = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = [10, 11]
    db.scalars.return_value = scalars_result

    cand = MagicMock()
    cand.import_job_id = 32

    _verify_line_scope(db, cand, [10, 11])

    db.get.assert_not_called()
    assert db.scalars.call_count == 1


def test_verify_line_scope_raises_when_line_missing_from_job() -> None:
    db = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = [10]
    db.scalars.return_value = scalars_result

    cand = MagicMock()
    cand.import_job_id = 32

    with pytest.raises(ShipmentStewardOpError, match="Line 99"):
        _verify_line_scope(db, cand, [10, 99])
