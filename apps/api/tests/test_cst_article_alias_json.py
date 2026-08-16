"""CST article-alias list payload: sales model from DimProduct, search across article/model."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql

from app.api.v1.endpoints.cst_steward import _alias_json, article_alias_q_match


def test_alias_json_includes_sales_model_from_product_not_alias_row():
    row = SimpleNamespace(
        id=9,
        customer_id=4,
        article_no_normalized="B0TESTASIN",
        product_id=88,
        status="proposed",
        valid_from=None,
        valid_to=None,
        evidence_json={"sales_model_name": "ignored-evidence-copy"},
        updated_at=datetime(2026, 8, 16, tzinfo=timezone.utc),
    )
    cust = SimpleNamespace(code="AMZ", name="Amazon")
    prod = SimpleNamespace(sku="90NB12", name="Notebook", sales_model_name="Vivobook 16")

    out = _alias_json(row, cust, prod)

    assert out["sales_model_name"] == "Vivobook 16"
    assert out["product_sku"] == "90NB12"
    assert out["article_no_normalized"] == "B0TESTASIN"
    assert out["product_id"] == 88
    assert "ignored-evidence-copy" not in (out["sales_model_name"] or "")


def test_alias_json_sales_model_none_when_product_missing():
    row = SimpleNamespace(
        id=1,
        customer_id=1,
        article_no_normalized="X",
        product_id=2,
        status="confirmed",
        valid_from=None,
        valid_to=None,
        evidence_json=None,
        updated_at=None,
    )
    out = _alias_json(row, None, None)
    assert out["sales_model_name"] is None
    assert out["product_sku"] is None


def test_alias_search_clause_covers_article_sales_model_sku_and_customer():
    compiled = str(
        article_alias_q_match("vivobook").compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "article_no_normalized" in compiled
    assert "sales_model_name" in compiled
    assert "sku" in compiled.lower() or "dim_product" in compiled.lower()
    assert "vivobook" in compiled.lower()
