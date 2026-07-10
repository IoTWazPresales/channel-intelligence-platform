"""Unit tests for the PO Management surface (Session C Unit 3). Mock-based."""
import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock

from app.services.commercial_planner import po_management as mod


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _R:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)

    def scalars(self):
        return _Scalars(self._rows)


def _db(results):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(results))
    return db


def test_shipment_quantity_source_is_fact_layer():
    assert mod.SHIPMENT_QUANTITY_SOURCE == "fact_inbound_shipment"


def test_coverage_first_run_groups_by_quarter_and_product_line():
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 2, 15))]),  # observed shipment aggregate
        _R([(10, "Laptops", "PC")]),                            # product line
        _R([(10, 18.5)]),                                       # fx
        _R([]),                                                 # linked po ids -> none (first run)
    ]
    out = asyncio.run(mod.coverage(_db(results)))
    assert out["data_unavailable"] is False
    assert out["total_pos_observed"] == 1
    assert out["total_pos_linked"] == 0
    assert out["first_run"] is True
    g = out["groups"][0]
    assert g["product_line"] == "Laptops"
    assert g["quarter_label"] == "26Q1"
    assert g["shipped_units"] == 100.0
    assert g["shipped_value_plan"] == 1000.0 * 18.5
    assert g["fx_complete"] is True


def test_coverage_fx_partial_when_assumption_missing():
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 2, 15))]),
        _R([(10, "Laptops", "PC")]),
        _R([]),  # no fx assumption
        _R([]),  # linked
    ]
    out = asyncio.run(mod.coverage(_db(results)))
    assert out["groups"][0]["fx_complete"] is False


def test_backlog_unlinked_group_has_upload_prompt():
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 2, 15))]),  # observed
        _R([(10, "Laptops", "PC")]),                            # product line
        _R([(10, 18.5)]),                                       # fx
        _R([]),                                                 # linked po ids
        _R([]),                                                 # active lineup coverage keys
        _R([]),                                                 # case links
    ]
    out = asyncio.run(mod.backlog(_db(results)))
    g = out["groups"][0]
    assert g["status"] == "unlinked"
    assert g["upload_prompt"]["product_line"] == "Laptops"
    assert g["upload_prompt"]["period_label"] == "26Q1"


def test_backlog_suppresses_upload_prompt_when_active_lineup_exists(monkeypatch):
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 4, 20))]),
        _R([(10, "Laptops", "PC")]),
        _R([(10, 18.5)]),
        _R([]),
        _R([]),
        _R([]),
    ]
    db = _db(results)

    async def _fake_coverage_state(_db):
        return {(2026, 2, "Laptops")}, set()

    monkeypatch.setattr(mod, "_lineup_coverage_state", _fake_coverage_state)
    out = asyncio.run(mod.backlog(db))
    g = out["groups"][0]
    assert g["status"] == "unlinked"
    assert g.get("lineup_case_exists") is True
    assert "upload_prompt" not in g


def test_backlog_parse_incomplete_not_upload_prompt(monkeypatch):
    results = [
        _R([(500, 10, 100.0, 1000.0, dt.date(2026, 4, 20))]),
        _R([(10, "Laptops", "PC")]),
        _R([(10, 18.5)]),
        _R([]),
        _R([]),
        _R([]),
    ]
    db = _db(results)

    async def _fake_coverage_state(_db):
        return set(), {(2026, 2, "Laptops")}

    monkeypatch.setattr(mod, "_lineup_coverage_state", _fake_coverage_state)
    out = asyncio.run(mod.backlog(db))
    g = out["groups"][0]
    assert g.get("parse_incomplete") is True
    assert "upload_prompt" not in g
    assert g.get("lineup_case_exists") is not True


def test_project_reconciliation_partitions_multi_bu_case():
    recon = {
        "products": [
            {
                "customer_id": 1,
                "product_line": "NV",
                "business_unit": "NV",
                "units_flag": "matched",
                "awaiting_po": False,
            },
            {
                "customer_id": 1,
                "product_line": "NR",
                "business_unit": "NR",
                "units_flag": "short",
                "awaiting_po": True,
            },
            {
                "customer_id": 2,
                "product_line": "NV",
                "business_unit": "NV",
                "units_flag": "unshipped",
                "awaiting_po": False,
            },
        ],
        "customers": [
            {"customer_id": 1, "label": "Customer A", "awaiting_po": True},
            {"customer_id": 2, "label": "Customer B", "awaiting_po": False},
        ],
        "po_flags": [],
    }
    nv = mod.project_reconciliation_for_product_line(recon, group_product_line="NV")
    nr = mod.project_reconciliation_for_product_line(recon, group_product_line="NR")
    assert nv["summary"]["matched"] == 1
    assert nv["summary"]["unshipped"] == 1
    assert nv["summary"]["short"] == 0
    assert nr["summary"]["short"] == 1
    assert nr["summary"]["matched"] == 0
    assert nv["summary"] != nr["summary"]
    nv_c1 = next(c for c in nv["customers"] if c["customer_id"] == 1)
    assert nv_c1["awaiting_po"] is False
    nr_c1 = next(c for c in nr["customers"] if c["customer_id"] == 1)
    assert nr_c1["awaiting_po"] is True


def test_project_reconciliation_single_bu_unchanged():
    recon = {
        "products": [
            {"customer_id": 1, "product_line": "NB", "business_unit": "NB", "units_flag": "matched", "awaiting_po": False},
            {"customer_id": 1, "product_line": "NB", "business_unit": "NB", "units_flag": "short", "awaiting_po": False},
        ],
        "customers": [{"customer_id": 1, "label": "Makro", "awaiting_po": False}],
        "po_flags": [],
    }
    nb = mod.project_reconciliation_for_product_line(recon, group_product_line="NB")
    assert nb["summary"]["matched"] == 1
    assert nb["summary"]["short"] == 1
    assert len(nb["customers"]) == 1
    assert nb["customers"][0]["summary"]["matched"] == 1


def test_project_reconciliation_uses_business_unit_when_product_line_null():
    recon = {
        "products": [
            {"customer_id": 1, "product_line": None, "business_unit": "NX", "units_flag": "over", "awaiting_po": False},
        ],
        "customers": [{"customer_id": 1, "label": "X", "awaiting_po": False}],
        "po_flags": [],
    }
    nx = mod.project_reconciliation_for_product_line(recon, group_product_line="NX")
    nv = mod.project_reconciliation_for_product_line(recon, group_product_line="NV")
    assert nx["summary"]["over"] == 1
    assert nv["summary"]["over"] == 0


def test_backlog_linked_group_projects_by_product_line(monkeypatch):
    results = [
        _R([
            (500, 10, 100.0, 1000.0, dt.date(2026, 4, 20)),
            (500, 11, 50.0, 500.0, dt.date(2026, 4, 20)),
        ]),
        _R([(10, "NV", "NV"), (11, "NR", "NR")]),
        _R([(10, 18.5), (11, 18.5)]),
        _R([500]),  # linked po ids (scalars)
        _R([]),  # lineup coverage
        _R([(500, 42)]),  # case links
    ]
    db = _db(results)

    async def _fake_reconcile(_db, case_id):
        return {
            "products": [
                {"customer_id": 1, "product_line": "NV", "business_unit": "NV", "units_flag": "matched", "awaiting_po": False},
                {"customer_id": 1, "product_line": "NR", "business_unit": "NR", "units_flag": "short", "awaiting_po": True},
            ],
            "customers": [{"customer_id": 1, "label": "A", "awaiting_po": True}],
            "summary": {"matched": 1, "short": 1, "over": 0, "unshipped": 0, "unplanned": 0, "amended": 0, "po_no_match": 0},
            "po_flags": [],
        }

    monkeypatch.setattr(mod, "reconcile_case", _fake_reconcile)
    out = asyncio.run(mod.backlog(db))
    linked = [g for g in out["groups"] if g["status"] == "linked"]
    assert len(linked) == 2
    by_line = {g["product_line"]: g for g in linked}
    assert by_line["NV"]["reconciliation_summary"]["matched"] == 1
    assert by_line["NV"]["reconciliation_summary"]["short"] == 0
    assert by_line["NR"]["reconciliation_summary"]["short"] == 1
    assert by_line["NR"]["reconciliation_summary"]["matched"] == 0
