"""T1b: the Brief settlement counts come from one SQL aggregate and match the per-case rules.

World (synthetic tenant, rolled back): open cases covering every rate/mode combination, plus a
settled case and an intelligence-excluded case that must not count. The aggregate must give the
same numbers the old per-case Python rules (``fx_declared`` / ``fx_mode_valid`` /
``case_missing_roe``) gave on the same rows. Also: ``recon_rows_exist_stmt`` runs.

Not run by the author: the coordinator runs it on cip_test.
"""

from __future__ import annotations

import secrets
from datetime import date

import pytest
from app.models.cpor import CporCase
from app.models.dimensions import DimCustomer
from app.services import brief_signals
from app.services.cpor.settle_readiness import case_missing_roe, fx_declared, fx_mode_valid
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
            "cpor_case": select(func.count()).where(CporCase.case_code.like(f"T1B-{tag}-%")),
            "dim_customer": select(func.count()).where(DimCustomer.code == f"T1B-{tag}-C"),
        }
    )
    assert counts == {key: 0 for key in counts}, f"fixture rows left after teardown: {counts}"


def _case(tag: str, n: int, customer_id: int, **kw) -> CporCase:
    return CporCase(
        case_code=f"T1B-{tag}-{n}",
        tenant_id=f"t-{tag}",
        customer_id=customer_id,
        promotion_type="price_promo",
        window_start=date(2098, 1, 1),
        window_end=date(2098, 2, 1),
        **kw,
    )


@pytest.mark.anyio
async def test_fx_counts_match_the_per_case_rules(session, monkeypatch):
    monkeypatch.setattr(brief_signals, "commercial_planner_enabled", lambda: True)
    tag = session.info["tag"]
    tenant = f"t-{tag}"
    cust = DimCustomer(code=f"T1B-{tag}-C", name=f"Customer {tag}", tenant_id=tenant)
    session.add(cust)
    await session.flush()
    cases = [
        _case(tag, 1, cust.id, status="active", roe_snapshot=18.2, fx_mode=None),  # blocked
        _case(tag, 2, cust.id, status="active", roe_snapshot=18.2, fx_mode="booked"),
        _case(tag, 3, cust.id, status="draft", roe_snapshot=18.2, fx_mode="floating"),
        _case(tag, 4, cust.id, status="active", roe_snapshot=None, fx_mode="booked"),  # no rate
        _case(tag, 5, cust.id, status="active", roe_snapshot=None, fx_mode=None),  # no rate
        _case(tag, 6, cust.id, status="active", roe_snapshot=0, fx_mode="booked"),  # zero = no rate
        # fx_mode is constrained to booked/floating/NULL, so a junk value cannot be seeded.
        _case(tag, 8, cust.id, status="settled", roe_snapshot=18.2, fx_mode=None),  # not open
        _case(tag, 9, cust.id, status="active", roe_snapshot=18.2, fx_mode=None, intelligence_exclude=True),
    ]
    session.add_all(cases)
    await session.flush()

    user = {"tenant_id": tenant}
    open_n, blocked_n, no_rate_n = (await session.execute(brief_signals.open_case_fx_counts_stmt(user))).one()

    counted = [c for c in cases if c.status != "settled" and not c.intelligence_exclude]
    assert open_n == len(counted) == 6
    assert blocked_n == len([c for c in counted if fx_declared(c) and not fx_mode_valid(c)]) == 1
    assert no_rate_n == len([c for c in counted if case_missing_roe(c)]) == 3

    out = await brief_signals._settlement_aggregates(session, user)
    assert (out["open_cases"], out["fx_blocked_cases"], out["fx_rate_missing_cases"]) == (6, 1, 3)


@pytest.mark.anyio
async def test_recon_existence_probe_returns_a_bool(session):
    assert isinstance(await session.scalar(brief_signals.recon_rows_exist_stmt()), bool)
