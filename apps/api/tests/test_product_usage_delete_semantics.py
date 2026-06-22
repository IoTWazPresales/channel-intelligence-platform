"""Unit checks for product delete hard vs soft classification."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from app.services.product_usage import _SPECS, cleanup_soft_product_references


def _hard_blocker_labels() -> set[str]:
    labels = {label for label, _col in _SPECS}
    labels.update(
        {
            "Product roadmap",
            "Lineup plan items",
            "Import mapping candidates (product)",
        }
    )
    return labels


def test_hard_blocker_labels_exclude_derived_and_alias_sources() -> None:
    labels = _hard_blocker_labels()
    assert "Sell-out" in labels
    assert "Lineup plan items" in labels
    assert "Pricing" in labels
    assert "Stock health" not in labels
    assert "Weeks of stock" not in labels
    assert "Stock risk" not in labels
    assert "Buy recommendations" not in labels
    assert "Product aliases" not in labels
    assert "Forecast summary" not in labels
    assert "Exceptions (linked SKU)" not in labels


def test_cleanup_soft_runs_one_delete_per_derived_table() -> None:
    async def run() -> None:
        db = MagicMock()
        db.execute = AsyncMock(return_value=MagicMock(rowcount=0))
        await cleanup_soft_product_references(db, 99)
        assert len(db.execute.await_args_list) == 10

    asyncio.run(run())
