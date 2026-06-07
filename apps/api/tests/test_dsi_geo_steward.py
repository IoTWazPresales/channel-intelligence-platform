"""DSI geo stewardship: unresolved token collection + region alias resolution (unit-level)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.db.base import Base
from app.services.imports.dsi_resolution_plan import (
    _alias_region_id_for_dsi,
    _resolve_dim_region_from_source,
    collect_dsi_job_unresolved_geo_tokens_sync,
    dsi_geo_region_alias_source_id,
)
from app.services.imports.dsi_steward_candidate_ops import StewardOpError
from app.services.imports.dsi_steward_geo_catalog import create_channel_source_token_alias_sync


def test_region_source_token_alias_registered_in_sqlalchemy_metadata() -> None:
    assert "region_source_token_alias" in Base.metadata.tables


def test_dsi_geo_region_alias_source_id_matches_channel_policy() -> None:
    cand = MagicMock()
    cand.source_definition_id = 3
    job = MagicMock()
    job.source.id = 9
    assert dsi_geo_region_alias_source_id(cand, job) == 3
    cand.source_definition_id = None
    assert dsi_geo_region_alias_source_id(cand, job) == 9


def test_resolve_dim_region_via_approved_alias() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(side_effect=[None, None])
    sess.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[77, 77])))
    rid, reason = _resolve_dim_region_from_source(sess, "Some Province", source_definition_id=4)
    assert rid == 77
    assert reason == "source_region_token_alias"


def test_resolve_dim_region_conflicting_aliases() -> None:
    sess = MagicMock()
    sess.scalar = MagicMock(side_effect=[None, None])
    sess.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[1, 2])))
    rid, reason = _resolve_dim_region_from_source(sess, "Ambiguous", source_definition_id=1)
    assert rid is None
    assert reason == "conflicting_region_token_aliases"


def test_alias_region_id_for_dsi_empty_token() -> None:
    sess = MagicMock()
    rid, reason = _alias_region_id_for_dsi(sess, 1, "   ")
    assert rid is None
    assert reason is None


def test_collect_unresolved_geo_merges_row_counts() -> None:
    job = MagicMock()
    job.template_slug = "distributor_inventory"
    job.source = MagicMock()
    job.source.id = 5

    c1 = MagicMock()
    c1.entity_type = "customer_dealer_token"
    c1.id = 10
    c1.row_count = 2
    c1.context = {
        "source_channel_evidence_norms": ["bb_open"],
        "source_channel_raw_samples": ["BB_Open Channel"],
        "source_region_evidence_norms": ["exotic"],
        "source_region_raw_samples": [" Exotic-Province "],
    }
    c1.source_definition_id = 5

    c2 = MagicMock()
    c2.entity_type = "customer_dealer_token"
    c2.id = 11
    c2.row_count = 3
    c2.context = {
        "source_channel_evidence_norms": ["bb_open"],
        "source_channel_raw_samples": ["BB_Open Channel"],
        "source_region_evidence_norms": [],
        "source_region_raw_samples": [],
    }
    c2.source_definition_id = 5

    sess = MagicMock()
    sess.get = MagicMock(return_value=job)

    def _scalars(stmt):
        m = MagicMock()

        def all():
            return [c1, c2]

        m.all = all
        return m

    sess.scalars = MagicMock(side_effect=_scalars)

    def fake_geo(session, ctx, *, source_definition_id=None):
        ch_norms = ctx.get("source_channel_evidence_norms") or []
        rg_norms = ctx.get("source_region_evidence_norms") or []
        out = {
            "provisional_channel_conflict": False,
            "provisional_region_conflict": False,
            "source_channel_resolved_id": None,
            "source_channel_resolution_detail": "no_catalog_match" if ch_norms else "missing_source_evidence",
            "source_channel_raw_token": "BB_Open Channel" if ch_norms else None,
            "source_region_resolved_id": None,
            "source_region_resolution_detail": "no_catalog_match" if rg_norms else "missing_source_evidence",
            "source_region_raw_token": " Exotic-Province " if rg_norms else None,
        }
        return out

    with patch(
        "app.services.imports.dsi_geo_resolution_cache.resolve_source_geo_from_ctx_cached",
        side_effect=fake_geo,
    ):
        with patch("app.services.imports.dsi_geo_resolution_cache.DSIGeoResolutionCache") as mock_cache_cls:
            mock_cache_cls.build.return_value = MagicMock()
            mock_cache_cls.build.return_value.preload_aliases = MagicMock()
            payload = collect_dsi_job_unresolved_geo_tokens_sync(sess, 99)

    assert payload["import_job_id"] == 99
    assert len(payload["channels"]) == 1
    ch0 = payload["channels"][0]
    assert ch0["normalized_token"] == "bb_open channel"
    assert ch0["row_count"] == 5
    assert sorted(ch0["candidate_ids"]) == [10, 11]
    assert len(payload["regions"]) == 1
    assert payload["regions"][0]["row_count"] == 2


def test_collect_unresolved_geo_channel_geographic_hint_sadc_compound() -> None:
    job = MagicMock()
    job.template_slug = "distributor_inventory"
    job.source = MagicMock()
    job.source.id = 5

    cand = MagicMock()
    cand.entity_type = "customer_dealer_token"
    cand.id = 10
    cand.row_count = 78
    cand.context = {
        "source_channel_evidence_norms": ["sadc_botswana"],
        "source_channel_raw_samples": ["SADC_Botswana"],
        "source_region_evidence_norms": [],
        "source_region_raw_samples": [],
    }
    cand.source_definition_id = 5

    sess = MagicMock()
    sess.get = MagicMock(return_value=job)
    sess.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=[cand]))
    )
    sess.scalar = MagicMock(return_value=None)

    def fake_geo(session, ctx, *, source_definition_id=None):
        return {
            "provisional_channel_conflict": False,
            "provisional_region_conflict": False,
            "source_channel_resolved_id": None,
            "source_channel_resolution_detail": "no_catalog_match",
            "source_channel_raw_token": "SADC_Botswana",
            "source_region_resolved_id": None,
            "source_region_resolution_detail": "missing_source_evidence",
            "source_region_raw_token": None,
        }

    mock_cache = MagicMock()
    mock_cache.preload_aliases = MagicMock()
    mock_cache.approved_region_alias_region_ids = MagicMock(return_value=[])

    with patch(
        "app.services.imports.dsi_geo_resolution_cache.resolve_source_geo_from_ctx_cached",
        side_effect=fake_geo,
    ):
        with patch("app.services.imports.dsi_geo_resolution_cache.DSIGeoResolutionCache") as mock_cache_cls:
            mock_cache_cls.build.return_value = mock_cache
            payload = collect_dsi_job_unresolved_geo_tokens_sync(sess, 43)

    assert len(payload["channels"]) == 1
    ch0 = payload["channels"][0]
    assert ch0["raw_token"] == "SADC_Botswana"
    assert ch0["geographic_hint"]["guessed_region_code"] == "BW"
    assert ch0["geographic_hint"]["matched_catalog"] is False
    assert ch0["geographic_hint"]["alias_registered"] is False
    assert ch0["geographic_hint"]["registered_region_id"] is None


def test_collect_unresolved_geo_geographic_hint_alias_registered() -> None:
    job = MagicMock()
    job.template_slug = "distributor_inventory"
    job.source = MagicMock()
    job.source.id = 5

    cand = MagicMock()
    cand.entity_type = "customer_dealer_token"
    cand.id = 10
    cand.row_count = 78
    cand.context = {
        "source_channel_evidence_norms": ["sadc_botswana"],
        "source_channel_raw_samples": ["SADC_Botswana"],
        "source_region_evidence_norms": [],
        "source_region_raw_samples": [],
    }
    cand.source_definition_id = 5

    reg = MagicMock()
    reg.code = "BW"
    reg.id = 42

    sess = MagicMock()
    sess.get = MagicMock(return_value=job)

    def _scalars(stmt):
        m = MagicMock()

        def all():
            table = getattr(getattr(stmt, "column_descriptions", [{}])[0], "get", lambda *_: None)("name")
            if table == "ImportEntityMappingCandidate":
                return [cand]
            return [reg]

        m.all = all
        return m

    sess.scalars = _scalars
    sess.scalar = MagicMock(return_value=None)

    def fake_geo(session, ctx, *, source_definition_id=None):
        return {
            "provisional_channel_conflict": False,
            "provisional_region_conflict": False,
            "source_channel_resolved_id": None,
            "source_channel_resolution_detail": "no_catalog_match",
            "source_channel_raw_token": "SADC_Botswana",
            "source_region_resolved_id": None,
            "source_region_resolution_detail": "missing_source_evidence",
            "source_region_raw_token": None,
        }

    mock_cache = MagicMock()
    mock_cache.preload_aliases = MagicMock()
    mock_cache.approved_region_alias_region_ids = MagicMock(return_value=[42])

    with patch(
        "app.services.imports.dsi_geo_resolution_cache.resolve_source_geo_from_ctx_cached",
        side_effect=fake_geo,
    ):
        with patch("app.services.imports.dsi_geo_resolution_cache.DSIGeoResolutionCache") as mock_cache_cls:
            mock_cache_cls.build.return_value = mock_cache
            payload = collect_dsi_job_unresolved_geo_tokens_sync(sess, 43)

    ch0 = payload["channels"][0]
    assert ch0["geographic_hint"]["alias_registered"] is True
    assert ch0["geographic_hint"]["registered_region_id"] == 42
    assert ch0["geographic_hint"]["matched_catalog"] is True


def test_create_channel_alias_requires_raw_token() -> None:
    sess = MagicMock()
    job = MagicMock()
    job.template_slug = "distributor_inventory"
    job.source = MagicMock()
    job.source.id = 1
    sess.get = MagicMock(return_value=job)
    with pytest.raises(StewardOpError) as ei:
        create_channel_source_token_alias_sync(sess, import_job_id=3, channel_id=9, raw_token="  ", notes=None)
    assert ei.value.status_code == 400
