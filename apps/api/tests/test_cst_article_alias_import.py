"""SCM article-alias workbook parse + import grouping, and customer-name resolution.

Unit tests use mocks. The resolver tests run in one rolled-back transaction on cip_test with
synthetic customers only.
"""

from __future__ import annotations

import asyncio
import secrets
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.services.imports.cst_article_alias_import as alias_import
from app.core.config import get_settings
from app.db.sync_url import sqlalchemy_sync_engine_url
from app.models.dimensions import DimCustomer, DimDistributor
from app.models.iam import Tenant
from app.models.import_distributor_si import CustomerSourceTokenAlias
from app.models.ingestion import ImportJob, ImportTemplate, SourceDefinition
from app.services.imports.cst_article_alias_import import (
    _resolve_customer_id,
    import_article_alias_rows,
    parse_article_alias_workbook,
)
from app.services.merge_redirect import follow_customer_merge_redirect_sync


def _xlsx_bytes(rows: list[tuple]) -> bytes:
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(list(row))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_article_alias_workbook_canonical_headers():
    raw = _xlsx_bytes(
        [
            ("Customer", "Article code", "Sales Model name"),
            ("Retailer Alpha", "850039776", "E1504FA-382B1W"),
            ("Retailer Alpha Online", "850038868", "X1504VA-NJ58256W"),
        ]
    )
    rows = parse_article_alias_workbook(raw)
    assert len(rows) == 2
    assert rows[0]["customer"] == "Retailer Alpha"
    assert rows[0]["article"] == "850039776"
    assert rows[1]["customer"] == "Retailer Alpha Online"


def test_no_hardcoded_customer_name_map():
    assert not hasattr(alias_import, "CUSTOMER_NAME_CANON")


def test_import_skips_collision_same_article_two_models():
    session = MagicMock()
    session.scalar.return_value = None

    rows = [
        {"customer": "Retailer Alpha", "article": "850038868", "sales_model": "MODEL-A"},
        {"customer": "Retailer Alpha", "article": "850038868", "sales_model": "MODEL-B"},
    ]

    with patch(
        "app.services.imports.cst_article_alias_import._load_product_resolution_index",
        return_value=MagicMock(),
    ), patch(
        "app.services.imports.cst_article_alias_import._resolve_customer_id",
        return_value=9001,
    ), patch(
        "app.services.imports.cst_article_alias_import.resolve_product_id_single_match",
        return_value=1,
    ):
        summary = import_article_alias_rows(session, rows, source="scm_upload")

    assert summary.collisions == 1
    assert summary.proposed == 0
    session.add.assert_not_called()


def test_import_resolves_each_customer_name_once_and_passes_tenant():
    session = MagicMock()
    rows = [
        {"customer": "Retailer Alpha", "article": "A1", "sales_model": "M1"},
        {"customer": "Retailer Alpha", "article": "A2", "sales_model": "M2"},
        {"customer": "Unknown Shop", "article": "A3", "sales_model": "M3"},
    ]
    with patch(
        "app.services.imports.cst_article_alias_import._load_product_resolution_index",
        return_value=MagicMock(),
    ), patch(
        "app.services.imports.cst_article_alias_import._resolve_customer_id",
        side_effect=lambda _s, name, tenant_id=None: None,
    ) as resolve:
        summary = import_article_alias_rows(session, rows, source="scm_upload", tenant_id="t-x")

    assert resolve.call_count == 2
    assert {c.kwargs["tenant_id"] for c in resolve.call_args_list} == {"t-x"}
    assert summary.customer_unresolved == 3
    assert summary.customer_unresolved_samples == ["Retailer Alpha", "Unknown Shop"]


def test_import_proposes_sku_twin_instead_of_skipping():
    session = MagicMock()
    session.scalar.return_value = None
    added = []

    def _add(obj):
        obj.id = 501
        added.append(obj)

    session.add.side_effect = _add
    session.flush.return_value = None

    idx = MagicMock()
    idx.sales_model_name_to_ids = {"model-x": (10, 11)}
    pick = MagicMock()
    pick.product_id = 10
    pick.as_evidence.return_value = {
        "sku_twin": True,
        "sku_twin_flag": False,
        "sku_twin_pick_reason": "lifecycle_filter",
        "unique_pm_match": False,
    }

    rows = [{"customer": "Retailer Beta", "article": "B08H8NH4XG", "sales_model": "MODEL-X"}]
    with patch(
        "app.services.imports.cst_article_alias_import._load_product_resolution_index",
        return_value=idx,
    ), patch(
        "app.services.imports.cst_article_alias_import._resolve_customer_id",
        return_value=9002,
    ), patch(
        "app.services.imports.cst_article_alias_import.resolve_product_id_single_match",
        return_value=None,
    ), patch(
        "app.services.imports.cst_sku_twin_disambiguate.disambiguate_sales_model_sku_twins",
        return_value=pick,
    ):
        summary = import_article_alias_rows(session, rows, source="scm_upload")

    assert summary.sku_twin_proposed == 1
    assert summary.proposed == 1
    assert summary.model_ambiguous == 0
    assert added[0].product_id == 10
    assert added[0].status == "proposed"
    assert added[0].evidence_json["sku_twin"] is True
    assert added[0].evidence_json["unique_pm_match"] is False


def test_confirm_unique_skips_sku_twin_evidence():
    from app.services.imports.cst_article_alias_import import confirm_scm_unique_proposed

    session = MagicMock()
    row = MagicMock()
    row.status = "proposed"
    row.evidence_json = {"source": "scm_upload", "sku_twin": True}
    session.get.return_value = row
    with patch("app.services.imports.cst_d1.confirm_customer_article_alias") as confirm:
        out = confirm_scm_unique_proposed(session, [9], actor="test")
    assert out == {"confirmed": 0, "skipped": 1}
    confirm.assert_not_called()


# --- generic customer-name resolution on cip_test ------------------------------------------


@pytest.fixture
def db():
    engine = create_engine(sqlalchemy_sync_engine_url(get_settings().database_url_sync))
    with engine.connect() as conn:
        name = conn.execute(text("SELECT current_database()")).scalar()
        print(f"SELECT current_database() -> {name}", flush=True)
        if name != "cip_test":
            pytest.exit(f"stop: current_database() is {name}", returncode=1)
        conn.rollback()
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
    engine.dispose()


@pytest.fixture
def world(db: Session) -> dict:
    t = secrets.token_hex(4)
    keeper = DimCustomer(code=f"CUST-W1D6-K-{t}", name=f"Synth{t} Keeper", customer_status="active")
    other = DimCustomer(code=f"CUST-W1D6-O-{t}", name=f"Synth{t} Other", customer_status="active")
    db.add_all([keeper, other])
    db.flush()
    loser = DimCustomer(
        code=f"TMP-CUST-W1D6-L-{t}",
        name=f"Synth{t} Old Name",
        customer_status="merged",
        merged_into_customer_id=keeper.id,
    )
    dist = DimDistributor(code=f"DIST-W1D6-{t}", name=f"Synth{t} Distributor")
    other_tenant = f"w1d6-{t}"
    db.add_all([loser, dist, Tenant(id=other_tenant, name="W1-D6 fixture tenant")])
    db.flush()
    foreign_customer = DimCustomer(
        code=f"CUST-W1D6-F-{t}",
        name=f"Synth{t} Foreign Customer",
        customer_status="active",
        tenant_id=other_tenant,
    )
    db.add(foreign_customer)
    db.flush()
    bridged = DimCustomer(
        code=f"TMP-CUST-W1D6-B-{t}",
        name=f"Synth{t} Bridged",
        customer_status="merged",
        merged_into_customer_id=foreign_customer.id,
        tenant_id="default",
    )
    db.add(bridged)
    db.flush()

    def alias(cid: int, token: str, *, distributor_id=None, status="approved", tenant_id="default"):
        db.add(
            CustomerSourceTokenAlias(
                customer_id=cid,
                raw_token=token,
                normalized_token=token,
                distributor_id=distributor_id,
                status=status,
                tenant_id=tenant_id,
            )
        )

    alias(keeper.id, f"synth{t} online")  # display name used in files, not a dim name
    alias(loser.id, f"synth{t} legacy")  # alias left on a merged loser
    alias(keeper.id, f"synth{t} split")  # same token, two customers in different scopes
    alias(other.id, f"synth{t} split", distributor_id=dist.id)
    alias(keeper.id, f"synth{t} same")  # same token, same customer in two scopes
    alias(keeper.id, f"synth{t} same", distributor_id=dist.id)
    alias(keeper.id, f"synth{t} pending", status="proposed")
    alias(keeper.id, f"synth{t} foreign", tenant_id=other_tenant)
    alias(bridged.id, f"synth{t} bridged token")
    db.flush()
    return {
        "t": t,
        "keeper": keeper.id,
        "other": other.id,
        "loser": loser.id,
        "foreign_customer": foreign_customer.id,
        "bridged": bridged.id,
        "other_tenant": other_tenant,
    }


def test_resolves_dim_customer_name_case_and_space_insensitive(db: Session, world: dict) -> None:
    t = world["t"]
    assert _resolve_customer_id(db, f"  synth{t} KEEPER ") == world["keeper"]
    # merged loser's name -> keeper
    assert _resolve_customer_id(db, f"Synth{t} Old Name") == world["keeper"]


def test_resolves_through_approved_customer_alias(db: Session, world: dict) -> None:
    t = world["t"]
    assert _resolve_customer_id(db, f"Synth{t}   Online") == world["keeper"]
    assert _resolve_customer_id(db, f"Synth{t} Legacy") == world["keeper"]
    assert _resolve_customer_id(db, f"Synth{t} Same") == world["keeper"]


def test_ambiguous_unapproved_foreign_tenant_and_unknown_stay_unresolved(
    db: Session, world: dict
) -> None:
    t = world["t"]
    assert _resolve_customer_id(db, f"Synth{t} Split") is None
    assert _resolve_customer_id(db, f"Synth{t} Pending") is None
    assert _resolve_customer_id(db, f"Synth{t} Foreign") is None
    assert _resolve_customer_id(db, f"Synth{t} Foreign", tenant_id=world["other_tenant"]) is None
    assert _resolve_customer_id(db, f"Synth{t} Nobody") is None
    assert _resolve_customer_id(db, "   ") is None


def test_import_reports_unresolved_names(db: Session, world: dict) -> None:
    t = world["t"]
    rows = [
        {"customer": f"Synth{t} Nobody", "article": "A1", "sales_model": "M1"},
        {"customer": f"Synth{t} Split", "article": "A2", "sales_model": "M2"},
    ]
    with patch(
        "app.services.imports.cst_article_alias_import._load_product_resolution_index",
        return_value=MagicMock(),
    ):
        summary = import_article_alias_rows(db, rows, source="scm_upload")
    assert summary.customer_unresolved == 2
    assert summary.customer_unresolved_samples == sorted([f"Synth{t} Nobody", f"Synth{t} Split"])
    assert summary.proposed == 0


def test_cross_tenant_redirect_refused_same_tenant_unchanged(db: Session, world: dict) -> None:
    t = world["t"]
    assert follow_customer_merge_redirect_sync(db, world["bridged"], tenant_id="default") is None
    assert _resolve_customer_id(db, f"Synth{t} Bridged") is None
    assert _resolve_customer_id(db, f"Synth{t} Bridged Token") is None
    assert follow_customer_merge_redirect_sync(db, world["loser"], tenant_id="default") == world["keeper"]
    assert _resolve_customer_id(db, f"Synth{t} Old Name") == world["keeper"]
    assert _resolve_customer_id(db, f"Synth{t} Legacy") == world["keeper"]
    assert follow_customer_merge_redirect_sync(db, world["bridged"]) == world["foreign_customer"]


def _alias_count(db: Session) -> int:
    return int(db.scalar(text("select count(*) from customer_source_token_alias")))


class _AliasDb:
    """Async facade over the rolled-back sync session. commit flushes, it does not commit."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.added: list = []

    async def run_sync(self, fn):
        return fn(self.session)

    async def scalar(self, stmt):
        return self.session.scalar(stmt)

    def add(self, row) -> None:
        self.added.append(row)
        self.session.add(row)

    async def commit(self) -> None:
        self.session.flush()

    async def refresh(self, row) -> None:
        self.session.refresh(row)

    async def rollback(self) -> None:
        return None


def _import_job(db: Session, tenant_id: str, token: str) -> int:
    tpl = ImportTemplate(
        slug=f"w1d6-{token}-{tenant_id}"[:64],
        display_name="w1d6",
        pipeline_handler="customer_sell_through",
    )
    db.add(tpl)
    db.flush()
    src = SourceDefinition(
        tenant_id=tenant_id,
        import_template_id=int(tpl.id),
        code=f"w1d6-{token}"[:64],
        name="w1d6",
        source_kind="file",
    )
    db.add(src)
    db.flush()
    job = ImportJob(
        tenant_id=tenant_id,
        source_id=int(src.id),
        template_slug="customer_sell_through",
        file_name=f"w1d6-{token}.xlsx",
    )
    db.add(job)
    db.flush()
    return int(job.id)


def test_create_customer_source_token_alias_tenant_guard(db: Session, world: dict) -> None:
    from app.api.v1.endpoints.mappings import (
        CustomerSourceTokenAliasCreate,
        create_customer_source_token_alias,
    )

    t = world["t"]
    job_id = _import_job(db, "default", f"d-{t}")
    foreign_job_id = _import_job(db, world["other_tenant"], f"f-{t}")
    proxy = _AliasDb(db)
    before = _alias_count(db)
    with pytest.raises(HTTPException) as refused:
        asyncio.run(
            create_customer_source_token_alias(
                CustomerSourceTokenAliasCreate(
                    customer_id=world["foreign_customer"],
                    raw_token=f"Synth{t} Cross Customer",
                    created_from_import_job_id=job_id,
                ),
                proxy,
            )
        )
    assert refused.value.status_code == 400
    with pytest.raises(HTTPException) as bridged:
        asyncio.run(
            create_customer_source_token_alias(
                CustomerSourceTokenAliasCreate(
                    customer_id=world["bridged"],
                    raw_token=f"Synth{t} Cross Redirect",
                    created_from_import_job_id=job_id,
                ),
                proxy,
            )
        )
    assert bridged.value.status_code == 400
    with pytest.raises(HTTPException) as other_import:
        asyncio.run(
            create_customer_source_token_alias(
                CustomerSourceTokenAliasCreate(
                    customer_id=world["keeper"],
                    raw_token=f"Synth{t} Other Import",
                    created_from_import_job_id=foreign_job_id,
                ),
                proxy,
            )
        )
    assert other_import.value.status_code == 400
    assert proxy.added == []
    assert _alias_count(db) == before

    created = asyncio.run(
        create_customer_source_token_alias(
            CustomerSourceTokenAliasCreate(
                customer_id=world["loser"],
                raw_token=f"Synth{t} Same Tenant",
                created_from_import_job_id=job_id,
            ),
            proxy,
        )
    )

    assert created["customer_id"] == world["loser"]
    assert created["status"] == "approved"
    assert proxy.added[0].customer_id == world["loser"]
    assert proxy.added[0].tenant_id == "default"
    assert _alias_count(db) == before + 1
