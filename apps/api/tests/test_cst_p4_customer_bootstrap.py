"""Placeholder report config bootstrap — mocked session, synthetic customers, no DB writes."""

from __future__ import annotations

from types import SimpleNamespace

import app.services.imports.cst_p4_customer_bootstrap as mod
from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.services.imports.cst_p4_customer_bootstrap import bootstrap_p4_customer_configs

SYNTH_IDS = [9101, 9102, 9103]


class _FakeSession:
    """Minimal stand-in supporting the two call shapes the bootstrap function needs."""

    def __init__(self, customers: dict[int, object], configs: dict[int, object]):
        self._customers = customers
        self._configs = configs
        self.added: list[object] = []

    def get(self, model, pk):
        assert model is DimCustomer
        return self._customers.get(pk)

    def scalar(self, stmt):
        (customer_id,) = stmt.compile().params.values()
        return self._configs.get(customer_id)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def _customer(id_: int, tenant_id: str = "default") -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=f"Synthetic Customer {id_}", tenant_id=tenant_id)


def _customers(ids=SYNTH_IDS) -> dict[int, SimpleNamespace]:
    return {cid: _customer(cid) for cid in ids}


def test_no_customer_ids_or_exclusions_in_code() -> None:
    assert not hasattr(mod, "P4_CUSTOMER_IDS")
    assert not hasattr(mod, "EXCLUDED_PILOT_CUSTOMER_ID")


def test_creates_placeholder_config_for_each_selected_customer() -> None:
    session = _FakeSession(_customers(), configs={})
    result = bootstrap_p4_customer_configs(session, SYNTH_IDS)
    assert result["ok"] is True
    assert result["created_count"] == 3
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 0
    assert result["missing_customer"] == []
    assert [c["customer_id"] for c in result["created"]] == SYNTH_IDS
    for cfg in session.added:
        assert cfg.reports_expected is True
        assert cfg.expected_cadence == "weekly"
        assert cfg.report_structure_type is None
        assert cfg.notes == "P4 awaiting sample WEEK file (Q-004)"
        assert cfg.feed_profile_json == {"status": "awaiting_sample_file", "pilot": "p4"}


def test_only_the_selected_customers_are_touched() -> None:
    session = _FakeSession(_customers(), configs={})
    result = bootstrap_p4_customer_configs(session, [9102])
    assert [c["customer_id"] for c in result["created"]] == [9102]
    assert {cfg.customer_id for cfg in session.added} == {9102}


def test_empty_selection_writes_nothing() -> None:
    session = _FakeSession(_customers(), configs={})
    result = bootstrap_p4_customer_configs(session, [])
    assert result["created_count"] == 0 and result["updated_count"] == 0
    assert session.added == []


def test_duplicate_ids_are_bootstrapped_once() -> None:
    session = _FakeSession(_customers(), configs={})
    result = bootstrap_p4_customer_configs(session, [9101, 9101, 9103])
    assert [c["customer_id"] for c in result["created"]] == [9101, 9103]


def test_missing_customer_is_reported_not_raised() -> None:
    session = _FakeSession(_customers([9101, 9102]), configs={})
    result = bootstrap_p4_customer_configs(session, SYNTH_IDS)
    assert result["missing_customer"] == [9103]
    assert result["created_count"] == 2


def test_customer_of_another_tenant_is_reported_missing_not_written() -> None:
    customers = _customers()
    customers[9103] = _customer(9103, tenant_id="other-tenant")
    session = _FakeSession(customers, configs={})
    result = bootstrap_p4_customer_configs(session, SYNTH_IDS)
    assert result["missing_customer"] == [9103]
    assert 9103 not in {c["customer_id"] for c in result["created"]}

    session2 = _FakeSession(customers, configs={})
    result2 = bootstrap_p4_customer_configs(session2, [9103], tenant_id="other-tenant")
    assert [c["customer_id"] for c in result2["created"]] == [9103]


def test_selected_customer_with_richer_config_is_skipped_never_overwritten() -> None:
    """Covers the old fixed-id exclusion: a graduated config is protected by data, not by id."""
    flat_cfg = CustomerReportConfig(
        customer_id=9101,
        reports_expected=True,
        expected_cadence="weekly",
        report_structure_type="flat",
        notes="already onboarded",
        feed_profile_json={"vat_basis": "inc_vat"},
    )
    vat_only_cfg = CustomerReportConfig(
        customer_id=9102,
        reports_expected=True,
        expected_cadence="monthly",
        report_structure_type=None,
        notes="vat basis known",
        feed_profile_json={"vat_basis": "ex_vat"},
    )
    session = _FakeSession(_customers(), configs={9101: flat_cfg, 9102: vat_only_cfg})
    result = bootstrap_p4_customer_configs(session, SYNTH_IDS)
    assert result["created_count"] == 1
    assert result["skipped_count"] == 2
    assert {s["customer_id"] for s in result["skipped"]} == {9101, 9102}
    assert {s["reason"] for s in result["skipped"]} == {"richer_config_present"}
    # Untouched — the original richer fields survive.
    assert flat_cfg.report_structure_type == "flat"
    assert flat_cfg.feed_profile_json == {"vat_basis": "inc_vat"}
    assert flat_cfg.notes == "already onboarded"
    assert vat_only_cfg.expected_cadence == "monthly"
    assert vat_only_cfg.feed_profile_json == {"vat_basis": "ex_vat"}
    assert flat_cfg not in session.added and vat_only_cfg not in session.added


def test_placeholder_config_without_richer_fields_is_refreshed() -> None:
    stale_placeholder = CustomerReportConfig(
        customer_id=9102,
        reports_expected=False,
        expected_cadence="weekly",
        report_structure_type=None,
        notes="stale note",
        feed_profile_json=None,
    )
    session = _FakeSession(_customers(), configs={9102: stale_placeholder})
    result = bootstrap_p4_customer_configs(session, SYNTH_IDS)
    assert result["updated_count"] == 1
    assert result["created_count"] == 2
    assert stale_placeholder.reports_expected is True
    assert stale_placeholder.notes == "P4 awaiting sample WEEK file (Q-004)"


# --- route and script contract -----------------------------------------------------------------


def test_route_requires_a_non_empty_customer_id_list_and_passes_caller_tenant(monkeypatch) -> None:
    from app.api.v1.endpoints import cst_steward
    from app.core.security import Role, get_current_user
    from app.main import app
    from fastapi.testclient import TestClient

    seen: dict = {}

    class _Ctx:
        def __enter__(self):
            return SimpleNamespace(commit=lambda: None)

        def __exit__(self, *exc):
            return False

    def fake_bootstrap(session, customer_ids, *, tenant_id=None):
        seen["ids"] = list(customer_ids)
        seen["tenant"] = tenant_id
        return {"ok": True}

    monkeypatch.setattr(cst_steward, "SessionLocal", lambda: _Ctx())
    monkeypatch.setattr(cst_steward, "bootstrap_p4_customer_configs", fake_bootstrap)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "w1d6-admin",
        "role": Role.ADMIN,
        "email": None,
        "tenant_id": "t-synth",
        "display_name": None,
    }
    try:
        client = TestClient(app)
        url = "/api/v1/cst-steward/p4-bootstrap-configs"
        assert client.post(url, json={}).status_code == 422
        assert client.post(url, json={"customer_ids": []}).status_code == 422
        r = client.post(url, json={"customer_ids": [9101, 9102]})
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert seen == {"ids": [9101, 9102], "tenant": "t-synth"}


def test_script_takes_customer_ids_on_the_command_line(monkeypatch) -> None:
    import importlib.util
    from pathlib import Path

    import pytest

    path = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_p4_cst_configs.py"
    spec = importlib.util.spec_from_file_location("bootstrap_p4_cst_configs_w1d6", path)
    script = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(script)

    calls: list[dict] = []
    monkeypatch.setattr(script, "run", lambda **kw: calls.append(kw) or {"ok": True})
    assert script.main(["--customer-id", "9101", "--customer-id", "9103"]) == 0
    assert calls == [{"customer_ids": [9101, 9103], "tenant_id": None, "confirm": False}]
    with pytest.raises(SystemExit):
        script.main([])
