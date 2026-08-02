"""Unit tests for sticky POD carry-forward (P1-D004 / BACKLOG-088)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from app.services.imports import shipment_evidence_observations as obs_mod
from app.services.imports import shipment_inbound_facts as facts_mod


def test_sticky_pod_prefers_incoming_then_prior() -> None:
    assert facts_mod._sticky_pod(date(2026, 1, 2), date(2026, 1, 1)) == date(2026, 1, 2)
    assert facts_mod._sticky_pod(None, date(2026, 1, 1)) == date(2026, 1, 1)
    assert facts_mod._sticky_pod(None, None) is None


def test_merge_shipped_row_keeps_prior_pod_when_incoming_null() -> None:
    target = {col: None for col in facts_mod._UPSERT_REFRESH_COLUMNS}
    target["quantity"] = 1.0
    target["amount"] = 10.0
    target["pod_date"] = date(2026, 3, 1)
    target["status"] = "received"
    target["import_job_id"] = 1
    target["line_state"] = "shipped"
    incoming = dict(target)
    incoming["quantity"] = 2.0
    incoming["amount"] = 20.0
    incoming["pod_date"] = None
    incoming["status"] = "scheduled"
    incoming["import_job_id"] = 2
    facts_mod._merge_shipped_row_into(target, incoming)
    assert target["quantity"] == 3.0
    assert target["pod_date"] == date(2026, 3, 1)
    assert target["status"] == "received"
    assert target["import_job_id"] == 2


def test_apply_sticky_pod_to_rows_from_prior_map() -> None:
    rows = [
        {"fact_upsert_key": "ship:a", "pod_date": None, "status": "scheduled"},
        {"fact_upsert_key": "ship:b", "pod_date": date(2026, 4, 1), "status": "received"},
    ]
    facts_mod._apply_sticky_pod_to_rows(rows, {"ship:a": date(2026, 2, 2)})
    assert rows[0]["pod_date"] == date(2026, 2, 2)
    assert rows[0]["status"] == "received"
    assert rows[1]["pod_date"] == date(2026, 4, 1)


def test_apply_sticky_observation_pods(monkeypatch) -> None:
    db = MagicMock()
    values = [
        {"line_identity_key": "ship:x", "pod_date": None},
        {"line_identity_key": "ship:y", "pod_date": date(2026, 5, 1)},
    ]
    monkeypatch.setattr(
        obs_mod,
        "_prior_pod_by_identity_keys",
        lambda _db, keys: {"ship:x": date(2026, 1, 9)},
    )
    obs_mod._apply_sticky_observation_pods(db, values)
    assert values[0]["pod_date"] == date(2026, 1, 9)
    assert values[1]["pod_date"] == date(2026, 5, 1)
