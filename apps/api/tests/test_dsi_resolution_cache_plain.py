"""DSIResolutionCache must hold detached plain rows — never Session-bound ORM instances."""

from __future__ import annotations

from app.db.session_sync import SessionLocal
from app.services.imports.distributor_sales_inventory import (
    DSIResolutionCache,
    DSIResolutionCustAliasRow,
    DSIResolutionDistAliasRow,
    DSIResolutionCustomerRow,
    DSIResolutionDistributorRow,
    _build_resolution_cache,
    _resolve_customer_from_cache,
    _resolve_distributor_from_cache,
)
from app.services.imports.source_token_alias_conflicts import customer_alias_conflict_reason_from_cache


def test_build_resolution_cache_returns_only_plain_rows() -> None:
    with SessionLocal() as db:
        cache = _build_resolution_cache(db, None)
    assert isinstance(cache, DSIResolutionCache)
    for row in cache.all_distributors:
        assert isinstance(row, DSIResolutionDistributorRow)
    for row in cache.dist_aliases:
        assert isinstance(row, DSIResolutionDistAliasRow)
    for row in cache.all_customers:
        assert isinstance(row, DSIResolutionCustomerRow)
    for row in cache.cust_aliases:
        assert isinstance(row, DSIResolutionCustAliasRow)


def test_resolution_cache_survives_session_commit_without_db_access(monkeypatch) -> None:
    cache = DSIResolutionCache(
        all_distributors=[DSIResolutionDistributorRow(id=1, code="dist-01", name="Dist One")],
        dist_aliases=[
            DSIResolutionDistAliasRow(normalized_token="dist01", source_definition_id=None, distributor_id=1),
        ],
        all_customers=[DSIResolutionCustomerRow(id=10, code="cust-01", name="Cust One")],
        customer_code_to_id={"cust-01": 10},
        customer_name_to_ids={"cust one": [10]},
        cust_aliases=[
            DSIResolutionCustAliasRow(
                normalized_token="cust01", source_definition_id=None, distributor_id=1, customer_id=10
            ),
        ],
        open_channel_cid=None,
    )
    with SessionLocal() as db:
        db.commit()

        def _fail_db(*_args, **_kwargs):
            raise AssertionError("cache access must not query DB after commit")

        monkeypatch.setattr(db, "execute", _fail_db)
        monkeypatch.setattr(db, "scalar", _fail_db)
        monkeypatch.setattr(db, "scalars", _fail_db)

        _ = cache.dist_aliases[0].normalized_token
        _ = cache.cust_aliases[0].customer_id
        _ = cache.all_distributors[0].name
        did, _ = _resolve_distributor_from_cache("dist-01", None, cache)
        assert did == 1
        cid, _ = _resolve_customer_from_cache(
            source_id=None,
            distributor_id=1,
            customer_raw="cust-01",
            dealer_group_raw=None,
            channel_raw=None,
            open_flag_raw=None,
            res_cache=cache,
        )
        assert cid == 10
        assert (
            customer_alias_conflict_reason_from_cache(
                cache,
                source_definition_id=None,
                distributor_id=1,
                normalized_token="cust01",
            )
            is None
        )
