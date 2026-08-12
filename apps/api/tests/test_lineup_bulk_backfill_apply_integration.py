"""Apply-path integration tests for bulk lineup backfill (disposable DB only — never cip)."""
from __future__ import annotations

import asyncio
import io
import os
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy import create_engine, select, text

BULK_SMOKE_DB = os.environ.get("CIP_BULK_SMOKE_DATABASE", "cip_bulk_smoke")
BULK_SMOKE_URL_SYNC = f"postgresql+psycopg://cip:cip@127.0.0.1:5432/{BULK_SMOKE_DB}"
BULK_SMOKE_URL_ASYNC = f"postgresql+asyncpg://cip:cip@127.0.0.1:5432/{BULK_SMOKE_DB}"


def _assert_not_cip(url: str) -> None:
    db_name = url.rsplit("/", 1)[-1].split("?", 1)[0]
    assert db_name != "cip", f"Refusing writes against cip (url={url})"


def _minimal_xlsx(*, sheets: dict[str, list[list]]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=name, index=False, header=False)
    return buf.getvalue()


def _clean_single_bu_xlsx() -> bytes:
    return _minimal_xlsx(
        sheets={
            "NB": [
                ["SKU", "Qty", "Customer"],
                ["bulk-nb-01", "10", "Amazon"],
                ["bulk-unknown", "3", "Amazon"],
            ],
        }
    )


def _multi_bu_xlsx() -> bytes:
    return _minimal_xlsx(
        sheets={
            "NB": [
                ["SKU", "Qty", "Customer"],
                ["bulk-nb-01", "10", "Amazon"],
                ["bulk-nr-01", "5", "Amazon"],
            ],
        }
    )


def _multi_bu_slice_xlsx() -> bytes:
    """5 NB rows + 2 NR rows on one sheet — fan-out slice disjointness fixture."""
    rows = [["SKU", "Qty", "Customer"]]
    for i in range(1, 6):
        rows.append([f"bulk-nb-{i:02d}", str(i), "Amazon"])
    for i in range(1, 3):
        rows.append([f"bulk-nr-{i:02d}", str(10 + i), "Amazon"])
    return _minimal_xlsx(sheets={"Mixed": rows})


def _sync_enqueue_parse(**kwargs):
    from app.services.commercial_planner.lineup_parse_worker import run_lineup_case_parse_sync

    run_lineup_case_parse_sync(
        kwargs["case_id"],
        kwargs["filename"],
        kwargs["file_bytes"],
        import_job_id=kwargs["import_job_id"],
        template_slug=kwargs.get("template_slug", "bulk_lineup_backfill"),
        source_code=kwargs.get("source_code", "bulk_lineup_backfill_system"),
    )
    return {"outcome": "parsed_sync", "task_id": "test-sync"}


def _half_year_xlsx() -> bytes:
    return _minimal_xlsx(
        sheets={
            "NB": [
                ["2026 1H NEW PLAN", "", ""],
                ["SKU", "Qty", "Customer"],
                ["bulk-nb-01", "8", "PlanCustomer"],
            ],
        }
    )


def _collision_xlsx(filename_suffix: str) -> bytes:
    return _minimal_xlsx(
        sheets={
            "NB": [
                ["SKU", "Qty", "Customer"],
                [f"sku-{filename_suffix}", "10", "Amazon"],
            ],
        }
    )


def _spec_dump_xlsx() -> bytes:
    rows = [["SKU", "Qty", "Customer"]]
    rows.append(["only-one", "1", "Amazon"])
    rows.extend([["missing-token", "1", "Amazon"] for _ in range(40)])
    return _minimal_xlsx(sheets={"NB": rows})


@pytest.fixture(scope="module")
def bulk_smoke_env():
    """Point both sync URLs at cip_bulk_smoke for the module."""
    _assert_not_cip(BULK_SMOKE_URL_SYNC)
    _assert_not_cip(BULK_SMOKE_URL_ASYNC)

    os.environ["DATABASE_URL"] = BULK_SMOKE_URL_ASYNC
    os.environ["DATABASE_URL_SYNC"] = BULK_SMOKE_URL_SYNC
    os.environ["DATABASE_URL_SYNC_MIGRATE"] = BULK_SMOKE_URL_SYNC

    from app.core.config import get_settings

    get_settings.cache_clear()

    settings = get_settings()
    resolved_sync = settings.database_url_sync
    resolved_migrate = settings.database_url_sync_migrate or settings.database_url_sync
    print(f"resolved DATABASE_URL_SYNC={resolved_sync}")
    print(f"resolved DATABASE_URL_SYNC_MIGRATE={resolved_migrate}")
    _assert_not_cip(resolved_sync)
    _assert_not_cip(resolved_migrate)

    with create_engine(BULK_SMOKE_URL_SYNC).connect() as conn:
        db = conn.execute(text("SELECT current_database()")).scalar_one()
        assert db == BULK_SMOKE_DB, db
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        assert rev == "20260812_0013", f"expected tip 20260812_0013 on {BULK_SMOKE_DB}, got {rev}"
        col = conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'commercial_lineup_case' AND column_name = 'superseded_by_case_id'
                """
            )
        ).first()
        assert col is not None, "superseded_by_case_id missing"

    yield

    get_settings.cache_clear()


def _clear_bulk_backfill_cases() -> None:
    from app.db.session_sync import SessionLocal
    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
    from sqlalchemy import delete

    with SessionLocal() as db:
        case_ids = list(
            db.scalars(
                select(CommercialLineupCase.id).where(
                    CommercialLineupCase.source_context == "bulk_lineup_backfill"
                )
            ).all()
        )
        if case_ids:
            db.execute(delete(CommercialLineupLine).where(CommercialLineupLine.case_id.in_(case_ids)))
            db.execute(
                delete(CommercialLineupCase).where(CommercialLineupCase.source_context == "bulk_lineup_backfill")
            )
            db.commit()


def _seed_catalog():
    from app.db.session_sync import SessionLocal
    from app.models.dimensions import DimCustomer, DimProduct
    from app.services.imports.product_resolution_index_cache import (
        invalidate_product_resolution_index_cache,
    )

    with SessionLocal() as db:
        cust = db.scalar(select(DimCustomer).where(DimCustomer.name == "Amazon"))
        if cust is None:
            cust = DimCustomer(code="AMZ-BULK", name="Amazon", customer_status="active")
            db.add(cust)
            db.flush()
        plan_cust = db.scalar(select(DimCustomer).where(DimCustomer.name == "PlanCustomer"))
        if plan_cust is None:
            db.add(DimCustomer(code="PLAN-BULK", name="PlanCustomer", customer_status="active"))
        skus = {
            "bulk-nb-01": ("NB", "bulk-nb-01"),
            "bulk-nr-01": ("NR", "bulk-nr-01"),
            "bulk-nb-02": ("NB", "bulk-nb-02"),
            "bulk-nb-03": ("NB", "bulk-nb-03"),
            "bulk-nb-04": ("NB", "bulk-nb-04"),
            "bulk-nb-05": ("NB", "bulk-nb-05"),
            "bulk-nr-02": ("NR", "bulk-nr-02"),
            "sku-older": ("NB", "sku-older"),
            "sku-newer": ("NB", "sku-newer"),
            "only-one": ("NB", "only-one"),
        }
        for sku, (bu, code) in skus.items():
            existing = db.scalar(select(DimProduct).where(DimProduct.sku == sku))
            if existing is None:
                db.add(
                    DimProduct(
                        sku=sku,
                        name=code,
                        part_number=code,
                        sales_model_name=code,
                        business_unit=bu,
                        product_line=bu,
                        is_active=True,
                    )
                )
            else:
                existing.business_unit = bu
                existing.product_line = bu
                existing.part_number = code
                existing.sales_model_name = code
                existing.is_active = True
        db.commit()
    invalidate_product_resolution_index_cache()
    with SessionLocal() as db:
        cust = db.scalar(select(DimCustomer).where(DimCustomer.name == "Amazon"))
        assert cust is not None
        return int(cust.id)


def _run_preview_and_apply(
    files: list[tuple[str, bytes, str | None]],
    *,
    sync_parse: bool = False,
    session_id: int | None = None,
) -> tuple[dict, dict, int]:
    from app.db.session import AsyncSessionLocal
    from app.services.commercial_planner.lineup_bulk_backfill_apply import (
        apply_bulk_lineup_batch_sync,
        persist_preview_session,
    )
    from app.services.commercial_planner.lineup_bulk_backfill_preview import (
        BulkFileInput,
        build_bulk_lineup_preview,
    )

    async def _preview() -> tuple[dict, int]:
        inputs = [BulkFileInput(filename=n, file_bytes=b, folder_path=f) for n, b, f in files]
        async with AsyncSessionLocal() as db:
            preview = await build_bulk_lineup_preview(db, inputs)
            if session_id is None:
                job = await persist_preview_session(db, preview)
                return preview, int(job.id)
            return preview, session_id

    preview, sid = asyncio.run(_preview())

    parse_patch = (
        "app.services.commercial_planner.lineup_bulk_backfill_apply.enqueue_lineup_parse_sync"
    )
    if sync_parse:
        with patch(parse_patch, side_effect=_sync_enqueue_parse):
            apply_result = apply_bulk_lineup_batch_sync(sid)
    else:
        with patch(parse_patch, return_value={"outcome": "mock_enqueued", "task_id": "test"}):
            apply_result = apply_bulk_lineup_batch_sync(sid)

    return preview, apply_result, sid


@pytest.mark.usefixtures("bulk_smoke_env")
def test_bulk_lineup_apply_integration_on_disposable_clone():
    """End-to-end apply on cip_bulk_smoke: fan-out, 1H split, soft supersession, flag≠block, idempotency."""
    from app.db.session_sync import SessionLocal
    from app.models.commercial_lineup import CommercialLineupCase

    _seed_catalog()
    _clear_bulk_backfill_cases()

    files = [
        ("clean_single_bu.xlsx", _clean_single_bu_xlsx(), r"NB\2026\Q1"),
        ("multi_bu_sheet.xlsx", _multi_bu_xlsx(), r"NB\2026\Q2"),
        ("half_year.xlsx", _half_year_xlsx(), None),
        ("a_older_collision.xlsx", _collision_xlsx("older"), r"NB\2026\Q3"),
        ("z_newer_collision.xlsx", _collision_xlsx("newer"), r"NB\2026\Q3"),
        ("spec_dump.xlsx", _spec_dump_xlsx(), r"NB\2026\Q1"),
    ]

    preview, apply_result, session_id = _run_preview_and_apply(files)

    # --- catalogue miss worklist (advisory, does not block) ---
    wl_tokens = {w["token"].lower() for w in preview.get("catalogue_miss_worklist") or []}
    assert "bulk-unknown" in wl_tokens, "out-of-catalogue SKU should appear on worklist"

    # --- needs_attention diverted ---
    attention = apply_result.get("needs_attention") or []
    assert any(
        a.get("filename") == "spec_dump.xlsx" or "bu_likely_not_lineup" in (a.get("attention_reasons") or [])
        for a in attention
    ), "spec-dump file should divert to needs_attention"

    with SessionLocal() as db:
        cases = db.scalars(
            select(CommercialLineupCase).where(CommercialLineupCase.source_context == "bulk_lineup_backfill")
        ).all()
        case_count_first = len(cases)

        # --- single-BU case with business_unit + period ---
        clean_cases = [c for c in cases if c.file_name == "clean_single_bu.xlsx"]
        assert len(clean_cases) == 1
        assert clean_cases[0].business_unit == "NB"
        assert clean_cases[0].period_label == "2026 Q1"
        assert clean_cases[0].commercial_status == "draft_imported"
        assert clean_cases[0].superseded_by_case_id is None

        # --- multi-BU fan-out ---
        multi_cases = [c for c in cases if c.file_name == "multi_bu_sheet.xlsx"]
        assert len(multi_cases) >= 2
        multi_bus = {c.business_unit for c in multi_cases}
        assert "NB" in multi_bus and "NR" in multi_bus
        assert all(c.period_label == "2026 Q2" for c in multi_cases)

        # --- 1H → Q1 + Q2 ---
        half_cases = [c for c in cases if c.file_name == "half_year.xlsx"]
        half_labels = {c.period_label for c in half_cases}
        assert "2026 Q1" in half_labels and "2026 Q2" in half_labels
        assert len(half_cases) == 2

        # --- soft supersession: both cases exist, loser points to winner ---
        collision_cases = [c for c in cases if "collision" in (c.file_name or "")]
        assert len(collision_cases) == 2
        winner = next(c for c in collision_cases if c.file_name == "z_newer_collision.xlsx")
        loser = next(c for c in collision_cases if c.file_name == "a_older_collision.xlsx")
        assert winner.commercial_status == "draft_imported"
        assert winner.superseded_by_case_id is None
        assert loser.commercial_status == "superseded"
        assert loser.superseded_by_case_id == winner.id

        active_collision = [c for c in collision_cases if c.superseded_by_case_id is None]
        assert len(active_collision) == 1

        # --- spec dump not applied ---
        assert not any(c.file_name == "spec_dump.xlsx" for c in cases)

    # --- idempotency ---
    from app.services.commercial_planner.lineup_bulk_backfill_apply import apply_bulk_lineup_batch_sync

    with patch(
        "app.services.commercial_planner.lineup_bulk_backfill_apply.enqueue_lineup_parse_sync",
        return_value={"outcome": "mock_enqueued", "task_id": "test"},
    ):
        second = apply_bulk_lineup_batch_sync(session_id)

    assert second.get("skipped", 0) >= 1
    assert second.get("applied", 0) == 0
    with SessionLocal() as db:
        case_count_second = len(
            db.scalars(
                select(CommercialLineupCase).where(CommercialLineupCase.source_context == "bulk_lineup_backfill")
            ).all()
        )
    assert case_count_second == case_count_first, "re-apply must not double-create cases"


@pytest.mark.usefixtures("bulk_smoke_env")
def test_multi_bu_fan_out_slice_disjointness_and_existing_collisions():
    """Multi-BU sheet: parsed lines match preview slices; second preview surfaces collisions."""
    from app.db.session import AsyncSessionLocal
    from app.db.session_sync import SessionLocal
    from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine
    from app.services.commercial_planner.lineup_bulk_backfill_preview import (
        BulkFileInput,
        build_bulk_lineup_preview,
    )

    _seed_catalog()
    _clear_bulk_backfill_cases()

    file_name = "multi_bu_slice.xlsx"
    file_bytes = _multi_bu_slice_xlsx()
    files = [(file_name, file_bytes, r"NB\2026\Q2")]

    preview, apply_result, session_id = _run_preview_and_apply(files, sync_parse=True)

    ready = [p for p in preview.get("case_proposals") or [] if p.get("status") == "ready"]
    multi_props = [p for p in ready if p.get("filename") == file_name]
    assert len(multi_props) == 2
    by_bu = {p["business_unit"]: p for p in multi_props}
    assert by_bu["NB"]["row_count"] == 5
    assert by_bu["NR"]["row_count"] == 2
    assert by_bu["NB"].get("slice_source_rows")
    assert by_bu["NR"].get("slice_source_rows")
    assert set(by_bu["NB"]["slice_source_rows"]).isdisjoint(set(by_bu["NR"]["slice_source_rows"]))

    with SessionLocal() as db:
        cases = db.scalars(
            select(CommercialLineupCase).where(
                CommercialLineupCase.source_context == "bulk_lineup_backfill",
                CommercialLineupCase.file_name == file_name,
            )
        ).all()
        assert len(cases) == 2
        lines_by_case: dict[int, list[CommercialLineupLine]] = {}
        for case in cases:
            lines = db.scalars(
                select(CommercialLineupLine).where(CommercialLineupLine.case_id == case.id)
            ).all()
            lines_by_case[int(case.id)] = list(lines)

        nb_case = next(c for c in cases if c.business_unit == "NB")
        nr_case = next(c for c in cases if c.business_unit == "NR")
        assert len(lines_by_case[int(nb_case.id)]) == 5
        assert len(lines_by_case[int(nr_case.id)]) == 2

        nb_rows = {(ln.source_row_number, ln.product_id) for ln in lines_by_case[int(nb_case.id)]}
        nr_rows = {(ln.source_row_number, ln.product_id) for ln in lines_by_case[int(nr_case.id)]}
        assert nb_rows.isdisjoint(nr_rows)
        assert len(nb_rows | nr_rows) == 7

    from app.services.commercial_planner.lineup_bulk_backfill_apply import apply_bulk_lineup_batch_sync

    with patch(
        "app.services.commercial_planner.lineup_bulk_backfill_apply.enqueue_lineup_parse_sync",
        return_value={"outcome": "mock_enqueued", "task_id": "test"},
    ):
        second_apply = apply_bulk_lineup_batch_sync(session_id)
    assert second_apply.get("applied", 0) == 0
    assert second_apply.get("skipped", 0) >= 2

    async def _second_preview() -> dict:
        async with AsyncSessionLocal() as db:
            return await build_bulk_lineup_preview(
                db,
                [BulkFileInput(filename=file_name, file_bytes=file_bytes, folder_path=r"NB\2026\Q2")],
            )

    preview2 = asyncio.run(_second_preview())
    existing_collisions = preview2.get("existing_case_collisions") or []
    assert len(existing_collisions) >= 2
    proposed_keys = {
        m.get("proposal_key")
        for g in existing_collisions
        for m in g.get("members") or []
        if m.get("kind") == "proposed_case"
    }
    assert len(proposed_keys) >= 2
