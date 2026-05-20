"""Unit tests for intra-job segment merge + Open Channel consolidation (pending customer map)."""

from __future__ import annotations

from decimal import Decimal

from app.services.imports.shipment_evidence_customer_remainder_merge import (
    apply_intra_job_remainder_merge_pass,
)


def _pb(
    *,
    line_ids: list[int],
    source_tokens: list[str],
    display: str,
    special: str | None = None,
    dup: list[str] | None = None,
) -> dict:
    d: dict = {
        "line_ids": list(line_ids),
        "source_tokens": list(source_tokens),
        "samples": list(source_tokens[:5]),
        "qty": Decimal(0),
        "amt": Decimal(0),
        "needs_name_review": False,
        "display_suggested_name": display,
        "special_category": special,
    }
    if dup:
        d["possible_duplicate_of"] = list(dup)
    return d


def test_mid_position_sadc_q2_compuspeed_merges_to_compuspeed() -> None:
    """SADC – Q2 COMPUSPEED → cleaned segment COMPUSPEED matches canonical ``Compuspeed``."""
    pending = {
        "comp": _pb(line_ids=[1], source_tokens=["Compuspeed"], display="Compuspeed"),
        "sadc": _pb(line_ids=[2], source_tokens=["SADC - Q2 COMPUSPEED"], display="SADC - Q2 COMPUSPEED"),
    }
    apply_intra_job_remainder_merge_pass(pending)
    assert "sadc" not in pending
    m = pending["comp"]
    assert sorted(m["line_ids"]) == [1, 2]
    assert m["display_suggested_name"] == "Compuspeed"


def test_multi_segment_retail_compuspeed_q2_ambiguous_two_targets() -> None:
    """Two targets both ≥0.88 vs segment ``COMPUSPEED`` → duplicate hint, no merge."""
    pending = {
        "src": _pb(line_ids=[1], source_tokens=["RETAIL - COMPUSPEED Q2"], display="RETAIL - COMPUSPEED Q2"),
        "sa": _pb(line_ids=[2], source_tokens=["x"], display="COMPUSPEED SA"),
        "bv": _pb(line_ids=[3], source_tokens=["y"], display="COMPUSPEED BV"),
    }
    apply_intra_job_remainder_merge_pass(pending)
    assert "src" in pending and "sa" in pending and "bv" in pending
    dup = pending["src"].get("possible_duplicate_of") or []
    assert dup, "expected possible_duplicate_of when two targets hit merge threshold"
    assert dup[0] in ("bv", "sa")


def test_retail_ic_q2_no_usable_anchor_unchanged() -> None:
    """RETAIL - IC Q2: after Q-strip the anchor is too short (<3) → no segment match pass."""
    pending = {
        "src": _pb(line_ids=[1], source_tokens=["RETAIL - IC Q2"], display="RETAIL - IC Q2"),
        "other": _pb(line_ids=[2], source_tokens=["IC Retail"], display="IC Retail"),
    }
    apply_intra_job_remainder_merge_pass(pending)
    assert "src" in pending
    assert not pending["src"].get("possible_duplicate_of")


def test_segment_merge_tb_acme_retail() -> None:
    pending = {
        "canonical": _pb(line_ids=[1], source_tokens=["Acme Retail"], display="Acme Retail"),
        "noisy": _pb(line_ids=[2], source_tokens=["TB - Acme Retail"], display="TB - Acme Retail"),
    }
    apply_intra_job_remainder_merge_pass(pending)
    assert "noisy" not in pending
    assert sorted(pending["canonical"]["line_ids"]) == [1, 2]


def test_tb_polytechnic_single_segment_merge() -> None:
    pending = {
        "corp": _pb(line_ids=[10], source_tokens=["Polytechnic"], display="Polytechnic"),
        "tb": _pb(line_ids=[11], source_tokens=["TB Polytechnic"], display="TB Polytechnic"),
    }
    apply_intra_job_remainder_merge_pass(pending)
    assert "tb" not in pending
    assert 11 in pending["corp"]["line_ids"]


def test_open_channel_variants_consolidated() -> None:
    pending = {
        "a": _pb(line_ids=[1], source_tokens=["t1"], display="Open Channel - OA90"),
        "b": _pb(line_ids=[2], source_tokens=["t2"], display="Open Channel Syntech"),
    }
    apply_intra_job_remainder_merge_pass(pending)
    assert len([k for k, v in pending.items() if (v.get("display_suggested_name") or "").strip() == "Open Channel"]) == 1
    oc = next(v for _k, v in pending.items() if (v.get("display_suggested_name") or "").strip() == "Open Channel")
    assert sorted(oc["line_ids"]) == [1, 2]
    assert oc.get("special_category") is None


def test_open_channel_other_noise_not_consolidated() -> None:
    """Rows without Open Channel triggers stay in ``noise_only``; OC suffix rows still merge."""
    pending = {
        "noise": _pb(line_ids=[1], source_tokens=["x"], display="Accessory", special="noise_only"),
        "oc": _pb(line_ids=[2], source_tokens=["t2"], display="Open Channel - Redington"),
    }
    apply_intra_job_remainder_merge_pass(pending, distributor_suggested_names=frozenset())
    assert "noise" in pending
    assert pending["noise"].get("special_category") == "noise_only"
    oc_rows = [v for _k, v in pending.items() if (v.get("display_suggested_name") or "").strip() == "Open Channel"]
    assert len(oc_rows) == 1
    assert 2 in oc_rows[0]["line_ids"]


def test_open_channel_noise_merges_when_display_contains_open_channel_phrase() -> None:
    pending = {
        "noise": _pb(line_ids=[1], source_tokens=["oc"], display="open channel", special="noise_only"),
        "oc": _pb(line_ids=[2], source_tokens=["t2"], display="Open Channel - Redington"),
    }
    apply_intra_job_remainder_merge_pass(pending, distributor_suggested_names=frozenset())
    assert "noise" not in pending
    oc_rows = [v for _k, v in pending.items() if (v.get("display_suggested_name") or "").strip() == "Open Channel"]
    assert len(oc_rows) == 1
    assert sorted(oc_rows[0]["line_ids"]) == [1, 2]
    assert oc_rows[0].get("special_category") is None


def test_open_channel_distributor_name_collision_merges() -> None:
    """Customer display cleans to the same string as a distributor suggested name → Open Channel bucket."""
    pending = {
        "cust": _pb(line_ids=[1], source_tokens=["raw"], display="TB - ACME Distribution"),
    }
    apply_intra_job_remainder_merge_pass(
        pending,
        distributor_suggested_names=frozenset({"Acme Distribution"}),
    )
    oc = next(v for _k, v in pending.items() if (v.get("display_suggested_name") or "").strip() == "Open Channel")
    assert 1 in oc["line_ids"]
    assert oc.get("special_category") is None


def test_open_channel_cleaned_display_equals_channel_merges() -> None:
    pending = {
        "c": _pb(line_ids=[9], source_tokens=["tok"], display="RETAIL - Channel"),
    }
    apply_intra_job_remainder_merge_pass(pending, distributor_suggested_names=frozenset())
    oc = next(v for _k, v in pending.items() if (v.get("display_suggested_name") or "").strip() == "Open Channel")
    assert 9 in oc["line_ids"]
