"""T1a: batched PO reconciliation (`reconcile_cases`) - identical output, bounded query count.

Pure unit tests (mock session, no database). The golden payload below was produced by the
per-case implementation that existed before batching, from the same fixture rows, so the batched
path is proven to return exactly what the old path returned.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.services.commercial_planner import lineup_po_reconciliation as mod

_GOLDEN_OLD_PATH_JSON = (
    '{"case_id":1,"commercial_status":"po_issued","customers":[{"awaiting_po":false,"customer'
    '_id":90,"label":"Open Channel","products":[{"awaiting_po":false,"business_unit":"Display'
    '","customer_id":90,"pipeline_units":0.0,"planned_units":0.0,"product_id":40,"product_lin'
    'e":"Monitors","product_name":"Prod 40","shipped_units":7.0,"units_flag":"unplanned","val'
    'ue":{"fx_plan_per_cost":null,"planned_value_plan":0.0,"shipped_value_cost":70.0,"shipped'
    '_value_plan":null,"value_status":"fx_unavailable","variance_plan":null},"warnings":[]},{'
    '"awaiting_po":false,"business_unit":"PC","customer_id":90,"pipeline_units":0.0,"planned_'
    'units":8.0,"product_id":60,"product_line":"Laptops","product_name":"Prod 60","shipped_un'
    'its":8.0,"units_flag":"matched","value":{"fx_plan_per_cost":null,"planned_value_plan":40'
    '.0,"shipped_value_cost":80.0,"shipped_value_plan":null,"value_status":"fx_unavailable","'
    'variance_plan":null},"warnings":[]}],"summary":{"amended":0,"matched":1,"over":0,"po_no_'
    'match":0,"short":0,"unplanned":1,"unshipped":0}},{"awaiting_po":false,"customer_id":101,'
    '"label":"Customer A","products":[{"awaiting_po":false,"business_unit":"PC","customer_id"'
    ':101,"pipeline_units":15.0,"planned_units":120.0,"product_id":10,"product_line":"Laptops'
    '","product_name":"Prod 10","shipped_units":120.0,"units_flag":"matched","value":{"fx_pla'
    'n_per_cost":18.5,"planned_value_plan":6000.0,"shipped_value_cost":1200.0,"shipped_value_'
    'plan":22200.0,"value_status":"ok","variance_plan":16200.0},"warnings":[]},{"awaiting_po"'
    ':false,"business_unit":"PC","customer_id":101,"pipeline_units":0.0,"planned_units":0.0,"'
    'product_id":50,"product_line":"Laptops","product_name":"Prod 50","shipped_units":9.0,"un'
    'its_flag":"amended","value":{"fx_plan_per_cost":null,"planned_value_plan":0.0,"shipped_v'
    'alue_cost":90.0,"shipped_value_plan":null,"value_status":"fx_unavailable","variance_plan'
    '":null},"warnings":[]}],"summary":{"amended":1,"matched":1,"over":0,"po_no_match":0,"sho'
    'rt":0,"unplanned":0,"unshipped":0}},{"awaiting_po":false,"customer_id":102,"label":"Cust'
    'omer B","products":[{"awaiting_po":false,"business_unit":"PC","customer_id":102,"pipelin'
    'e_units":5.0,"planned_units":50.0,"product_id":20,"product_line":"Laptops","product_name'
    '":"Prod 20","shipped_units":20.0,"units_flag":"short","value":{"fx_plan_per_cost":18.0,"'
    'planned_value_plan":2500.0,"shipped_value_cost":200.0,"shipped_value_plan":3600.0,"value'
    '_status":"ok","variance_plan":1100.0},"warnings":["UoM mismatch risk: lineup base '
    'unit(s) [\'box\'] for product 20 are not \'eaches\'; shipment quantity is summed as eaches."'
    ']}],"summary":{"amended":0,"matched":0,"over":0,"po_no_match":0,"short":1,"unplanned":0,'
    '"unshipped":0}},{"awaiting_po":true,"customer_id":103,"label":"Customer #103","products"'
    ':[{"awaiting_po":true,"business_unit":"PC","customer_id":103,"pipeline_units":0.0,"plann'
    'ed_units":10.0,"product_id":30,"product_line":"Laptops","product_name":"Prod 30","shippe'
    'd_units":0.0,"units_flag":null,"value":{"fx_plan_per_cost":null,"planned_value_plan":50.'
    '0,"shipped_value_cost":0.0,"shipped_value_plan":null,"value_status":"fx_unavailable","va'
    'riance_plan":null},"warnings":[]}],"summary":{"amended":0,"matched":0,"over":0,"po_no_ma'
    'tch":0,"short":0,"unplanned":0,"unshipped":0}},{"awaiting_po":false,"customer_id":null,"'
    'label":"Unattributed","products":[{"awaiting_po":false,"business_unit":"PC","customer_id'
    '":null,"pipeline_units":0.0,"planned_units":0.0,"product_id":10,"product_line":"Laptops"'
    ',"product_name":"Prod 10","shipped_units":3.0,"units_flag":"amended","value":{"fx_plan_p'
    'er_cost":18.5,"planned_value_plan":0.0,"shipped_value_cost":30.0,"shipped_value_plan":55'
    '5.0,"value_status":"ok","variance_plan":555.0},"warnings":[]},{"awaiting_po":false,"busi'
    'ness_unit":"PC","customer_id":null,"pipeline_units":0.0,"planned_units":4.0,"product_id"'
    ':70,"product_line":"Laptops","product_name":"Prod 70","shipped_units":0.0,"units_flag":"'
    'unshipped","value":{"fx_plan_per_cost":null,"planned_value_plan":8.0,"shipped_value_cost'
    '":0.0,"shipped_value_plan":null,"value_status":"fx_unavailable","variance_plan":null},"w'
    'arnings":[]}],"summary":{"amended":1,"matched":0,"over":0,"po_no_match":0,"short":0,"unp'
    'lanned":0,"unshipped":1}}],"data_unavailable":false,"linked_po_count":3,"plan_currency":'
    '"ZAR","po_flags":[{"flag":"po_no_match","po_number_raw":"PO-3","purchase_order_id":502}]'
    ',"products":[{"awaiting_po":false,"business_unit":"Display","customer_id":90,"pipeline_u'
    'nits":0.0,"planned_units":0.0,"product_id":40,"product_line":"Monitors","product_name":"'
    'Prod 40","shipped_units":7.0,"units_flag":"unplanned","value":{"fx_plan_per_cost":null,"'
    'planned_value_plan":0.0,"shipped_value_cost":70.0,"shipped_value_plan":null,"value_statu'
    's":"fx_unavailable","variance_plan":null},"warnings":[]},{"awaiting_po":false,"business_'
    'unit":"PC","customer_id":90,"pipeline_units":0.0,"planned_units":8.0,"product_id":60,"pr'
    'oduct_line":"Laptops","product_name":"Prod 60","shipped_units":8.0,"units_flag":"matched'
    '","value":{"fx_plan_per_cost":null,"planned_value_plan":40.0,"shipped_value_cost":80.0,"'
    'shipped_value_plan":null,"value_status":"fx_unavailable","variance_plan":null},"warnings'
    '":[]},{"awaiting_po":false,"business_unit":"PC","customer_id":101,"pipeline_units":15.0,'
    '"planned_units":120.0,"product_id":10,"product_line":"Laptops","product_name":"Prod 10",'
    '"shipped_units":120.0,"units_flag":"matched","value":{"fx_plan_per_cost":18.5,"planned_v'
    'alue_plan":6000.0,"shipped_value_cost":1200.0,"shipped_value_plan":22200.0,"value_status'
    '":"ok","variance_plan":16200.0},"warnings":[]},{"awaiting_po":false,"business_unit":"PC"'
    ',"customer_id":101,"pipeline_units":0.0,"planned_units":0.0,"product_id":50,"product_lin'
    'e":"Laptops","product_name":"Prod 50","shipped_units":9.0,"units_flag":"amended","value"'
    ':{"fx_plan_per_cost":null,"planned_value_plan":0.0,"shipped_value_cost":90.0,"shipped_va'
    'lue_plan":null,"value_status":"fx_unavailable","variance_plan":null},"warnings":[]},{"aw'
    'aiting_po":false,"business_unit":"PC","customer_id":102,"pipeline_units":5.0,"planned_un'
    'its":50.0,"product_id":20,"product_line":"Laptops","product_name":"Prod 20","shipped_uni'
    'ts":20.0,"units_flag":"short","value":{"fx_plan_per_cost":18.0,"planned_value_plan":2500'
    '.0,"shipped_value_cost":200.0,"shipped_value_plan":3600.0,"value_status":"ok","variance_'
    'plan":1100.0},"warnings":["UoM mismatch risk: lineup base unit(s) [\'box\'] for product 20'
    ' are not \'eaches\'; shipment quantity is summed as eaches."]},{"awaiting_po":true,"busine'
    'ss_unit":"PC","customer_id":103,"pipeline_units":0.0,"planned_units":10.0,"product_id":3'
    '0,"product_line":"Laptops","product_name":"Prod 30","shipped_units":0.0,"units_flag":nul'
    'l,"value":{"fx_plan_per_cost":null,"planned_value_plan":50.0,"shipped_value_cost":0.0,"s'
    'hipped_value_plan":null,"value_status":"fx_unavailable","variance_plan":null},"warnings"'
    ':[]},{"awaiting_po":false,"business_unit":"PC","customer_id":null,"pipeline_units":0.0,"'
    'planned_units":0.0,"product_id":10,"product_line":"Laptops","product_name":"Prod 10","sh'
    'ipped_units":3.0,"units_flag":"amended","value":{"fx_plan_per_cost":18.5,"planned_value_'
    'plan":0.0,"shipped_value_cost":30.0,"shipped_value_plan":555.0,"value_status":"ok","vari'
    'ance_plan":555.0},"warnings":[]},{"awaiting_po":false,"business_unit":"PC","customer_id"'
    ':null,"pipeline_units":0.0,"planned_units":4.0,"product_id":70,"product_line":"Laptops",'
    '"product_name":"Prod 70","shipped_units":0.0,"units_flag":"unshipped","value":{"fx_plan_'
    'per_cost":null,"planned_value_plan":8.0,"shipped_value_cost":0.0,"shipped_value_plan":nu'
    'll,"value_status":"fx_unavailable","variance_plan":null},"warnings":[]}],"summary":{"ame'
    'nded":2,"matched":2,"over":0,"po_no_match":1,"short":1,"unplanned":1,"unshipped":1}}'
)


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _R:
    def __init__(self, rows=(), scalar_rows=None, scalar_one=None):
        self._rows = list(rows)
        self._scalar = list(scalar_rows) if scalar_rows is not None else list(rows)
        self._scalar_one = scalar_one

    def all(self):
        return list(self._rows)

    def scalars(self):
        return _Scalars(self._scalar)

    def scalar_one_or_none(self):
        return self._scalar_one


def _case(case_id=1, product_line="Laptops"):
    return SimpleNamespace(
        id=case_id,
        commercial_status="po_issued",
        currency_code="ZAR",
        product_line=product_line,
    )


def _line(case_id, cust, pid, qty, dap, unit="ea"):
    return SimpleNamespace(
        case_id=case_id,
        product_id=pid,
        customer_id=cust,
        quantity_units=qty,
        dap_evidence_local=dap,
        base_unit_raw=unit,
        raw_row_payload={},
    )


def _batch_results(
    cases,
    *,
    po_links=(),
    lines=(),
    shipped=(),
    pipeline=(),
    resolved=(),
    po_shipped=(),
    meta=(),
    fx=(),
    names=(),
    canonical=None,
    aliases=(),
):
    """Execute() results in the fixed batched query order.

    Row shapes: po_links (case_id, po_id, raw, norm); shipped (case_id, cust, pid, units, value);
    pipeline (case_id, cust, pid, units); resolved (case_id, cust); po_shipped (case_id, po_id).
    The evidence queries (shipped/pipeline/resolved/po_shipped) only run when a PO link exists;
    the product/fx/customer lookups only run when some product is in play.
    """
    out = [
        _R(scalar_rows=cases),  # cases
        _R(scalar_one=canonical),  # open-channel canonical id
        _R(scalar_rows=list(aliases)),  # open-channel alias ids
        _R(po_links),  # (case_id, po_id, raw, norm)
        _R(scalar_rows=lines),  # lineup lines
    ]
    if po_links:
        out += [_R(shipped), _R(pipeline), _R(resolved), _R(po_shipped)]
    if lines or shipped:
        out += [_R(meta), _R(fx), _R(names)]
    return out


def _db(results):
    db = MagicMock()
    db.get = AsyncMock(side_effect=AssertionError("per-case db.get must not be used"))
    db.execute = AsyncMock(side_effect=list(results))
    return db


# ---- golden: identical to the pre-batching per-case path ------------------------------------

_GOLDEN_LINES = [
    (101, 10, 100, 50),
    (101, 10, 20, 50),
    (102, 20, 50, 50, "box"),
    (91, 60, 8, 5),
    (103, 30, 10, 5),
    (None, 70, 4, 2),
]
_GOLDEN_SHIPPED = [
    (101, 10, 120, 1200.0),
    (102, 20, 20, 200.0),
    (91, 40, 7, 70.0),
    (101, 50, 9, 90.0),
    (None, 10, 3, 30.0),
    (91, 60, 8, 80.0),
]
_GOLDEN_META = [
    (10, "Prod 10", "Laptops", "PC"),
    (20, "Prod 20", "Laptops", "PC"),
    (30, "Prod 30", "Laptops", "PC"),
    (40, "Prod 40", "Monitors", "Display"),
    (50, "Prod 50", "Laptops", "PC"),
    (60, "Prod 60", "Laptops", "PC"),
    (70, "Prod 70", "Laptops", "PC"),
]


def _golden_results(case):
    lines = [_line(1, *row) for row in _GOLDEN_LINES]
    return _batch_results(
        [case],
        po_links=[(1, 500, "PO-1", "1"), (1, 501, None, "2"), (1, 502, "PO-3", "3")],
        lines=lines,
        shipped=[(1, *row) for row in _GOLDEN_SHIPPED],
        pipeline=[(1, 101, 10, 15.0), (1, 102, 20, 5.0)],
        resolved=[(1, 101), (1, 102), (1, 91)],
        po_shipped=[(1, 500), (1, 501)],
        meta=_GOLDEN_META,
        fx=[(10, 18.5), (20, 18.0)],
        names=[(101, "Customer A"), (102, "Customer B"), (90, "Open Channel")],
        canonical=90,
        aliases=[91],
    )


def test_reconcile_case_matches_old_path_golden():
    out = asyncio.run(mod.reconcile_case(_db(_golden_results(_case())), 1))
    assert json.loads(json.dumps(out)) == json.loads(_GOLDEN_OLD_PATH_JSON)


def test_reconcile_cases_matches_old_path_golden():
    out = asyncio.run(mod.reconcile_cases(_db(_golden_results(_case())), [1]))
    assert set(out) == {1}
    assert json.loads(json.dumps(out[1])) == json.loads(_GOLDEN_OLD_PATH_JSON)


# ---- multi-case isolation and bounded query count -------------------------------------------

_PO_LINKS = [(1, 500, "PO-A", "a"), (2, 500, "PO-A", "a"), (2, 600, "PO-B", "b")]
_SHIPPED = [(1, 5, 10, 60.0, 600.0), (2, 7, 11, 40.0, 400.0)]
_PIPELINE = [(1, 5, 10, 40.0)]
_RESOLVED = [(1, 5), (2, 7)]
_PO_SHIPPED = [(1, 500), (2, 500)]
_META = [(10, "P10", "Laptops", "PC"), (11, "P11", "Monitors", "Display")]
_FX = [(10, 2.0), (11, 2.0)]
_NAMES = [(5, "Cust 5"), (7, "Cust 7")]


def _lines():
    return [_line(1, 5, 10, 100, 2.0), _line(2, 7, 11, 40, 3.0)]


def _two_case_results(only=None):
    """Both cases (PO 500 shared; PO 600 only on case 2), or just the rows of ``only``."""
    cases = [_case(1), _case(2, product_line="Monitors")]

    def keep(rows, idx=0):
        return [r for r in rows if only is None or (getattr(r, "case_id", None) or r[idx]) == only]

    if only is not None:
        cases = [c for c in cases if c.id == only]
    return cases, _batch_results(
        cases,
        po_links=keep(_PO_LINKS),
        lines=[ln for ln in _lines() if only is None or ln.case_id == only],
        shipped=keep(_SHIPPED),
        pipeline=keep(_PIPELINE),
        resolved=keep(_RESOLVED),
        po_shipped=keep(_PO_SHIPPED),
        meta=_META,
        fx=_FX,
        names=_NAMES,
    )


def test_two_cases_sharing_a_po_are_reconciled_independently():
    _cases, results = _two_case_results()
    out = asyncio.run(mod.reconcile_cases(_db(results), [1, 2]))
    assert set(out) == {1, 2}
    one, two = out[1], out[2]
    assert one["case_id"] == 1 and two["case_id"] == 2
    assert one["linked_po_count"] == 1 and two["linked_po_count"] == 2
    assert one["summary"]["short"] == 1 and one["summary"]["po_no_match"] == 0
    assert two["summary"]["matched"] == 1 and two["summary"]["po_no_match"] == 1
    assert [p["pipeline_units"] for p in one["products"]] == [40.0]
    assert [p["pipeline_units"] for p in two["products"]] == [0.0]
    assert [f["purchase_order_id"] for f in two["po_flags"]] == [600]
    assert one["po_flags"] == []


def test_batch_equals_per_case_calls():
    _cases, results = _two_case_results()
    batch = asyncio.run(mod.reconcile_cases(_db(results), [1, 2]))
    for case_id in (1, 2):
        _c, single_results = _two_case_results(only=case_id)
        assert batch[case_id] == asyncio.run(mod.reconcile_case(_db(single_results), case_id))


def _n_case_results(n):
    ids = range(1, n + 1)
    return _batch_results(
        [_case(i) for i in ids],
        po_links=[(i, 1000 + i, f"PO-{i}", str(i)) for i in ids],
        lines=[_line(i, 5, 10, 100, 2.0) for i in ids],
        shipped=[(i, 5, 10, 60.0, 600.0) for i in ids],
        resolved=[(i, 5) for i in ids],
        po_shipped=[(i, 1000 + i) for i in ids],
        meta=[(10, "P10", "Laptops", "PC")],
        fx=[(10, 2.0)],
        names=[(5, "Cust 5")],
    )


@pytest.mark.parametrize("n", [1, 5, 40])
def test_query_count_is_fixed_regardless_of_case_count(n):
    db = _db(_n_case_results(n))
    out = asyncio.run(mod.reconcile_cases(db, list(range(1, n + 1))))
    assert set(out) == set(range(1, n + 1))
    assert db.execute.await_count == 12  # same for 1, 5 and 40 cases
    db.get.assert_not_called()


def test_empty_and_duplicate_ids():
    db = _db([])
    assert asyncio.run(mod.reconcile_cases(db, [])) == {}
    assert db.execute.await_count == 0
    _cases, results = _two_case_results()
    out = asyncio.run(mod.reconcile_cases(_db(results), [1, 2, 2, 1]))
    assert set(out) == {1, 2}


def test_unknown_case_ids_are_omitted_and_single_raises():
    out = asyncio.run(mod.reconcile_cases(_db(_batch_results([_case(1)])), [1, 999]))
    assert set(out) == {1}
    with pytest.raises(mod.CaseNotFoundError):
        asyncio.run(mod.reconcile_case(_db(_batch_results([])), 999))


def test_query_failure_yields_data_unavailable_for_every_case():
    cases = [_case(1), _case(2)]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[_R(scalar_rows=cases), RuntimeError("boom")])
    out = asyncio.run(mod.reconcile_cases(db, [1, 2]))
    assert set(out) == {1, 2}
    for cid in (1, 2):
        assert out[cid]["data_unavailable"] is True
        assert out[cid]["case_id"] == cid
        assert out[cid]["summary"] == {f: 0 for f in mod.UNITS_FLAGS}
