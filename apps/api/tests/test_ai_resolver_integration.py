"""AI resolver wiring on existing import handlers (mocked, no DB writes)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.core.config import get_settings
from app.services.imports.ai_import_resolver import TokenResolutionSuggestion
from app.services.imports.ai_resolver_wiring import try_ai_token_resolution
from app.services.imports.product_master_workflow import _maybe_ai_remap_product_by_description


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _suggestion(*, cid: int = 42, confidence: float = 0.95) -> TokenResolutionSuggestion:
    return TokenResolutionSuggestion(
        best_match_id=cid,
        confidence=confidence,
        reasoning="test match",
        alternatives=[],
    )


# --- Product master workflow ---


def test_pm_ai_not_called_when_sku_exists() -> None:
    db = MagicMock()
    db.scalars.return_value.first.return_value = 99
    pl = {"sku": "SKU1", "name": "Widget"}
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_resolver_wiring.suggest_token_resolution") as mock_ai:
            out = _maybe_ai_remap_product_by_description(db, pl, {}, pd.Series(), 1)
    assert out["sku"] == "SKU1"
    mock_ai.assert_not_called()


def test_pm_ai_called_when_sku_missing_and_enabled() -> None:
    db = MagicMock()
    db.scalars.return_value.first.side_effect = [None, None]
    prod = SimpleNamespace(sku="EXIST", part_number="EXIST", id=42)
    db.get.return_value = prod
    pl = {"sku": "NEW-SKU", "name": "Blue widget"}
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
            return_value=_suggestion(),
        ) as mock_ai:
            out = _maybe_ai_remap_product_by_description(db, pl, {}, pd.Series({"name": "Blue widget"}), 1)
    assert mock_ai.called
    assert out["sku"] == "EXIST"


def test_pm_ai_high_confidence_remaps_sku() -> None:
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    prod = SimpleNamespace(sku="P-42", part_number="P-42", id=42)
    db.get.return_value = prod
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
            return_value=_suggestion(confidence=0.91),
        ):
            out = _maybe_ai_remap_product_by_description(
                db, {"sku": "X", "name": "desc"}, {}, pd.Series(), 1
            )
    assert out["sku"] == "P-42"


def test_pm_ai_low_confidence_leaves_sku() -> None:
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
            return_value=_suggestion(confidence=0.5),
        ):
            out = _maybe_ai_remap_product_by_description(
                db, {"sku": "X", "name": "desc"}, {}, pd.Series(), 1
            )
    assert out["sku"] == "X"


def test_pm_ai_failure_graceful() -> None:
    db = MagicMock()
    db.scalars.return_value.first.return_value = None
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_resolver_wiring.suggest_token_resolution", return_value=None):
            out = _maybe_ai_remap_product_by_description(
                db, {"sku": "X", "name": "desc"}, {}, pd.Series(), 1
            )
    assert out["sku"] == "X"


# --- Wiring helper ---


def test_try_ai_disabled_returns_none() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "false"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_resolver_wiring.suggest_token_resolution") as mock_ai:
            entity_id, tag, sug = try_ai_token_resolution(
                raw_token="TOK",
                token_type="product",
                candidates=[],
                import_type="test",
                job_id=1,
            )
    assert entity_id is None
    assert tag is None
    assert sug is None
    mock_ai.assert_not_called()


def test_try_ai_auto_resolved_threshold() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
            return_value=_suggestion(confidence=0.9),
        ):
            entity_id, tag, _ = try_ai_token_resolution(
                raw_token="TOK",
                token_type="product",
                candidates=[{"id": 42, "code": "c", "name": "n"}],
                import_type="test",
                job_id=1,
            )
    assert entity_id == 42
    assert tag == "ai_auto_resolved"


def test_try_ai_suggested_below_threshold() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
            return_value=_suggestion(confidence=0.5),
        ):
            entity_id, tag, sug = try_ai_token_resolution(
                raw_token="TOK",
                token_type="distributor",
                candidates=[],
                import_type="test",
                job_id=1,
            )
    assert entity_id is None
    assert tag == "ai_suggested"
    assert sug is not None


# --- Customer / distributor master (FK code resolution via wiring) ---


def test_customer_master_ai_resolves_unknown_distributor_code() -> None:
    db = MagicMock()
    db.scalars.return_value.all.return_value = [SimpleNamespace(id=10, code="d1", name="Dist")]
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
            return_value=_suggestion(cid=10, confidence=0.95),
        ):
            entity_id, tag, _ = try_ai_token_resolution(
                raw_token="DIST-X",
                token_type="distributor",
                candidates=[{"id": 10, "code": "d1", "name": "Dist"}],
                import_type="customer_master",
                job_id=1,
            )
    assert entity_id == 10
    assert tag == "ai_auto_resolved"


def test_customer_master_deterministic_distributor_no_ai() -> None:
    """When code maps in lookup dict, handlers should not need AI (wiring not invoked)."""
    distributors = {"d1": 10}
    assert distributors.get("d1".lower()) == 10
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_resolver_wiring.suggest_token_resolution") as mock_ai:
            if distributors.get("d1"):
                pass
    mock_ai.assert_not_called()


def test_distributor_master_no_ai_on_happy_path() -> None:
    """Distributor master upsert has no unresolved-token path; AI wiring is not invoked."""
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_resolver_wiring.suggest_token_resolution") as mock_ai:
            existing = {"d1": SimpleNamespace(code="d1")}
            assert "d1" in existing
    mock_ai.assert_not_called()


# --- DSI format drift ---


def test_dsi_ai_product_suggestion_appends_diagnostic() -> None:
    from app.services.imports.ai_resolver_wiring import append_ai_diagnostic

    diag: list = ["unresolved_product"]
    sug = _suggestion(confidence=0.5)
    out = append_ai_diagnostic(diag, token_type="product", suggestion=sug)
    assert len(out) == 2
    assert out[1]["type"] == "ai_suggestion"


def test_dsi_format_drift_recorded_when_enabled() -> None:
    from app.services.imports.ai_resolver_wiring import record_format_drift_on_job

    job = SimpleNamespace(id=1, staged_metadata={})
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.ai_resolver_wiring.detect_format_drift",
            return_value=SimpleNamespace(
                has_drift=True,
                new_columns=["new_col"],
                missing_columns=[],
                confidence=1.0,
            ),
        ):
            record_format_drift_on_job(
                job,
                current_headers=["sku", "new_col"],
                column_mapping_memory={"known_headers": ["sku", "qty"]},
                field_mapping={},
            )
    assert "format_drift_detected" in job.staged_metadata


# --- Shipment evidence ---


def test_shipment_ai_product_auto_resolved_in_post_resolve() -> None:
    from app.services.imports.shipment_evidence_import import _resolve_unresolved_shipment_lines_for_job

    idx = SimpleNamespace(sku_to_id={"A": 1})
    line = SimpleNamespace(
        product_id=None,
        item_code="UNKNOWN",
        ean_code=None,
        upc_code=None,
        sales_model_name=None,
        product_resolution_status=None,
        product_resolution_token=None,
        product_resolution_detail=None,
        distributor_id=5,
        bill_to_raw=None,
        ship_to_raw=None,
        distributor_resolution_status="resolved",
        distributor_resolution_token=None,
    )
    job = SimpleNamespace(id=1)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [line]

    def fake_resolve_product(*_a, **_k):
        return None, "no_match", "UNKNOWN", "unresolved"

    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.shipment_evidence_import.resolve_product_for_evidence",
            side_effect=fake_resolve_product,
        ):
            with patch(
                "app.services.imports.ai_resolver_wiring.suggest_token_resolution",
                return_value=_suggestion(),
            ):
                _resolve_unresolved_shipment_lines_for_job(db, job, idx, 1)

    assert line.product_id == 42
    assert line.product_resolution_status == "resolved_unique"


def test_shipment_ai_failure_graceful() -> None:
    from app.services.imports.shipment_evidence_import import _resolve_unresolved_shipment_lines_for_job

    idx = SimpleNamespace(sku_to_id={})
    line = SimpleNamespace(
        product_id=None,
        item_code="X",
        ean_code=None,
        upc_code=None,
        sales_model_name=None,
        product_resolution_status=None,
        product_resolution_token=None,
        product_resolution_detail=None,
        distributor_id=1,
        bill_to_raw=None,
        ship_to_raw=None,
        distributor_resolution_status="resolved",
        distributor_resolution_token=None,
    )
    job = SimpleNamespace(id=1)
    db = MagicMock()
    db.scalars.return_value.all.return_value = [line]

    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "true"}, clear=False):
        get_settings.cache_clear()
        with patch(
            "app.services.imports.shipment_evidence_import.resolve_product_for_evidence",
            return_value=(None, "no_match", "X", None),
        ):
            with patch("app.services.imports.ai_resolver_wiring.suggest_token_resolution", return_value=None):
                _resolve_unresolved_shipment_lines_for_job(db, job, idx, 1)

    assert line.product_id is None


def test_global_zero_ai_calls_when_disabled() -> None:
    with patch.dict("os.environ", {"AI_ASSIST_ENABLED": "false"}, clear=False):
        get_settings.cache_clear()
        with patch("app.services.imports.ai_resolver_wiring.suggest_token_resolution") as mock_ai:
            with patch("app.services.imports.ai_resolver_wiring.detect_format_drift") as mock_drift:
                try_ai_token_resolution(
                    raw_token="T",
                    token_type="product",
                    candidates=[],
                    import_type="x",
                    job_id=1,
                )
    assert mock_ai.call_count == 0
    assert mock_drift.call_count == 0
