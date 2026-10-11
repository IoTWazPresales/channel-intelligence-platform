"""N-0068 / D-0060: column sets per product line in the database, cip_test only.

Everything runs inside one transaction that is always rolled back. Skips on any
database other than cip_test, and when cip_test lacks tenant_column_grain
(migration 20261006_0024 not applied there). Never writes to cip.

Checks:
- tenant_column_grain is one row per tenant and refuses a blank grain;
- dim_product.ean carries no unique index or constraint, so duplicate EANs load
  (they are a FLAG on the import job, not a block);
- catalog_product is still in place (D-0060: do not retire it);
- a Product Master mapping save for one sellable product line lands under
  mapping_profile.by_product_line.<line> on the real source row, and the next
  suggestion for that line (and only that line) reads it back.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


@pytest.fixture()
def conn():
    from app.core.config import get_settings

    get_settings.cache_clear()
    eng = create_engine(get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1))
    try:
        c = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = c.execute(text("select current_database()")).scalar_one()
    if db != "cip_test":
        c.close()
        eng.dispose()
        pytest.skip(f"N-0068 column-grain DB test runs on cip_test only (current_database()={db})")
    if c.execute(text("select to_regclass('public.tenant_column_grain')")).scalar_one() is None:
        c.close()
        eng.dispose()
        pytest.skip("cip_test has no tenant_column_grain (20261006_0024 not applied)")
    c.rollback()
    tx = c.begin()
    try:
        yield c
    finally:
        tx.rollback()
        c.close()
        eng.dispose()


def test_tenant_column_grain_one_row_per_tenant_and_not_blank(conn) -> None:
    assert conn.execute(text("select current_database()")).scalar_one() == "cip_test"
    pk_cols = conn.execute(
        text(
            """
            select a.attname
            from pg_index i
            join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
            where i.indrelid = 'tenant_column_grain'::regclass and i.indisprimary
            """
        )
    ).scalars().all()
    assert pk_cols == ["tenant_id"]
    default = conn.execute(
        text(
            "select column_default from information_schema.columns "
            "where table_name = 'tenant_column_grain' and column_name = 'grain'"
        )
    ).scalar_one()
    assert "product_line" in (default or "")
    tid = f"n0068-{uuid.uuid4().hex[:8]}"
    conn.execute(text("insert into tenant (id, name) values (:t, :t)"), {"t": tid})
    sp = conn.begin_nested()
    with pytest.raises(IntegrityError):
        conn.execute(text("insert into tenant_column_grain (tenant_id, grain) values (:t, '  ')"), {"t": tid})
    sp.rollback()
    conn.execute(text("insert into tenant_column_grain (tenant_id) values (:t)"), {"t": tid})
    assert (
        conn.execute(text("select grain from tenant_column_grain where tenant_id = :t"), {"t": tid}).scalar_one()
        == "product_line"
    )
    sp = conn.begin_nested()
    with pytest.raises(IntegrityError):
        conn.execute(text("insert into tenant_column_grain (tenant_id, grain) values (:t, 'feed')"), {"t": tid})
    sp.rollback()


def test_dim_product_ean_has_no_unique_rule_and_duplicates_load(conn) -> None:
    unique_on_ean = conn.execute(
        text(
            """
            select count(*)
            from pg_index i
            join pg_attribute a on a.attrelid = i.indrelid and a.attnum = any(i.indkey)
            where i.indrelid = 'dim_product'::regclass and i.indisunique and a.attname = 'ean'
            """
        )
    ).scalar_one()
    assert unique_on_ean == 0
    expr_unique = conn.execute(
        text(
            "select count(*) from pg_indexes where tablename = 'dim_product' "
            "and indexdef ilike 'create unique%' and indexdef ilike '%ean%'"
        )
    ).scalar_one()
    assert expr_unique == 0
    tag = uuid.uuid4().hex[:8]
    ean = f"99{tag}"[:13]
    for i in range(2):
        conn.execute(
            text(
                "insert into dim_product (sku, name, is_active, product_line, ean) "
                "values (:sku, :name, true, 'N0068-LINE', :ean)"
            ),
            {"sku": f"N0068-{tag}-{i}", "name": f"N0068 duplicate EAN fixture {i}", "ean": ean},
        )
    assert conn.execute(text("select count(*) from dim_product where ean = :e"), {"e": ean}).scalar_one() == 2


def test_catalog_product_is_kept(conn) -> None:
    assert conn.execute(text("select to_regclass('public.catalog_product')")).scalar_one() is not None
    assert conn.execute(text("select to_regclass('public.product_catalog')")).scalar_one() is not None


def test_pm_mapping_save_lands_on_the_line_and_reads_back(conn) -> None:
    from app.models.ingestion import ImportJob, SourceDefinition
    from app.services.imports.pm_mapping_memory import load_by_header_norm, tenant_column_grain_sync
    from app.services.imports.product_master_workflow import (
        STAGE_PM_HEADERS,
        save_mapping_sync,
        suggest_mapping_decisions,
    )

    source_id = conn.execute(
        text(
            """
            select sd.id from source_definition sd
            join import_template t on t.id = sd.import_template_id
            where t.slug = 'product_master'
            order by sd.id limit 1
            """
        )
    ).scalar()
    if source_id is None:
        pytest.skip("cip_test has no Product Master source_definition")
    tag = uuid.uuid4().hex[:6].upper()
    line_mb, line_nb = f"MB{tag}", f"NB{tag}"
    for i, line in enumerate((line_mb, line_nb)):
        conn.execute(
            text(
                "insert into dim_product (sku, name, is_active, product_line) values (:s, :n, true, :l)"
            ),
            {"s": f"N0068-{tag}-L{i}", "n": f"N0068 line fixture {i}", "l": line},
        )
    conn.execute(
        text(
            "insert into tenant_column_grain (tenant_id, grain) values ('default', 'product_line') "
            "on conflict (tenant_id) do update set grain = 'product_line'"
        )
    )

    with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
        assert tenant_column_grain_sync(db, "default") == "product_line"
        job = ImportJob(
            tenant_id="default",
            source_id=source_id,
            template_slug="product_master",
            import_mode="validate",
            status="draft",
            stage=STAGE_PM_HEADERS,
            file_name="n0068.xlsx",
            file_headers=["Item", "Title", "Chipset Socket"],
        )
        db.add(job)
        db.flush()
        cols = [
            {"header": "Item", "target": "technical_product_id"},
            {"header": "Title", "target": "display_name"},
            {"header": "Chipset Socket", "target": "series"},
        ]
        save_mapping_sync(db, job.id, cols, product_line=line_mb)
        src = db.get(SourceDefinition, source_id)
        db.refresh(src)
        profile = (src.column_mapping_memory or {}).get("mapping_profile") or {}
        mb_set = profile["by_product_line"][line_mb]["by_header_norm"]
        assert mb_set["chipset_socket"]["target"] == "series"
        assert line_nb not in profile.get("by_product_line", {})

        assert load_by_header_norm(src, product_line=line_mb)["chipset_socket"]["target"] == "series"
        assert "chipset_socket" not in load_by_header_norm(src, product_line=line_nb) or (
            # A source-wide learned mapping for this header (from real data) is allowed, but it is not
            # the line overlay we just wrote.
            "chipset_socket" in ((src.column_mapping_memory or {}).get("by_header_norm") or {})
        )
        inf = {"columns": [{"name": "Chipset Socket", "dtype": "object", "sample": ["AM5"]}], "row_count": 1}
        mb_suggest = suggest_mapping_decisions(["Chipset Socket"], src, inf, product_line=line_mb, grain="product_line")
        assert mb_suggest["Chipset Socket"]["target"] == "series"
