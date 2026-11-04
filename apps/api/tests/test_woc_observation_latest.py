"""The latest cover read picks one row per pair with a narrow lateral lookup."""

from __future__ import annotations

from sqlalchemy.dialects import postgresql

from app.services.woc_observation_read import latest_woc_observation_stmt


def _sql(**kwargs: object) -> str:
    stmt = latest_woc_observation_stmt(tenant_id="default", **kwargs)  # type: ignore[arg-type]
    return str(stmt.compile(dialect=postgresql.dialect()))


def test_latest_read_is_a_lateral_limit_not_a_wide_distinct_on() -> None:
    sql = _sql()
    assert "LATERAL" in sql
    assert "LIMIT" in sql
    assert "DISTINCT ON" not in sql
    assert "woc_pairs" in sql


def test_latest_read_keeps_distributor_and_product_filters_on_the_pair_list() -> None:
    sql = _sql(distributor_id=7, product_id=99)
    assert "distributor_id" in sql
    assert "product_id" in sql
