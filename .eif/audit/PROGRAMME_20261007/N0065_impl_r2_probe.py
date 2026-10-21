"""N-0065 round 2 (RUN-20261007-N0065-IMPL): read-only proof on cip that request-path
SessionLocal() sessions now carry the bound product-line scope.

Run from apps/api with its virtualenv. Every transaction is READ ONLY and ends in rollback,
except one COMMIT of a READ ONLY transaction (writes nothing) to show the scope survives a
commit. Prints current_database() first and asserts cip. No identities printed.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import text

from app.core.product_line_scope import (
    product_line_scope_for,
    request_editable_product_lines,
    request_product_lines,
)
from app.db.session_sync import SessionLocal

SHOW = "select current_setting('cip.product_lines', true)"
SHOW_EDIT = "select current_setting('cip.editable_product_lines', true)"
PRODUCTS = "select count(*) from dim_product"
FORECAST = "select count(*) from fact_demand_forecast"


@contextmanager
def scope(read, edit):
    t1 = request_product_lines.set(read)
    t2 = request_editable_product_lines.set(edit)
    try:
        yield
    finally:
        request_product_lines.reset(t1)
        request_editable_product_lines.reset(t2)


def ro(s) -> None:
    s.execute(text("SET TRANSACTION READ ONLY"))
    assert s.execute(text("show transaction_read_only")).scalar_one() == "on"


def counts(label: str) -> None:
    with SessionLocal() as s:
        ro(s)
        print(
            f"[sync SessionLocal {label}] cip.product_lines={s.execute(text(SHOW)).scalar_one()!r}",
            f"editable={s.execute(text(SHOW_EDIT)).scalar_one()!r}",
            f"dim_product={s.execute(text(PRODUCTS)).scalar_one()}",
            f"fact_demand_forecast={s.execute(text(FORECAST)).scalar_one()}",
        )
        s.rollback()


def main() -> int:
    with SessionLocal() as s:
        db = s.execute(text("select current_database()")).scalar_one()
        print("current_database() =", db)
        assert db == "cip"
        s.rollback()

    counts("worker/unset")
    with scope(*product_line_scope_for(is_admin=False, assignments=[])):
        counts("non-admin, no rows")
    with scope(*product_line_scope_for(is_admin=True, assignments=[])):
        counts("admin")
    with scope(*product_line_scope_for(is_admin=False, assignments=[("AZ", False)])):
        counts("non-admin, AZ read-only")
        with SessionLocal() as s:
            ro(s)
            other = s.execute(
                text("select count(*) from dim_product where product_line is distinct from 'AZ'")
            ).scalar_one()
            editable = s.execute(
                text("select count(*) from dim_product where cip_product_id_editable(id)")
            ).scalar_one()
            print(f"  rows of any other line={other} editable(AZ read-only)={editable}")
            s.rollback()

    with scope(*product_line_scope_for(is_admin=True, assignments=[])):
        with SessionLocal() as s:
            ro(s)
            before = s.execute(text(PRODUCTS)).scalar_one()
            s.commit()  # READ ONLY transaction: nothing written
            ro(s)
            after = s.execute(text(PRODUCTS)).scalar_one()
            print(f"[admin, commit then read] before={before} after={after} setting_after={s.execute(text(SHOW)).scalar_one()!r}")
            s.rollback()

    # Pool hygiene: the request values must not be visible to a later unscoped checkout.
    for i in range(3):
        with SessionLocal() as s:
            ro(s)
            print(f"[pool checkout {i} unscoped] cip.product_lines={s.execute(text(SHOW)).scalar_one()!r} dim_product={s.execute(text(PRODUCTS)).scalar_one()}")
            s.rollback()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
