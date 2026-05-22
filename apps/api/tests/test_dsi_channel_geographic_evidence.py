"""DSI channel geographic evidence aggregation (job-level visibility)."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.imports.dsi_channel_geographic_evidence import collect_dsi_channel_geographic_evidence_sync


def test_collect_channel_geographic_evidence_aggregates_rows() -> None:
    job = MagicMock()
    job.template_slug = "distributor_inventory"

    cand = MagicMock()
    cand.entity_type = "customer_dealer_token"
    cand.id = 10
    cand.row_count = 5
    cand.context = {"source_channel_raw_samples": ["ZA", "BB_Open Channel"]}

    sess = MagicMock()
    sess.get = MagicMock(return_value=job)
    sess.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[cand]))
    )

    out = collect_dsi_channel_geographic_evidence_sync(sess, 99)
    assert out["import_job_id"] == 99
    assert len(out["channels"]) == 1
    ch = out["channels"][0]
    assert ch["guessed_region_code"] == "ZA"
    assert ch["row_count"] == 5
    assert ch["customer_candidate_count"] == 1
