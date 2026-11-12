"""A move or return draft is a stock action, not a support claim (mocked; no cip).

The server refuses every support step for it, so the API cannot turn a logistics
draft into a commitment. Its action metadata survives a cost edit.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.main import app
from app.services.cpor.lifecycle import LIFECYCLE_ACTIONS
from fastapi.testclient import TestClient

client = TestClient(app)

EP = "app.api.v1.endpoints.cpor_cases"
BR = "app.services.cpor.budget_reapproval"


def _case(status: str, origin: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=10,
        tenant_id=None,
        status=status,
        workflow_status=status,
        customer_id=1,
        case_code="X",
        origin=origin,
        export_version=1,
        needs_reapproval=False,
        roe_snapshot=None,
        fx_mode="booked",
        last_comment=None,
        submitted_at=None,
        decided_at=None,
        decided_by=None,
        created_at=None,
    )


def _post(case: SimpleNamespace, action: str):
    session = MagicMock()
    session.get = MagicMock(return_value=case)
    with patch(f"{EP}.SessionLocal") as SL, patch(f"{EP}._record_event"), patch(
        f"{EP}._run_drift_check", return_value=[]
    ), patch(f"{EP}.book_on_approve"), patch(f"{EP}.settle_fx_blocked", return_value=False), patch(
        f"{EP}._case_json", return_value={}
    ), patch(f"{EP}._products_map", return_value={}), patch(
        f"{BR}.evaluate_money_position", return_value={}
    ), patch(f"{BR}.apply_reapproval_flag"), patch(
        "app.services.budget_ledger.apply_case_transition"
    ) as ledger:
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        response = client.post(
            f"/api/v1/cpor/cases/{case.id}/transition", json={"action": action, "comment": "c"}
        )
    return response, session, ledger


@pytest.mark.parametrize("action", ["propose", "approve"])
def test_a_stock_action_cannot_enter_the_support_workflow(action):
    status = "draft" if action == "propose" else "proposed"
    case = _case(status, "stock_action")
    response, session, ledger = _post(case, action)
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "not_a_support_claim"
    assert case.status == status
    ledger.assert_not_called()
    session.commit.assert_not_called()


def test_a_stock_action_can_still_be_cancelled():
    case = _case("draft", "stock_action")
    response, _session, _ledger = _post(case, "cancel")
    assert response.status_code == 200, response.text
    assert case.status == "cancelled"


def test_a_cip_promotion_still_proposes():
    case = _case("draft", "proposed_by_cip")
    response, _session, _ledger = _post(case, "propose")
    assert response.status_code == 200, response.text
    assert case.status == "proposed"


def test_only_cancel_is_open_to_a_stock_action():
    from app.services.cpor.lifecycle import support_step_refused

    refused = {a for a in LIFECYCLE_ACTIONS if support_step_refused("stock_action", a)}
    assert refused == set(LIFECYCLE_ACTIONS) - {"cancel"}
    for origin in ("native", "proposed_by_cip", None):
        assert not support_step_refused(origin, "approve")


@pytest.mark.parametrize("action", ["approve", "settle"])
def test_ledger_refuses_support_money_for_a_stock_action(action):
    from app.services import budget_ledger

    session = MagicMock()
    case = _case("proposed", "stock_action")
    with patch.object(budget_ledger, "add_entry") as add_entry:
        with pytest.raises(ValueError, match="not_a_support_claim"):
            budget_ledger.apply_case_transition(session, case, action, actor="planner")
    add_entry.assert_not_called()
    session.scalars.assert_not_called()


def test_cost_edit_keeps_the_stock_action_sites():
    case = _case("draft", "stock_action")
    line = SimpleNamespace(
        id=21,
        case_id=10,
        product_id=9,
        cost_source="intake_weighted",
        cost_basis=10.0,
        cost_evidence_json={
            "stock_action": "move",
            "site_labels": ["North"],
            "flags": ["bucket_a"],
            "blend": {"old": True},
        },
    )
    session = MagicMock()

    def get(model, key):
        return case if getattr(model, "__name__", "") == "CporCase" else line

    session.get = MagicMock(side_effect=get)
    sug = SimpleNamespace(evidence={"manual_cost": 12.5}, flags=["manual"])
    with patch(f"{EP}.SessionLocal") as SL, patch(f"{EP}._record_event"), patch(
        f"{EP}.suggest_cost_basis", return_value=sug
    ), patch(f"{EP}.recompute_case_line", return_value={"flags": []}), patch(
        f"{EP}._line_json", return_value={}
    ):
        SL.return_value.__enter__.return_value = session
        SL.return_value.__exit__.return_value = None
        response = client.patch("/api/v1/cpor/cases/10/lines/21", json={"cost_basis": 12.5})
    assert response.status_code == 200, response.text
    evidence = line.cost_evidence_json
    assert evidence["stock_action"] == "move"
    assert evidence["site_labels"] == ["North"]
    # The cost evidence itself is replaced, as before.
    assert evidence["manual_cost"] == 12.5
    assert evidence["flags"] == ["manual"]
    assert "blend" not in evidence


def test_cost_edit_on_an_ordinary_line_adds_no_action_keys():
    from app.services.store_dc.rules import keep_stock_action_evidence

    assert keep_stock_action_evidence(None, {"a": 1}) == {"a": 1}
    assert keep_stock_action_evidence({"flags": []}, {"a": 1}) == {"a": 1}
    kept = keep_stock_action_evidence({"site_labels": [None]}, {"a": 1})
    assert kept == {"a": 1, "site_labels": [None]}
