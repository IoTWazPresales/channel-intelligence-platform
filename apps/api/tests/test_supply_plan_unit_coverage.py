"""Plan-unit PO coverage is a derived ratio, not a stored fact."""
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from app.services.supply_overview import shape_plan_unit_po_coverage, supply_overview


def test_shape_counts_linked_case_quantity_once_and_leaves_the_rest_as_backlog():
    rows = shape_plan_unit_po_coverage(
        [
            (4, "Highveld Wholesale", 100, 64),
            (None, "Unmapped distributor", 10, 0),
        ]
    )
    highveld, unmapped = rows
    assert highveld["plan_units"] == 100
    assert highveld["covered_units"] == 64
    assert highveld["backlog_units"] == 36
    assert highveld["covered"] == 0.64
    assert unmapped["distributor_id"] is None
    assert unmapped["backlog_units"] == 10
    assert unmapped["covered"] == 0.0


def test_shape_zero_plan_units_does_not_divide():
    rows = shape_plan_unit_po_coverage([(1, "Empty", 0, 0)])
    assert rows[0]["covered"] == 0.0
    assert rows[0]["backlog_units"] == 0


def test_failed_headline_read_logs_and_returns_empty(caplog):
    db = AsyncMock()
    first = MagicMock()
    first.scalar.return_value = "cip"
    db.execute = AsyncMock(side_effect=[first, RuntimeError("boom")])

    with caplog.at_level(logging.ERROR):
        out = asyncio.run(supply_overview(db, {"tenant_id": "default"}))

    assert out["database"] == "cip"
    assert out["data_unavailable"] is True
    assert out["labels"] == {}
    assert out["captions"] == {}
    assert any("supply overview read failed" in record.message for record in caplog.records)
