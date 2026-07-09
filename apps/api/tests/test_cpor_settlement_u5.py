"""Unit tests for CPOR U5 claim evidence + settlement (no DB)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd

from app.services.cpor.claim_evidence import claim_evidence_source_key, resolve_claim_product_id
from app.services.cpor.claim_evidence_apply import parse_claim_evidence_dataframe
from app.services.cpor.waterfall import compute_ttl_result
from app.services.imports.distributor_sales_inventory import ProductResolutionIndex


def _idx(**kwargs) -> ProductResolutionIndex:
    base = dict(
        sku_to_id={},
        part_number_to_ids={},
        sales_model_name_to_ids={},
        model_name_to_ids={},
        marketing_name_to_ids={},
        ean_to_ids={},
        upc_to_ids={},
        alias_value_to_ids={},
        steward_alias_by_key={},
        products_by_id={},
    )
    base.update(kwargs)
    return ProductResolutionIndex(**base)


def test_claim_source_key_stable() -> None:
    a = claim_evidence_source_key(
        case_id=1,
        sale_date=date(2026, 1, 15),
        source_model_token="SKU-1",
        units=10,
        unit_price=None,
        row_ordinal=0,
    )
    b = claim_evidence_source_key(
        case_id=1,
        sale_date=date(2026, 1, 15),
        source_model_token="sku-1",
        units=10,
        row_ordinal=0,
    )
    assert a == b
    assert a.startswith("cpor-claim|1|")


def test_resolve_item_then_ean_then_sales_model() -> None:
    idx = _idx(
        sku_to_id={"sku-a": 10},
        ean_to_ids={"600123": (20,)},
        sales_model_name_to_ids={"model-x": (30,)},
    )
    pid, tok, st = resolve_claim_product_id(idx, item_code="SKU-A")
    assert (pid, st) == (10, "resolved")
    pid, tok, st = resolve_claim_product_id(idx, ean="600123")
    assert (pid, st) == (20, "resolved")
    pid, tok, st = resolve_claim_product_id(idx, sales_model="MODEL-X")
    assert (pid, st) == (30, "resolved")
    pid, tok, st = resolve_claim_product_id(idx, item_code="NOPE")
    assert st == "unresolved" and pid is None


def test_ambiguous_ean_flags() -> None:
    idx = _idx(ean_to_ids={"600123": (1, 2)})
    pid, _, st = resolve_claim_product_id(idx, ean="600123")
    assert pid is None and st == "ambiguous"


def test_parse_claim_dataframe() -> None:
    df = pd.DataFrame(
        [
            {"sku": "A", "sale_date": "2026-01-10", "units": 5},
            {"sku": "B", "sale_date": "2026-01-11", "units": 2, "unit_price": 9.5},
        ]
    )
    rows, errs = parse_claim_evidence_dataframe(df)
    assert errs == []
    assert len(rows) == 2
    assert rows[0]["source_model_token"] == "A"
    assert rows[0]["units"] == 5.0


def test_ttl_result_uncapped_by_estimate() -> None:
    # Spec fixture spirit: result 49 * support_unit — not capped by estimate 20
    support_unit = Decimal("250.963265306122")
    ttl = compute_ttl_result(support_unit, 49)
    assert ttl is not None
    assert ttl > support_unit * Decimal("20")


def test_rollup_sets_result_qty(monkeypatch) -> None:
    from app.services.cpor import settlement as st

    case = SimpleNamespace(
        id=1,
        window_start=date(2026, 1, 1),
        window_end=date(2026, 1, 31),
        customer_id=5,
        status="ended",
    )
    line = SimpleNamespace(id=9, case_id=1, product_id=100, estimate_qty=20, result_qty=None, support_unit=10)
    claim = SimpleNamespace(
        case_id=1,
        product_id=100,
        sale_date=date(2026, 1, 15),
        units=49,
        source_model_token="A",
        raw_source_row={"_cpor_flags": {"out_of_window": False}},
    )

    session = MagicMock()
    session.get.return_value = case

    def _scalars(stmt):
        m = MagicMock()
        # first call claims, second lines — detect by string
        sql = str(stmt)
        if "cpor_claim_evidence" in sql.lower() or "CporClaimEvidenceLine" in sql:
            m.all.return_value = [claim]
        else:
            m.all.return_value = [line]
        return m

    # session.scalars returns different things; simplify with side_effect list
    session.scalars.side_effect = [
        MagicMock(all=MagicMock(return_value=[claim])),
        MagicMock(all=MagicMock(return_value=[line])),
    ]

    recomputed = []

    def _recompute(session, line, **kwargs):
        recomputed.append(line.result_qty)

    monkeypatch.setattr(st, "recompute_case_line", _recompute)
    out = st.rollup_result_qty_from_claims(session, 1)
    assert out["lines_updated"] == 1
    assert line.result_qty == 49.0
    assert recomputed == [49.0]
