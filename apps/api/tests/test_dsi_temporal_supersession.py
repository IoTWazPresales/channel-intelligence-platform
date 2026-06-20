"""Unit tests for DSI temporal supersession tier (no database)."""

from __future__ import annotations

from datetime import date

from app.services.imports.dsi_temporal_supersession import (
    REASON_TEMPORAL_SUPERSESSION,
    STATUS_FIFO_CANDIDATE,
    STATUS_RESOLVED,
    ProductShipmentWindowIndex,
    ShipmentWindow,
    try_temporal_supersession_product,
)


def _idx(
    canon: str,
    windows: dict[int, tuple[date, date]],
    *,
    global_extra: dict[int, tuple[date, date]] | None = None,
) -> ProductShipmentWindowIndex:
    dist_map = {
        (canon, pid): ShipmentWindow(product_id=pid, first_ship=fs, last_ship=ls)
        for pid, (fs, ls) in windows.items()
    }
    glob: dict[int, ShipmentWindow] = {}
    for pid, (fs, ls) in (global_extra or windows).items():
        glob[pid] = ShipmentWindow(product_id=pid, first_ship=fs, last_ship=ls)
    return ProductShipmentWindowIndex.from_windows(distributor_windows=dist_map, global_windows=glob)


def test_disjoint_supersession_resolves_pre_transition_line() -> None:
    """Running change: old SKU Mar–Apr, new SKU Jun–Oct — May sell-out maps to old SKU only."""
    old_pid, new_pid = 1001, 1002
    idx = _idx(
        "mustek",
        {
            old_pid: (date(2024, 3, 1), date(2024, 4, 30)),
            new_pid: (date(2024, 6, 1), date(2024, 10, 31)),
        },
    )
    res = try_temporal_supersession_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        eligible_product_ids=[old_pid, new_pid],
        evidence_date=date(2024, 5, 15),
        ambiguous_eligible={"product_ids": [old_pid, new_pid], "tier": "sales_model_name"},
    )
    assert res.product_id == old_pid
    assert res.resolve_reason == REASON_TEMPORAL_SUPERSESSION
    assert res.evidence is not None
    assert res.evidence["status"] == STATUS_RESOLVED
    assert res.evidence["fifo_candidate"] is False
    assert res.evidence["feasible_product_ids"] == [old_pid]


def test_disjoint_supersession_post_transition_both_feasible_stays_fifo_candidate() -> None:
    """After new SKU ships, both have first_ship <= D — tag fifo_candidate, do not resolve."""
    old_pid, new_pid = 1001, 1002
    idx = _idx(
        "mustek",
        {
            old_pid: (date(2024, 3, 1), date(2024, 4, 30)),
            new_pid: (date(2024, 6, 1), date(2024, 10, 31)),
        },
    )
    res = try_temporal_supersession_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        eligible_product_ids=[old_pid, new_pid],
        evidence_date=date(2024, 8, 1),
        ambiguous_eligible={"product_ids": [old_pid, new_pid], "tier": "sales_model_name"},
    )
    assert res.product_id is None
    assert res.resolve_reason is None
    assert res.evidence is not None
    assert res.evidence["status"] == STATUS_FIFO_CANDIDATE
    assert res.evidence["fifo_candidate"] is True
    assert set(res.evidence["feasible_product_ids"]) == {old_pid, new_pid}


def test_overlapping_windows_stay_fifo_candidate() -> None:
    """Overlapping ship windows — multiple feasible at same date, never silent FIFO."""
    pid_a, pid_b = 2001, 2002
    idx = _idx(
        "mustek",
        {
            pid_a: (date(2024, 1, 1), date(2024, 12, 31)),
            pid_b: (date(2024, 6, 1), date(2024, 12, 31)),
        },
    )
    res = try_temporal_supersession_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        eligible_product_ids=[pid_a, pid_b],
        evidence_date=date(2024, 9, 1),
        ambiguous_eligible={"product_ids": [pid_a, pid_b], "tier": "sales_model_name"},
    )
    assert res.product_id is None
    assert res.evidence is not None
    assert res.evidence["fifo_candidate"] is True
    assert len(res.evidence["feasible_product_ids"]) == 2


def test_no_distributor_evidence_does_not_resolve_via_global_window() -> None:
    """Global ordering windows are not used to assert distributor receipt."""
    only_global_pid, dist_pid = 3001, 3002
    idx = ProductShipmentWindowIndex.from_windows(
        distributor_windows={
            ("mustek", dist_pid): ShipmentWindow(
                dist_pid, date(2024, 6, 1), date(2024, 10, 31)
            ),
        },
        global_windows={
            only_global_pid: ShipmentWindow(only_global_pid, date(2024, 3, 1), date(2024, 4, 30)),
        },
    )
    res = try_temporal_supersession_product(
        idx,
        distributor_id=21,
        dist_id_to_canonical={21: "mustek"},
        eligible_product_ids=[only_global_pid, dist_pid],
        evidence_date=date(2024, 5, 1),
        ambiguous_eligible={"product_ids": [only_global_pid, dist_pid], "tier": "sales_model_name"},
    )
    assert res.product_id is None
    assert res.evidence is None
