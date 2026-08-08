"""P4 remaining customer configs bootstrap — mocked session, no DB writes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.customer_report_config import CustomerReportConfig
from app.models.dimensions import DimCustomer
from app.services.imports.cst_p4_customer_bootstrap import (
    P4_CUSTOMER_IDS,
    TAKEALOT_CUSTOMER_ID,
    bootstrap_p4_customer_configs,
)


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


def _customer(id_: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(id=id_, name=name)


def test_p4_roster_matches_expected_ids() -> None:
    assert P4_CUSTOMER_IDS == {
        52: "Evetech",
        18: "Computer Mania",
        12: "Incredible Connection",
        26: "Amazon",
        11: "Hifi",
        15: "Makro",
        57: "Game",
    }
    assert TAKEALOT_CUSTOMER_ID not in P4_CUSTOMER_IDS


def test_creates_placeholder_config_for_each_customer() -> None:
    customers = {cid: _customer(cid, name) for cid, name in P4_CUSTOMER_IDS.items()}
    session = _FakeSession(customers, configs={})
    result = bootstrap_p4_customer_configs(session)
    assert result["ok"] is True
    assert result["created_count"] == 7
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 0
    assert result["missing_customer"] == []
    created_ids = {c["customer_id"] for c in result["created"]}
    assert created_ids == set(P4_CUSTOMER_IDS)
    for cfg in session.added:
        assert cfg.reports_expected is True
        assert cfg.expected_cadence == "weekly"
        assert cfg.report_structure_type is None
        assert cfg.notes == "P4 awaiting sample WEEK file (Q-004)"
        assert cfg.feed_profile_json == {"status": "awaiting_sample_file", "pilot": "p4"}


def test_missing_customer_is_reported_not_raised() -> None:
    customers = {cid: _customer(cid, name) for cid, name in P4_CUSTOMER_IDS.items() if cid != 52}
    session = _FakeSession(customers, configs={})
    result = bootstrap_p4_customer_configs(session)
    assert 52 in result["missing_customer"]
    assert result["created_count"] == 6


def test_richer_existing_config_is_never_overwritten() -> None:
    customers = {cid: _customer(cid, name) for cid, name in P4_CUSTOMER_IDS.items()}
    richer_cfg = CustomerReportConfig(
        customer_id=18,
        reports_expected=True,
        expected_cadence="weekly",
        report_structure_type="flat",
        notes="already onboarded",
        feed_profile_json={"vat_basis": "inc_vat"},
    )
    session = _FakeSession(customers, configs={18: richer_cfg})
    result = bootstrap_p4_customer_configs(session)
    assert result["created_count"] == 6
    assert result["skipped_count"] == 1
    assert result["skipped"][0]["customer_id"] == 18
    assert result["skipped"][0]["reason"] == "richer_config_present"
    # Untouched — the original richer fields survive.
    assert richer_cfg.report_structure_type == "flat"
    assert richer_cfg.feed_profile_json == {"vat_basis": "inc_vat"}
    assert richer_cfg.notes == "already onboarded"


def test_placeholder_config_without_richer_fields_is_refreshed() -> None:
    customers = {cid: _customer(cid, name) for cid, name in P4_CUSTOMER_IDS.items()}
    stale_placeholder = CustomerReportConfig(
        customer_id=11,
        reports_expected=False,
        expected_cadence="weekly",
        report_structure_type=None,
        notes="stale note",
        feed_profile_json=None,
    )
    session = _FakeSession(customers, configs={11: stale_placeholder})
    result = bootstrap_p4_customer_configs(session)
    assert result["updated_count"] == 1
    assert result["created_count"] == 6
    assert stale_placeholder.reports_expected is True
    assert stale_placeholder.notes == "P4 awaiting sample WEEK file (Q-004)"


def test_takealot_never_touched_even_if_added_to_roster(monkeypatch) -> None:
    import app.services.imports.cst_p4_customer_bootstrap as mod

    monkeypatch.setattr(mod, "P4_CUSTOMER_IDS", {**P4_CUSTOMER_IDS, 20: "Takealot"})
    customers = {cid: _customer(cid, name) for cid, name in P4_CUSTOMER_IDS.items()}
    customers[20] = _customer(20, "Takealot")
    session = _FakeSession(customers, configs={})
    result = mod.bootstrap_p4_customer_configs(session)
    assert any(s["customer_id"] == 20 and s["reason"] == "takealot_never_touched" for s in result["skipped"])
    assert 20 not in {c["customer_id"] for c in result["created"]}
