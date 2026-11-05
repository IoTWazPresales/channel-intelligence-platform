"""M5c / D-0149: column-mapping memory and alias tables are tenant-scoped.

Two fictional tenants: same normalised token and same source *code* must resolve independently;
neither tenant sees the other's sheet memory or approved customer alias.

cip_test only; transactional rollback per test.
"""

from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import select, text

from app.db.session_sync import SessionLocal
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.iam import Tenant
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.services.imports.distributor_sales_inventory import _alias_customer_id
from app.services.imports.shipment_field_mapping import (
    merge_shipment_mapping_memory,
    remembered_sheet_names,
    remember_selected_sheets,
)
from app.services.imports.tenant_mapping_scope import effective_tenant_id

API_DIR = Path(__file__).resolve().parents[1]


def _migration_0055():
    path = API_DIR / "alembic" / "versions" / "20261103_0055_tenant_mapping_memory_aliases.py"
    spec = importlib.util.spec_from_file_location("m0055", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def db_world():
    with SessionLocal() as db:
        if db.scalar(text("select current_database()")) != "cip_test":
            pytest.skip("cip_test only")
        # 0055 was renumbered off the old 0052 filename. Apply it only when the
        # tenant column is still missing; a later head must not re-run upgrade.
        has_tenant = db.scalar(
            text(
                "select 1 from information_schema.columns "
                "where table_schema = 'public' and table_name = 'source_definition' "
                "and column_name = 'tenant_id'"
            )
        )
        if not has_tenant:
            ops = Operations.context(MigrationContext.configure(db.connection()))
            with ops:
                _migration_0055().upgrade()
        tag = uuid.uuid4().hex[:8]

        def mk_tenant(label: str) -> str:
            tid = f"tf-{label}-{tag}"
            db.add(Tenant(id=tid, name=f"Fictional tenant {label}"))
            db.flush()
            return tid

        def mk_source(tenant_id: str, code: str) -> SourceDefinition:
            tok = uuid.uuid4().hex[:8]
            tpl = ImportTemplate(
                slug=f"m5c-{tok}",
                display_name="m5c",
                pipeline_handler="inbound_shipments",
            )
            db.add(tpl)
            db.flush()
            src = SourceDefinition(
                tenant_id=tenant_id,
                import_template_id=int(tpl.id),
                code=code,
                name="m5c source",
                source_kind="file",
            )
            db.add(src)
            db.flush()
            return src

        yield db, mk_tenant, mk_source, tag
        db.rollback()


def test_customer_alias_same_token_different_tenant(db_world):
    db, mk_tenant, mk_source, _tag = db_world
    ta, tb = mk_tenant("alpha"), mk_tenant("beta")
    shared_code = f"shared-src-{uuid.uuid4().hex[:6]}"
    sa, sb = mk_source(ta, shared_code), mk_source(tb, shared_code)
    da = DimDistributor(tenant_id=ta, code=f"d-a-{uuid.uuid4().hex[:4]}", name="Dist A")
    db.add(da)
    db.flush()
    ca = DimCustomer(tenant_id=ta, code=f"c-a-{uuid.uuid4().hex[:4]}", name="Cust A")
    cb = DimCustomer(tenant_id=tb, code=f"c-b-{uuid.uuid4().hex[:4]}", name="Cust B")
    db.add_all([ca, cb])
    db.flush()
    token = "shared-dealer-token"
    nt = token
    db.add(
        CustomerSourceTokenAlias(
            tenant_id=ta,
            customer_id=int(ca.id),
            source_definition_id=int(sa.id),
            raw_token=token,
            normalized_token=nt,
            status="approved",
        )
    )
    db.add(
        CustomerSourceTokenAlias(
            tenant_id=tb,
            customer_id=int(cb.id),
            source_definition_id=int(sb.id),
            raw_token=token,
            normalized_token=nt,
            status="approved",
        )
    )
    db.flush()
    assert _alias_customer_id(db, int(sa.id), None, nt, None, tenant_id=ta) == int(ca.id)
    assert _alias_customer_id(db, int(sb.id), None, nt, None, tenant_id=tb) == int(cb.id)
    assert _alias_customer_id(db, int(sa.id), None, nt, None, tenant_id=tb) is None
    assert _alias_customer_id(db, int(sb.id), None, nt, None, tenant_id=ta) is None


def test_shipment_sheet_memory_not_shared_across_tenants(db_world):
    db, mk_tenant, mk_source, _tag = db_world
    ta, tb = mk_tenant("alpha"), mk_tenant("beta")
    code = f"ship-{uuid.uuid4().hex[:6]}"
    sa, sb = mk_source(ta, code), mk_source(tb, code)
    remember_selected_sheets(
        db,
        source_id=int(sa.id),
        tenant_id=ta,
        sheet_names=["Sheet-Alpha"],
        available_sheets=["Sheet-Alpha", "Sheet-Other"],
    )
    db.flush()
    db.refresh(sa)
    db.refresh(sb)
    assert remembered_sheet_names(sa, tenant_id=ta) == ["Sheet-Alpha"]
    assert remembered_sheet_names(sb, tenant_id=tb) == []
    assert remembered_sheet_names(sa, tenant_id=tb) == []
    merge_shipment_mapping_memory(
        db,
        source_id=int(sb.id),
        tenant_id=tb,
        field_mapping={"Col B": "item_code"},
    )
    db.refresh(sb)
    assert remembered_sheet_names(sb, tenant_id=tb) == []
    mem = (sb.column_mapping_memory or {}).get("by_header_norm") or {}
    assert "col_b" in mem
    scoped_a = db.get(SourceDefinition, int(sa.id))
    assert scoped_a is not None
    mem_a = (scoped_a.column_mapping_memory or {}).get("by_header_norm") or {}
    assert "col_b" not in mem_a


def test_migration_0055_downgrade_upgrade(db_world):
    db, *_ = db_world
    mod = _migration_0055()
    assert mod.revision == "20261103_0055"
    stamped = db.scalar(text("select version_num from alembic_version"))
    ops = Operations.context(MigrationContext.configure(db.connection()))
    with ops:
        mod.downgrade()
        assert db.scalar(text("select count(*) from information_schema.columns where table_name='source_definition' and column_name='tenant_id'")) == 0
        mod.upgrade()
    # Direct upgrade() does not stamp alembic_version. The column coming back is the proof.
    assert db.scalar(text("select version_num from alembic_version")) == stamped
    assert db.scalar(text("select count(*) from information_schema.columns where table_name='source_definition' and column_name='tenant_id'")) == 1
    assert effective_tenant_id(None) == "default"
