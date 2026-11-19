"""T1b: the customer-token worklist's column reads work on real SQL and keep its counts (cip_test).

World (synthetic, rolled back): one case with four unresolved lines (two share a token, one has its
own token, one has an empty token) and one resolved line that uses another token. The worklist is
read before and after the fixture goes in: ``rows_scanned``, ``total`` and ``bucket_counts`` move by
exactly the fixture (4 lines, +1 empty-token item, +2 token items). Other rows in the database are
untouched, so only the delta is asserted. Where the page includes the fixture items their fields are
checked.
Real session inside an outer transaction rolled back at the end (``tests/rolled_back_async_session.py``).

Not run by the author: the coordinator runs it on cip_test.
"""

from __future__ import annotations

import secrets

import pytest
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
from app.models.dimensions import DimCustomer, DimProduct
from app.services.commercial_planner.lineup_customer_token_stamp import list_customer_token_worklist
from sqlalchemy import func, select
from tests.rolled_back_async_session import leftover_counts, rolled_back_async_session


@pytest.fixture
async def session():
    async with rolled_back_async_session() as db:
        db.info["tag"] = secrets.token_hex(4)
        yield db
        tag = db.info["tag"]
    counts = await leftover_counts(
        {
            "commercial_lineup_line": select(func.count()).where(
                CommercialLineupLine.customer_token.like(f"t1b-{tag}-%")
            ),
            "dim_customer": select(func.count()).where(DimCustomer.code == f"T1B-{tag}-C"),
            "dim_product": select(func.count()).where(DimProduct.sku.like(f"T1B-{tag}-%")),
        }
    )
    assert counts == {key: 0 for key in counts}, f"fixture rows left after teardown: {counts}"


def _bucket(counts: dict, key: str) -> int:
    return int(counts.get(key, 0))


@pytest.mark.anyio
async def test_worklist_counts_move_by_exactly_the_fixture(session):
    tag = session.info["tag"]
    before = await list_customer_token_worklist(session, limit=500)

    cust = DimCustomer(code=f"T1B-{tag}-C", name=f"Customer {tag}", tenant_id="default")
    prods = [DimProduct(sku=f"T1B-{tag}-P{i}", name=f"Product {i}", tenant_id="default") for i in (1, 2, 3)]
    case = CommercialLineupCase(commercial_status="draft_imported", period_label="2098Q2")
    session.add_all([cust, *prods, case])
    await session.flush()
    shared, solo = f"t1b-{tag}-shared", f"t1b-{tag}-solo"
    session.add_all(
        [
            CommercialLineupLine(case_id=case.id, product_id=prods[0].id, customer_token=shared, quantity_units=1),
            CommercialLineupLine(case_id=case.id, product_id=prods[1].id, customer_token=shared.upper(), quantity_units=1),
            CommercialLineupLine(case_id=case.id, product_id=prods[2].id, customer_token=solo, quantity_units=1),
            CommercialLineupLine(case_id=case.id, product_id=prods[0].id, customer_token="", quantity_units=1),
            # resolved line with another token on the same case: isolates product 1 from the shared token
            CommercialLineupLine(case_id=case.id, product_id=prods[0].id, customer_id=cust.id,
                                 customer_token=f"t1b-{tag}-other", quantity_units=1),
        ]
    )
    await session.flush()

    after = await list_customer_token_worklist(session, limit=500)
    assert after["rows_scanned"] - before["rows_scanned"] == 4
    assert after["total"] - before["total"] == 3
    assert _bucket(after["bucket_counts"], "all") - _bucket(before["bucket_counts"], "all") == 3
    assert _bucket(after["bucket_counts"], "empty_token") - _bucket(before["bucket_counts"], "empty_token") == 1
    assert _bucket(after["bucket_counts"], "clean") - _bucket(before["bucket_counts"], "clean") == 2

    by_key = {it["item_key"]: it for it in after["items"]}
    if shared in by_key:
        assert by_key[shared]["line_count"] == 2
        assert by_key[shared]["bucket"] == "clean"
    if f"__empty_token__:case:{case.id}" in by_key:
        assert by_key[f"__empty_token__:case:{case.id}"]["bucket"] == "empty_token"
        assert by_key[f"__empty_token__:case:{case.id}"]["line_count"] == 1
