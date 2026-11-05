"""One failed customer FK count must not abort the rest of the session.

cip_test only. Seeds two dim_customer rows and rolls them back.
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import text

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer
from app.services.customer_full_repoint import count_customer_fk_refs


def test_failed_table_count_leaves_session_usable_and_returns_later_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.customer_full_repoint.discover_customer_fk_columns",
        lambda _db: (
            ("fk_count_missing_relation", "customer_id"),
            ("dim_customer", "merged_into_customer_id"),
        ),
    )
    monkeypatch.setattr("app.services.customer_full_repoint.extra_customer_ref_specs", lambda: ())

    suffix = secrets.token_hex(6)
    with SessionLocal() as db:
        current = db.execute(text("select current_database()")).scalar()
        print(f"current_database={current}")
        if current != "cip_test":
            pytest.fail(f"refusing to run unless current_database() is cip_test, got {current!r}")
        try:
            keeper = DimCustomer(
                code=f"FKC-K-{suffix}",
                name=f"FK count keeper {suffix}",
                customer_status="active",
            )
            loser = DimCustomer(
                code=f"FKC-L-{suffix}",
                name=f"FK count loser {suffix}",
                customer_status="unverified",
            )
            db.add(keeper)
            db.flush()
            loser.merged_into_customer_id = int(keeper.id)
            db.add(loser)
            db.flush()

            counts = count_customer_fk_refs(db, int(keeper.id))

            assert counts == {"dim_customer.merged_into_customer_id": 1}
            still = db.execute(
                text("select count(*) from dim_customer where code = :code"),
                {"code": f"FKC-L-{suffix}"},
            ).scalar()
            assert int(still or 0) == 1
            assert db.execute(text("select 1")).scalar() == 1
        finally:
            db.rollback()
