"""N-0040 (D-g): sellable product lines come from dim_product.product_line only.

DB test: inserts dim_product rows inside a transaction that is rolled back (write-capable module;
the conftest guard refuses it on ``cip``).
"""

from __future__ import annotations

import secrets

import pytest

from app.services.catalog.product_lines import (
    invalidate_sellable_product_lines_cache,
    list_sellable_product_lines,
    sellable_line_codes,
)


@pytest.mark.anyio
async def test_service_lists_trimmed_codes_and_excludes_null_and_blank():
    from app.api.v1.endpoints.catalog import list_product_lines
    from app.db.session import AsyncSessionLocal
    from app.models.dimensions import DimProduct

    tag = secrets.token_hex(3).upper()
    code_a = f"Q{tag}"  # unique so pre-existing rows cannot collide
    code_b = f"R{tag}"
    async with AsyncSessionLocal() as db:
        try:
            before = await list_sellable_product_lines(db, force_refresh=True)
            assert code_a not in before.codes
            specs = [
                code_a,
                f"  {code_a} ",  # trim variant counts as the same code
                code_a,
                code_b,
                None,
                "",
                "   ",
            ]
            for i, pl in enumerate(specs):
                db.add(DimProduct(sku=f"N0040-{tag}-{i}", name=f"N0040 test {i}", product_line=pl))
            await db.flush()

            after = await list_sellable_product_lines(db, force_refresh=True)
            by_code = {line.code: line for line in after.lines}
            assert by_code[code_a].product_count == 3
            assert by_code[code_b].product_count == 1
            assert by_code[code_a].label == code_a  # label = code; no label config exists
            assert all(line.code and line.code == line.code.strip() for line in after.lines)
            assert "" not in after.codes
            assert after.null_product_line_count == before.null_product_line_count + 3
            counts = [line.product_count for line in after.lines]
            assert counts == sorted(counts, reverse=True)

            # Cached result is served until invalidated.
            cached = await sellable_line_codes(db)
            assert code_a in cached

            payload = await list_product_lines(db)
            assert set(payload) == {"product_lines", "null_product_line_count"}
            assert {"code": code_b, "product_count": 1, "label": code_b} in payload["product_lines"]
        finally:
            await db.rollback()
            invalidate_sellable_product_lines_cache()
