"""SKU-twin pick for CST article aliases (no cip)."""

from __future__ import annotations

from datetime import date

from app.services.imports.cst_sku_twin_disambiguate import (
    InboundWindow,
    ProductLite,
    filter_by_best_lifecycle,
    pick_sku_twin,
    sku_twin_blocks_auto_confirm,
)


def _p(pid: int, sku: str, life: str | None) -> ProductLite:
    return ProductLite(product_id=pid, sku=sku, lifecycle_status=life, is_active=True)


def _w(pid: int, first: date | None, last: date | None, qty: float = 0, scope: str = "global") -> InboundWindow:
    return InboundWindow(product_id=pid, first_pod=first, last_pod=last, qty=qty, scope=scope if first else "none")


def test_lifecycle_published_beats_discarded():
    kept = filter_by_best_lifecycle(
        [_p(1, "A", "Published"), _p(2, "B", "Discarded")]
    )
    assert [k.product_id for k in kept] == [1]


def test_lifecycle_disabled_beats_discarded():
    kept = filter_by_best_lifecycle(
        [_p(1, "A", "Discarded"), _p(2, "B", "Disabled")]
    )
    assert [k.product_id for k in kept] == [2]


def test_lifecycle_published_beats_standby():
    kept = filter_by_best_lifecycle(
        [_p(1, "A", "Standby"), _p(2, "B", "Published")]
    )
    assert [k.product_id for k in kept] == [2]


def test_shipping_unique_when_only_one_twin_has_pod():
    survivors = [_p(652, "M00760", "Published"), _p(12581, "M00EL0", "Published")]
    windows = {
        652: _w(652, None, None),
        12581: _w(12581, date(2024, 7, 30), date(2025, 12, 11), 124),
    }
    pick = pick_sku_twin(survivors, windows, as_of=date(2026, 8, 17), shipping_scope="global")
    assert pick is not None
    assert pick.product_id == 12581
    assert pick.reason == "shipping_unique"
    assert pick.flag is False


def test_as_of_single_feasible_window():
    survivors = [_p(10, "OLD", "Published"), _p(11, "NEW", "Published")]
    windows = {
        10: _w(10, date(2023, 1, 1), date(2023, 6, 1), 10),
        11: _w(11, date(2025, 1, 1), date(2025, 6, 1), 10),
    }
    pick = pick_sku_twin(survivors, windows, as_of=date(2024, 1, 1), shipping_scope="global")
    assert pick is not None
    assert pick.product_id == 10
    assert pick.reason == "shipping_as_of"
    assert pick.flag is False


def test_both_published_both_in_channel_is_flagged_prefill():
    survivors = [_p(1164, "M00P10", "Published"), _p(5088, "M00YE0", "Published")]
    windows = {
        1164: _w(1164, date(2024, 2, 12), date(2024, 12, 6), 432),
        5088: _w(5088, date(2025, 3, 5), date(2025, 3, 5), 96),
    }
    pick = pick_sku_twin(survivors, windows, as_of=date(2026, 8, 17), shipping_scope="global")
    assert pick is not None
    assert pick.flag is True
    assert pick.reason == "tied_prefill"
    assert pick.product_id == 5088  # later last_pod
    assert pick.as_evidence()["sku_twin"] is True
    assert sku_twin_blocks_auto_confirm(pick.as_evidence()) is True


def test_auto_confirm_allows_unique_pm_match():
    assert sku_twin_blocks_auto_confirm({"source": "scm_upload", "unique_pm_match": True}) is False
