"""Unit tests for DSI geo steward bulk apply."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.imports.dsi_geo_steward_bulk_sync import apply_dsi_geo_steward_bulk_sync
from app.services.imports.dsi_steward_candidate_ops import StewardOpError


def test_geo_bulk_register_region_from_hint_applies_each_item() -> None:
    sess = MagicMock()

    with patch(
        "app.services.imports.dsi_geo_steward_bulk_sync.register_region_from_geographic_hint_sync",
        side_effect=[
            {"ok": True, "region_id": 1, "iso_alpha2": "BW"},
            {"ok": True, "region_id": 2, "iso_alpha2": "SZ"},
        ],
    ) as mock_hint:
        out = apply_dsi_geo_steward_bulk_sync(
            sess,
            import_job_id=43,
            action="register_region_from_hint",
            items=[
                {"kind": "channel", "raw_token": "SADC_Botswana", "iso_alpha2": "BW"},
                {"kind": "channel", "raw_token": "SADC_Eswatini", "iso_alpha2": "SZ"},
            ],
        )

    assert out["applied"] == 2
    assert out["failed"] == 0
    assert mock_hint.call_count == 2


def test_geo_bulk_collects_per_item_errors() -> None:
    sess = MagicMock()

    def _hint(sess, *, import_job_id, raw_token, iso_alpha2, notes):
        if raw_token == "BAD":
            raise StewardOpError("Could not infer ISO country from token", status_code=400)
        return {"ok": True, "region_id": 3, "iso_alpha2": iso_alpha2 or "LS"}

    with patch(
        "app.services.imports.dsi_geo_steward_bulk_sync.register_region_from_geographic_hint_sync",
        side_effect=_hint,
    ):
        out = apply_dsi_geo_steward_bulk_sync(
            sess,
            import_job_id=43,
            action="register_region_from_hint",
            items=[
                {"kind": "channel", "raw_token": "SADC_Lesotho"},
                {"kind": "channel", "raw_token": "BAD"},
            ],
        )

    assert out["applied"] == 1
    assert out["failed"] == 1
    assert out["results"][0]["ok"] is True
    assert out["results"][1]["ok"] is False


def test_geo_bulk_rejects_empty_items() -> None:
    with pytest.raises(StewardOpError) as ei:
        apply_dsi_geo_steward_bulk_sync(
            MagicMock(),
            import_job_id=1,
            action="register_region_from_hint",
            items=[],
        )
    assert ei.value.status_code == 400
