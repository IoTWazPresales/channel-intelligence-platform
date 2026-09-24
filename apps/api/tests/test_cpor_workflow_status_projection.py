"""N-0048 / BACKLOG-139: ``workflow_status`` is a projection of ``status`` (mocked; no cip)."""

from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.cpor.lifecycle import LIFECYCLE_ACTIONS, LIFECYCLE_TRANSITIONS, workflow_status_for

client = TestClient(app)

_REPAIR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "ops" / "repair_n0048_cpor_case_status_drift.py"


def _repair_module():
    spec = importlib.util.spec_from_file_location("repair_n0048", _REPAIR_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_projection_covers_every_lifecycle_status():
    for status in LIFECYCLE_TRANSITIONS:
        want = "pending_approval" if status == "proposed" else status
        assert workflow_status_for(status) == want


# (from status, action) for every legal transition, including the two that drifted on cip.
_LEGAL = [
    (src, action)
    for action in LIFECYCLE_ACTIONS
    for src in LIFECYCLE_TRANSITIONS
    if (action == "resend" and src == "rejected")
    or (action != "resend" and LIFECYCLE_ACTIONS[action] in LIFECYCLE_TRANSITIONS[src])
]


def _case(status: str, workflow_status: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        tenant_id=None,
        status=status,
        workflow_status=workflow_status,
        customer_id=1,
        case_code="X",
        export_version=1,
        needs_reapproval=False,
        roe_snapshot=None,
        fx_mode="booked",
        last_comment=None,
        submitted_at=None,
        decided_at=None,
        decided_by=None,
    )


@pytest.mark.parametrize("src,action", _LEGAL)
def test_every_transition_writes_the_projection(src, action):
    # Start with a stale workflow_status (the shape the four cip rows had) to prove it is rewritten.
    case = _case(src, "stale")
    session = MagicMock()
    session.get = MagicMock(return_value=case)
    ep = "app.api.v1.endpoints.cpor_cases"
    br = "app.services.cpor.budget_reapproval"
    with patch(f"{ep}.SessionLocal") as SL, patch(f"{ep}._record_event"), patch(
        f"{ep}._run_drift_check", return_value=[]
    ), patch(f"{ep}.book_on_approve"), patch(f"{ep}.settle_fx_blocked", return_value=False), patch(
        f"{ep}._case_json", return_value={}
    ), patch(f"{ep}._products_map", return_value={}), patch(
        f"{ep}.tenant_profile_hard_enforce", return_value=False
    ), patch(f"{br}.evaluate_money_position", return_value={}), patch(f"{br}.apply_reapproval_flag"):
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        r = client.post("/api/v1/cpor/cases/10/transition", json={"action": action, "comment": "c"})
    assert r.status_code == 200, r.text
    assert case.status == LIFECYCLE_ACTIONS[action]
    assert case.workflow_status == workflow_status_for(case.status)


def test_settle_and_cancel_from_ended_are_covered():
    assert ("ended", "settle") in _LEGAL
    assert ("ended", "cancel") in _LEGAL
    assert ("draft", "cancel") in _LEGAL


def test_payment_evidence_shell_case_writes_the_projection():
    from app.services.cpor.payment_evidence.apply_sync import _ensure_shell_case

    line = SimpleNamespace(
        linked_case_id=None,
        create_shell_case=True,
        resolved_customer_id=7,
        external_case_code="C1",
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 31),
        payment_date=None,
        description=None,
        promotion_type_raw=None,
        currency_code="ZAR",
        case_status_raw="Settled",
        credit_note_id="CN1",
    )
    db = MagicMock()
    db.scalar = MagicMock(return_value=None)
    added: list = []
    db.add = MagicMock(side_effect=added.append)
    _ensure_shell_case(db, line=line, tenant_id="default", actor="t")
    case = added[0]
    assert case.status == "draft"
    assert case.workflow_status == workflow_status_for(case.status) == "draft"


# The four drifted rows measured on cip 2026-09-24 (read-only), plus control rows.
_CIP_SHAPES = [
    {"id": 3, "case_code": "BATCH0-SMOKE-001", "origin": "native", "status": "cancelled", "workflow_status": "draft", "updated_at": None},
    {"id": 309, "case_code": "C26761655", "origin": "historical_import", "status": "settled", "workflow_status": "ended", "updated_at": None},
    {"id": 310, "case_code": "C26759823", "origin": "historical_import", "status": "cancelled", "workflow_status": "ended", "updated_at": None},
    {"id": 311, "case_code": "C26760971", "origin": "historical_import", "status": "settled", "workflow_status": "ended", "updated_at": None},
]
_CONTROLS = [
    {"id": 1, "case_code": "OK1", "origin": "native", "status": "draft", "workflow_status": "draft", "updated_at": None},
    {"id": 2, "case_code": "OK2", "origin": "native", "status": "proposed", "workflow_status": "pending_approval", "updated_at": None},
    {"id": 4, "case_code": "OK3", "origin": "historical_import", "status": "settled", "workflow_status": "settled", "updated_at": None},
]


def test_repair_plans_exactly_the_four_cip_rows_and_never_touches_status():
    mod = _repair_module()
    rows = [dict(r) for r in _CIP_SHAPES + _CONTROLS]
    changes = mod.plan_repair(rows)
    assert [c["id"] for c in changes] == [3, 309, 310, 311]
    assert {c["id"]: c["workflow_status_after"] for c in changes} == {
        3: "cancelled",
        309: "settled",
        310: "cancelled",
        311: "settled",
    }
    assert all(c["status"] == c["workflow_status_after"] for c in changes)
    before = mod.counts(rows)
    assert before == {"cpor_case_rows": 7, "status_ne_workflow_status": 5, "workflow_status_ne_projection": 4}


def test_repair_is_idempotent_on_the_four_cip_shapes():
    mod = _repair_module()
    rows = [dict(r) for r in _CIP_SHAPES + _CONTROLS]
    by_id = {r["id"]: r for r in rows}
    for c in mod.plan_repair(rows):
        by_id[c["id"]]["workflow_status"] = c["workflow_status_after"]
    assert mod.plan_repair(rows) == []
    # proposed keeps its pending_approval projection, so it is the only status != workflow_status left
    assert mod.counts(rows)["status_ne_workflow_status"] == 1
