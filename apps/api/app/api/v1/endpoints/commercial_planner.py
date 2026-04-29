from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone

from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete as sa_delete, distinct, func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_db
from app.models.commercial_lineup import (
    COMMERCIAL_LINEUP_STATUSES,
    CommercialLineupCase,
    CommercialLineupLine,
)
from app.models.commercial_planner import (
    CommercialCustomerTerm,
    CommercialDistributorTerm,
    CommercialPlan,
    CommercialPlanLine,
    CommercialSkuAssumption,
)
from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
from app.models.facts import FactForecast, FactPricing, FactSalesSellout
from app.models.historical_lineup import HistoricalLineupImportHeader, HistoricalLineupImportLine
from app.models.ingestion import ImportJob
from app.services.commercial_planner.calculator import CommercialCalcInputs, compute_line_economics
from app.services.commercial_planner.current_lineup_seed import CurrentLineupSourceNotConfiguredError
from app.services.commercial_planner.lineup_entity_resolution import (
    RESOLUTION_ALLOWED_CASE_STATUSES,
    apply_entity_resolutions,
    collect_entity_resolution_candidates,
)
from app.services.commercial_planner.lineup_case_parser import parse_current_lineup_file
from app.services.commercial_planner.lineup_open_channel import (
    CHANNEL_ROUTE_UPLOADED_CELL_KEY,
    STAGING_OPEN_CHANNEL_KEY,
    distributor_unassigned_soft,
    lineup_line_is_open_channel_staging,
    managed_customer_token_unresolved,
    sync_skip_detail_message,
    sync_ui_severity_for_line,
    uploaded_columns_from_payload,
)
from app.services.commercial_planner.lineup_plan_sync import (
    CAP_COMMERCIAL_PLAN_SYNC_KEY,
    attach_plan_line_sync_to_lineup_row,
    synced_commercial_plan_line_id,
)
from app.services.commercial_planner.open_channel_customer import get_open_channel_customer_id
from app.services.commercial_planner.unassigned_distributor import get_unassigned_distributor_id
from app.services.commercial_planner.read_model import (
    plan_line_read_model_extensions,
    product_specs_from_json,
    specs_json_flat_string_map,
)
from app.services.commercial_planner.suggestions import (
    SuggestionInputs,
    build_promo_mix_suggestion,
    build_pricing_suggestion,
    build_quantity_suggestion,
)

router = APIRouter()

ALLOWED_PLAN_STATUSES = {"draft", "review", "approved", "published"}


class PlanCreate(BaseModel):
    plan_name: str = Field(min_length=1, max_length=256)
    period_start: date
    period_end: date | None = None
    owner: str | None = None
    environment: str | None = None
    country_code: str | None = None
    currency_code: str = Field(default="USD", max_length=8)
    notes: str | None = None


class PlanPatch(BaseModel):
    plan_name: str | None = None
    status: str | None = None
    owner: str | None = None
    notes: str | None = None


class PlanLineCreate(BaseModel):
    customer_id: int
    distributor_id: int
    product_id: int
    target_units: float
    target_srp_local: float
    promo_srp_local: float | None = None
    promo_mix_pct: float = 0.5
    launch_date: date | None = None
    promo_start_date: date | None = None
    notes: str | None = None
    override_customer_margin_pct: float | None = None
    override_customer_rebate_pct: float | None = None
    override_distributor_margin_pct: float | None = None
    override_landed_cost_usd: float | None = None
    override_vat_rate_pct: float | None = None
    override_fx_rate_to_usd: float | None = None
    override_reserve_total_pct: float | None = None
    override_promo_reserve_split_pct: float | None = None


class PlanLinePatch(PlanLineCreate):
    customer_id: int | None = None
    distributor_id: int | None = None
    product_id: int | None = None
    target_units: float | None = None
    target_srp_local: float | None = None
    promo_mix_pct: float | None = None


class ClearBody(BaseModel):
    confirm: bool = False


class SyncToPlanRequest(BaseModel):
    commercial_plan_id: int | None = None
    fallback_customer_id: int | None = None
    fallback_distributor_id: int | None = None
    default_srp_local: float | None = None
    allow_zero_quantity: bool = False


def _line_payload(
    line: CommercialPlanLine,
    *,
    customer_code: str | None = None,
    customer_name: str | None = None,
    distributor_code: str | None = None,
    distributor_name: str | None = None,
    product_sku: str | None = None,
    product_name: str | None = None,
    product_part_number: str | None = None,
    product_model_name: str | None = None,
    product_sales_model_name: str | None = None,
    product_category: str | None = None,
    product_form_factor: str | None = None,
    product_lifecycle_status: str | None = None,
    product_line: str | None = None,
    product_series_name: str | None = None,
    product_business_unit: str | None = None,
    read_extensions: dict | None = None,
) -> dict:
    out = {
        "id": line.id,
        "commercial_plan_id": line.commercial_plan_id,
        "customer_id": line.customer_id,
        "distributor_id": line.distributor_id,
        "product_id": line.product_id,
        "customer_code": customer_code,
        "customer_name": customer_name,
        "distributor_code": distributor_code,
        "distributor_name": distributor_name,
        "product_sku": product_sku,
        "product_name": product_name,
        "product_part_number": product_part_number,
        "product_model_name": product_model_name,
        "product_sales_model_name": product_sales_model_name,
        "product_category": product_category,
        "product_form_factor": product_form_factor,
        "product_lifecycle_status": product_lifecycle_status,
        "product_line": product_line,
        "product_series_name": product_series_name,
        "product_business_unit": product_business_unit,
        "target_units": float(line.target_units),
        "target_srp_local": float(line.target_srp_local),
        "promo_srp_local": float(line.promo_srp_local) if line.promo_srp_local is not None else None,
        "promo_mix_pct": float(line.promo_mix_pct),
        "launch_date": line.launch_date.isoformat() if line.launch_date else None,
        "promo_start_date": line.promo_start_date.isoformat() if line.promo_start_date else None,
        "notes": line.notes,
        "calc_sell_in_price_usd": float(line.calc_sell_in_price_usd) if line.calc_sell_in_price_usd is not None else None,
        "calc_buy_price_usd": float(line.calc_buy_price_usd) if line.calc_buy_price_usd is not None else None,
        "calc_promo_reserve_usd": float(line.calc_promo_reserve_usd) if line.calc_promo_reserve_usd is not None else None,
        "calc_non_promo_reserve_usd": float(line.calc_non_promo_reserve_usd) if line.calc_non_promo_reserve_usd is not None else None,
        "calc_internal_gp_usd": float(line.calc_internal_gp_usd) if line.calc_internal_gp_usd is not None else None,
        "calc_customer_gp_pct": float(line.calc_customer_gp_pct) if line.calc_customer_gp_pct is not None else None,
        "calc_distributor_gp_pct": float(line.calc_distributor_gp_pct) if line.calc_distributor_gp_pct is not None else None,
        "calc_flags": line.calc_flags or [],
        "calc_explanation": line.calc_explanation,
        "override_customer_margin_pct": float(line.override_customer_margin_pct) if line.override_customer_margin_pct is not None else None,
        "override_customer_rebate_pct": float(line.override_customer_rebate_pct) if line.override_customer_rebate_pct is not None else None,
        "override_distributor_margin_pct": float(line.override_distributor_margin_pct) if line.override_distributor_margin_pct is not None else None,
        "override_landed_cost_usd": float(line.override_landed_cost_usd) if line.override_landed_cost_usd is not None else None,
        "override_vat_rate_pct": float(line.override_vat_rate_pct) if line.override_vat_rate_pct is not None else None,
        "override_fx_rate_to_usd": float(line.override_fx_rate_to_usd) if line.override_fx_rate_to_usd is not None else None,
        "override_reserve_total_pct": float(line.override_reserve_total_pct) if line.override_reserve_total_pct is not None else None,
        "override_promo_reserve_split_pct": float(line.override_promo_reserve_split_pct)
        if line.override_promo_reserve_split_pct is not None
        else None,
    }
    if read_extensions:
        out.update(read_extensions)
    return out


async def _line_payload_for_row(db: AsyncSession, line: CommercialPlanLine) -> dict:
    r = (
        await db.execute(
            select(
                DimCustomer.code,
                DimCustomer.name,
                DimDistributor.code,
                DimDistributor.name,
                DimProduct.sku,
                DimProduct.name,
                DimProduct.part_number,
                DimProduct.model_name,
                DimProduct.sales_model_name,
                DimProduct.category,
                DimProduct.form_factor,
                DimProduct.lifecycle_status,
                DimProduct.product_line,
                DimProduct.series_name,
                DimProduct.business_unit,
                DimProduct.specs_json,
                CommercialCustomerTerm.customer_margin_pct,
                CommercialCustomerTerm.customer_rebate_pct,
                CommercialDistributorTerm.distributor_margin_pct,
                CommercialSkuAssumption.vat_rate_pct,
                CommercialSkuAssumption.fx_rate_to_usd,
                CommercialSkuAssumption.reserve_total_pct,
                CommercialSkuAssumption.promo_reserve_split_pct,
                CommercialSkuAssumption.landed_cost_usd,
            )
            .select_from(CommercialPlanLine)
            .join(DimCustomer, DimCustomer.id == CommercialPlanLine.customer_id)
            .join(DimDistributor, DimDistributor.id == CommercialPlanLine.distributor_id)
            .join(DimProduct, DimProduct.id == CommercialPlanLine.product_id)
            .outerjoin(CommercialCustomerTerm, CommercialCustomerTerm.customer_id == CommercialPlanLine.customer_id)
            .outerjoin(CommercialDistributorTerm, CommercialDistributorTerm.distributor_id == CommercialPlanLine.distributor_id)
            .outerjoin(CommercialSkuAssumption, CommercialSkuAssumption.product_id == CommercialPlanLine.product_id)
            .where(CommercialPlanLine.id == line.id)
        )
    ).one_or_none()
    if r is None:
        return _line_payload(line)
    (
        cc,
        cn,
        dc,
        dn,
        ps,
        pn,
        ppn,
        pmn,
        psmn,
        pcat,
        pff,
        plcs,
        pline,
        psn,
        pbu,
        specs_json,
        ct_margin,
        ct_rebate,
        dt_margin,
        sa_vat,
        sa_fx,
        sa_reserve,
        sa_pr,
        sa_landed,
    ) = r
    read_ext = plan_line_read_model_extensions(
        line,
        specs_json if isinstance(specs_json, dict) else None,
        customer_margin_pct=float(ct_margin) if ct_margin is not None else None,
        customer_rebate_pct=float(ct_rebate) if ct_rebate is not None else None,
        distributor_margin_pct=float(dt_margin) if dt_margin is not None else None,
        sku_vat_rate_pct=float(sa_vat) if sa_vat is not None else None,
        sku_fx_rate_to_usd=float(sa_fx) if sa_fx is not None else None,
        sku_reserve_total_pct=float(sa_reserve) if sa_reserve is not None else None,
        sku_promo_reserve_split_pct=float(sa_pr) if sa_pr is not None else None,
        sku_landed_cost_usd=float(sa_landed) if sa_landed is not None else None,
    )
    return _line_payload(
        line,
        customer_code=cc,
        customer_name=cn,
        distributor_code=dc,
        distributor_name=dn,
        product_sku=ps,
        product_name=pn,
        product_part_number=ppn,
        product_model_name=pmn,
        product_sales_model_name=psmn,
        product_category=pcat,
        product_form_factor=pff,
        product_lifecycle_status=plcs,
        product_line=pline,
        product_series_name=psn,
        product_business_unit=pbu,
        read_extensions=read_ext,
    )


async def _resolve_terms_and_calc(db: AsyncSession, line: CommercialPlanLine) -> tuple[dict, list[str]]:
    missing: list[str] = []
    cterm = (
        await db.execute(select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == line.customer_id))
    ).scalars().first()
    dterm = (
        await db.execute(
            select(CommercialDistributorTerm).where(CommercialDistributorTerm.distributor_id == line.distributor_id)
        )
    ).scalars().first()
    sku = (
        await db.execute(select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id == line.product_id))
    ).scalars().first()
    if cterm is None:
        missing.append("missing_customer_term")
    if dterm is None:
        missing.append("missing_distributor_term")
    if sku is None:
        missing.append("missing_sku_assumption")

    inp = CommercialCalcInputs(
        target_units=float(line.target_units),
        target_srp_local=float(line.target_srp_local),
        promo_srp_local=float(line.promo_srp_local) if line.promo_srp_local is not None else None,
        promo_mix_pct=float(line.promo_mix_pct),
        fx_rate_to_usd=float(line.override_fx_rate_to_usd or (sku.fx_rate_to_usd if sku else 1.0)),
        vat_rate_pct=float(line.override_vat_rate_pct or (sku.vat_rate_pct if sku else 0.15)),
        landed_cost_usd=float(line.override_landed_cost_usd or (sku.landed_cost_usd if sku else 0.0)),
        customer_margin_pct=float(line.override_customer_margin_pct or (cterm.customer_margin_pct if cterm else 0.0)),
        customer_rebate_pct=float(line.override_customer_rebate_pct or (cterm.customer_rebate_pct if cterm else 0.0)),
        distributor_margin_pct=float(
            line.override_distributor_margin_pct or (dterm.distributor_margin_pct if dterm else 0.0)
        ),
        reserve_total_pct=float(line.override_reserve_total_pct or (sku.reserve_total_pct if sku else 0.10)),
        promo_reserve_split_pct=float(
            line.override_promo_reserve_split_pct or (sku.promo_reserve_split_pct if sku else 0.50)
        ),
    )
    calc = compute_line_economics(inp)
    payload = {
        "calc_sell_in_price_usd": calc.sell_in_price_usd,
        "calc_buy_price_usd": calc.buy_price_usd,
        "calc_promo_reserve_usd": calc.promo_reserve_usd,
        "calc_non_promo_reserve_usd": calc.non_promo_reserve_usd,
        "calc_internal_gp_usd": calc.internal_gp_usd,
        "calc_customer_gp_pct": calc.customer_gp_pct,
        "calc_distributor_gp_pct": calc.distributor_gp_pct,
        "calc_flags": list(dict.fromkeys([*missing, *calc.flags])),
        "calc_explanation": calc.explanation,
    }
    return payload, payload["calc_flags"]


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    plans = (await db.execute(select(CommercialPlan).order_by(CommercialPlan.id.desc()))).scalars().all()
    out = []
    for p in plans:
        line_count = (
            await db.execute(select(func.count(CommercialPlanLine.id)).where(CommercialPlanLine.commercial_plan_id == p.id))
        ).scalar_one()
        out.append(
            {
                "id": p.id,
                "plan_name": p.plan_name,
                "status": p.status,
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat() if p.period_end else None,
                "owner": p.owner,
                "environment": p.environment,
                "country_code": p.country_code,
                "currency_code": p.currency_code,
                "notes": p.notes,
                "line_count": int(line_count),
            }
        )
    return out


@router.post("/plans", status_code=201)
async def create_plan(body: PlanCreate, db: AsyncSession = Depends(get_db)):
    plan = CommercialPlan(**body.model_dump())
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return {"id": plan.id}


@router.patch("/plans/{plan_id}")
async def patch_plan(plan_id: int, body: PlanPatch, db: AsyncSession = Depends(get_db)):
    plan = await db.get(CommercialPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] not in ALLOWED_PLAN_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of: {', '.join(sorted(ALLOWED_PLAN_STATUSES))}")
    for k, v in data.items():
        setattr(plan, k, v)
    await db.commit()
    await db.refresh(plan)
    return {"id": plan.id, "status": plan.status}


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(
    plan_id: int,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Delete a commercial plan. Only draft plans may be deleted.

    If the plan has planner lines, ``force=true`` must be passed to confirm.
    Any current-lineup sync markers (``_cip_commercial_plan_sync``) that reference
    this plan are cleared from CommercialLineupLine.raw_row_payload to prevent
    stale workbench filtering.
    """
    plan = await db.get(CommercialPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    if plan.status != "draft":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot delete plan '{plan.plan_name}' with status '{plan.status}'. "
                "Only draft plans may be deleted."
            ),
        )
    lines = (
        await db.execute(select(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id))
    ).scalars().all()
    if lines and not force:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Plan '{plan.plan_name}' has {len(lines)} planner line(s). "
                "Pass force=true to confirm deletion. "
                "All planner lines and current-lineup sync markers for this plan will be removed."
            ),
        )
    # Clean up JSONB sync markers in current-lineup rows that reference this plan
    linked_lineup_lines = (
        await db.execute(
            select(CommercialLineupLine).where(
                CommercialLineupLine.raw_row_payload.contains(
                    {CAP_COMMERCIAL_PLAN_SYNC_KEY: {"commercial_plan_id": plan_id}}
                )
            )
        )
    ).scalars().all()
    for ll in linked_lineup_lines:
        if isinstance(ll.raw_row_payload, dict):
            payload = dict(ll.raw_row_payload)
            payload.pop(CAP_COMMERCIAL_PLAN_SYNC_KEY, None)
            ll.raw_row_payload = payload
    # Flush JSONB updates for lineup lines before deleting plan rows
    await db.flush()
    # Use a bulk SQL DELETE for plan lines so the FK is cleared immediately,
    # before the ORM tries to delete the parent plan row.
    # (ORM per-row db.delete() defers to flush and may order plan before lines.)
    await db.execute(
        sa_delete(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id)
    )
    await db.delete(plan)
    await db.commit()
    return Response(status_code=204)


@router.get("/plans/{plan_id}/lines")
async def list_plan_lines(plan_id: int, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(
                CommercialPlanLine,
                DimCustomer.code.label("customer_code"),
                DimCustomer.name.label("customer_name"),
                DimDistributor.code.label("distributor_code"),
                DimDistributor.name.label("distributor_name"),
                DimProduct.sku.label("product_sku"),
                DimProduct.name.label("product_name"),
                DimProduct.part_number.label("product_part_number"),
                DimProduct.model_name.label("product_model_name"),
                DimProduct.sales_model_name.label("product_sales_model_name"),
                DimProduct.category.label("product_category"),
                DimProduct.form_factor.label("product_form_factor"),
                DimProduct.lifecycle_status.label("product_lifecycle_status"),
                DimProduct.product_line.label("product_line"),
                DimProduct.series_name.label("product_series_name"),
                DimProduct.business_unit.label("product_business_unit"),
                DimProduct.specs_json.label("product_specs_json"),
                CommercialCustomerTerm.customer_margin_pct.label("row_ct_margin"),
                CommercialCustomerTerm.customer_rebate_pct.label("row_ct_rebate"),
                CommercialDistributorTerm.distributor_margin_pct.label("row_dt_margin"),
                CommercialSkuAssumption.vat_rate_pct.label("row_sa_vat"),
                CommercialSkuAssumption.fx_rate_to_usd.label("row_sa_fx"),
                CommercialSkuAssumption.reserve_total_pct.label("row_sa_reserve"),
                CommercialSkuAssumption.promo_reserve_split_pct.label("row_sa_pr"),
                CommercialSkuAssumption.landed_cost_usd.label("row_sa_landed"),
            )
            .join(DimCustomer, DimCustomer.id == CommercialPlanLine.customer_id)
            .join(DimDistributor, DimDistributor.id == CommercialPlanLine.distributor_id)
            .join(DimProduct, DimProduct.id == CommercialPlanLine.product_id)
            .outerjoin(CommercialCustomerTerm, CommercialCustomerTerm.customer_id == CommercialPlanLine.customer_id)
            .outerjoin(CommercialDistributorTerm, CommercialDistributorTerm.distributor_id == CommercialPlanLine.distributor_id)
            .outerjoin(CommercialSkuAssumption, CommercialSkuAssumption.product_id == CommercialPlanLine.product_id)
            .where(CommercialPlanLine.commercial_plan_id == plan_id)
            .order_by(CommercialPlanLine.id)
        )
    ).all()
    out = []
    for (
        line,
        cc,
        cn,
        dc,
        dn,
        ps,
        pn,
        ppn,
        pmn,
        psmn,
        pcat,
        pff,
        plcs,
        pline,
        psn,
        pbu,
        specs_json,
        ct_margin,
        ct_rebate,
        dt_margin,
        sa_vat,
        sa_fx,
        sa_reserve,
        sa_pr,
        sa_landed,
    ) in rows:
        read_ext = plan_line_read_model_extensions(
            line,
            specs_json if isinstance(specs_json, dict) else None,
            customer_margin_pct=float(ct_margin) if ct_margin is not None else None,
            customer_rebate_pct=float(ct_rebate) if ct_rebate is not None else None,
            distributor_margin_pct=float(dt_margin) if dt_margin is not None else None,
            sku_vat_rate_pct=float(sa_vat) if sa_vat is not None else None,
            sku_fx_rate_to_usd=float(sa_fx) if sa_fx is not None else None,
            sku_reserve_total_pct=float(sa_reserve) if sa_reserve is not None else None,
            sku_promo_reserve_split_pct=float(sa_pr) if sa_pr is not None else None,
            sku_landed_cost_usd=float(sa_landed) if sa_landed is not None else None,
        )
        out.append(
            _line_payload(
                line,
                customer_code=cc,
                customer_name=cn,
                distributor_code=dc,
                distributor_name=dn,
                product_sku=ps,
                product_name=pn,
                product_part_number=ppn,
                product_model_name=pmn,
                product_sales_model_name=psmn,
                product_category=pcat,
                product_form_factor=pff,
                product_lifecycle_status=plcs,
                product_line=pline,
                product_series_name=psn,
                product_business_unit=pbu,
                read_extensions=read_ext,
            )
        )
    return out


@router.post("/plans/{plan_id}/lines", status_code=201)
async def create_plan_line(plan_id: int, body: PlanLineCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(CommercialPlan, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    for model, pk, label in (
        (DimCustomer, body.customer_id, "customer"),
        (DimDistributor, body.distributor_id, "distributor"),
        (DimProduct, body.product_id, "product"),
    ):
        if not await db.get(model, pk):
            raise HTTPException(status_code=400, detail=f"Unknown {label}_id={pk}")
    line = CommercialPlanLine(commercial_plan_id=plan_id, **body.model_dump())
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return {"id": line.id}


@router.patch("/lines/{line_id}")
async def patch_plan_line(line_id: int, body: PlanLinePatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialPlanLine, line_id)
    if not row:
        raise HTTPException(status_code=404, detail="Line not found")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    for field, model in (
        ("customer_id", DimCustomer),
        ("distributor_id", DimDistributor),
        ("product_id", DimProduct),
    ):
        if field in data and data[field] is not None and not await db.get(model, data[field]):
            raise HTTPException(status_code=400, detail=f"Unknown {field.replace('_id', '')}_id={data[field]}")
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return await _line_payload_for_row(db, row)


@router.delete("/lines/{line_id}", status_code=204)
async def delete_plan_line(line_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialPlanLine, line_id)
    if not row:
        raise HTTPException(status_code=404, detail="Line not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.post("/plans/{plan_id}/recalculate")
async def recalculate_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id))
    ).scalars().all()
    if not rows:
        return {"updated": 0, "plan_id": plan_id, "flags": []}
    all_flags: list[str] = []
    for row in rows:
        payload, flags = await _resolve_terms_and_calc(db, row)
        for k, v in payload.items():
            setattr(row, k, v)
        all_flags.extend(flags)
    await db.commit()
    return {"updated": len(rows), "plan_id": plan_id, "flags": sorted(set(all_flags))}


@router.get("/plans/{plan_id}/summary")
async def get_plan_summary(plan_id: int, db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(select(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id))
    ).scalars().all()
    total_units = 0.0
    total_gp = 0.0
    total_promo_reserve = 0.0
    total_nonpromo_reserve = 0.0
    flags: set[str] = set()
    for row in rows:
        total_units += float(row.target_units)
        total_gp += float(row.calc_internal_gp_usd or 0.0)
        total_promo_reserve += float(row.calc_promo_reserve_usd or 0.0)
        total_nonpromo_reserve += float(row.calc_non_promo_reserve_usd or 0.0)
        for f in row.calc_flags or []:
            flags.add(str(f))
    return {
        "plan_id": plan_id,
        "line_count": len(rows),
        "total_units": round(total_units, 4),
        "total_internal_gp_usd": round(total_gp, 4),
        "total_promo_reserve_usd": round(total_promo_reserve, 4),
        "total_non_promo_reserve_usd": round(total_nonpromo_reserve, 4),
        "flags": sorted(flags),
    }


@router.get("/plans/{plan_id}/suggestions")
async def get_plan_suggestions(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Return suggestions for every line in a plan.

    Queries are batched: 5 SQL round-trips total regardless of line count.
    Prior-planned uses data from *other* plans only (same product+customer pair).
    Lineup evidence is sourced from the latest historical_lineup apply job — DAP is
    never used as landed_cost_usd.
    """
    rows = (
        await db.execute(
            select(CommercialPlanLine)
            .where(CommercialPlanLine.commercial_plan_id == plan_id)
            .order_by(CommercialPlanLine.id)
        )
    ).scalars().all()
    if not rows:
        return []

    product_ids = list({r.product_id for r in rows})
    cust_prod_pairs = list({(r.customer_id, r.product_id) for r in rows})

    # ── 1. Batch avg sellout per (customer_id, product_id) ───────────────────
    sellout_rows = (
        await db.execute(
            select(
                FactSalesSellout.customer_id,
                FactSalesSellout.product_id,
                func.coalesce(func.avg(FactSalesSellout.units), 0).label("avg_units"),
            )
            .where(tuple_(FactSalesSellout.customer_id, FactSalesSellout.product_id).in_(cust_prod_pairs))
            .group_by(FactSalesSellout.customer_id, FactSalesSellout.product_id)
        )
    ).all()
    avg_sellout_map: dict[tuple[int, int], float] = {
        (r.customer_id, r.product_id): float(r.avg_units) for r in sellout_rows
    }

    # ── 2. Batch prior planned from OTHER plans per (customer_id, product_id) ─
    prior_rows = (
        await db.execute(
            select(
                CommercialPlanLine.customer_id,
                CommercialPlanLine.product_id,
                func.avg(CommercialPlanLine.target_units).label("avg_units"),
            )
            .where(
                CommercialPlanLine.commercial_plan_id != plan_id,
                tuple_(CommercialPlanLine.customer_id, CommercialPlanLine.product_id).in_(cust_prod_pairs),
            )
            .group_by(CommercialPlanLine.customer_id, CommercialPlanLine.product_id)
        )
    ).all()
    prior_planned_map: dict[tuple[int, int], float] = {
        (r.customer_id, r.product_id): float(r.avg_units) for r in prior_rows
    }

    # ── 3. Batch latest forecast per product_id (window function) ────────────
    forecast_sq = (
        select(
            FactForecast.product_id,
            FactForecast.forecast_units,
            func.row_number()
            .over(partition_by=FactForecast.product_id, order_by=FactForecast.period_start.desc())
            .label("rn"),
        )
        .where(FactForecast.product_id.in_(product_ids))
        .subquery()
    )
    forecast_rows = (
        await db.execute(
            select(forecast_sq.c.product_id, forecast_sq.c.forecast_units).where(forecast_sq.c.rn == 1)
        )
    ).all()
    forecast_map: dict[int, float] = {r.product_id: float(r.forecast_units) for r in forecast_rows}

    # ── 4. Batch latest net price per product_id (window function) ───────────
    pricing_sq = (
        select(
            FactPricing.product_id,
            FactPricing.net_price,
            func.row_number()
            .over(partition_by=FactPricing.product_id, order_by=FactPricing.effective_date.desc())
            .label("rn"),
        )
        .where(FactPricing.product_id.in_(product_ids))
        .subquery()
    )
    pricing_rows = (
        await db.execute(
            select(pricing_sq.c.product_id, pricing_sq.c.net_price).where(pricing_sq.c.rn == 1)
        )
    ).all()
    pricing_map: dict[int, float] = {r.product_id: float(r.net_price) for r in pricing_rows}

    # ── 5. Batch lineup evidence per product_id (latest apply job) ───────────
    latest_job_id = await db.scalar(
        select(func.max(HistoricalLineupImportHeader.import_job_id))
        .join(HistoricalLineupImportLine, HistoricalLineupImportLine.header_id == HistoricalLineupImportHeader.id)
        .join(ImportJob, ImportJob.id == HistoricalLineupImportHeader.import_job_id)
        .where(
            HistoricalLineupImportLine.product_id.in_(product_ids),
            ImportJob.import_mode == "apply",
            ImportJob.template_slug == "historical_lineup",
        )
    )
    lineup_map: dict[int, dict] = {}
    if latest_job_id:
        lineup_ev_rows = (
            await db.execute(
                select(
                    HistoricalLineupImportLine.product_id,
                    func.max(HistoricalLineupImportLine.msrp_local).label("msrp_local"),
                    func.max(HistoricalLineupImportLine.promo_price_local).label("promo_price_local"),
                    func.sum(HistoricalLineupImportLine.quantity_units).label("total_quantity_units"),
                    func.max(HistoricalLineupImportHeader.period_label).label("period_label"),
                )
                .join(
                    HistoricalLineupImportHeader,
                    HistoricalLineupImportHeader.id == HistoricalLineupImportLine.header_id,
                )
                .where(
                    HistoricalLineupImportHeader.import_job_id == latest_job_id,
                    HistoricalLineupImportLine.product_id.in_(product_ids),
                )
                .group_by(HistoricalLineupImportLine.product_id)
            )
        ).all()
        for lr in lineup_ev_rows:
            lineup_map[lr.product_id] = {
                "msrp_local": float(lr.msrp_local) if lr.msrp_local is not None else None,
                "promo_price_local": float(lr.promo_price_local) if lr.promo_price_local is not None else None,
                "total_quantity_units": float(lr.total_quantity_units) if lr.total_quantity_units is not None else None,
                "period_label": lr.period_label,
                "job_id": latest_job_id,
            }

    # ── Build output ─────────────────────────────────────────────────────────
    out: list[dict] = []
    for row in rows:
        key = (row.customer_id, row.product_id)
        le = lineup_map.get(row.product_id, {})
        inp = SuggestionInputs(
            avg_sellout_units=avg_sellout_map.get(key, 0.0),
            prior_planned_units=prior_planned_map.get(key),
            forecast_units=forecast_map.get(row.product_id),
            latest_net_price=pricing_map.get(row.product_id),
            target_srp_local=float(row.target_srp_local),
            promo_mix_pct=float(row.promo_mix_pct),
            lineup_msrp_local=le.get("msrp_local"),
            lineup_promo_price_local=le.get("promo_price_local"),
            lineup_quantity_units=le.get("total_quantity_units"),
            lineup_period_label=le.get("period_label"),
            lineup_job_id=le.get("job_id"),
        )
        qty, qty_reason, qty_conf = build_quantity_suggestion(inp)
        srp, promo_srp, price_reason, price_conf = build_pricing_suggestion(inp)
        mix, mix_reason, mix_conf = build_promo_mix_suggestion(inp)
        out.append(
            {
                "line_id": row.id,
                "suggestions": [
                    {
                        "type": "target_units",
                        "value": qty,
                        "reason": qty_reason,
                        "confidence": qty_conf,
                        "factors": {
                            "avg_sellout_units": inp.avg_sellout_units,
                            "prior_planned_units": inp.prior_planned_units,
                            "forecast_units": inp.forecast_units,
                            "lineup_quantity_units": inp.lineup_quantity_units,
                            "lineup_job_id": inp.lineup_job_id,
                        },
                    },
                    {
                        "type": "pricing_band",
                        "value": {"target_srp_local": srp, "promo_srp_local": promo_srp},
                        "reason": price_reason,
                        "confidence": price_conf,
                        "factors": {
                            "latest_net_price": inp.latest_net_price,
                            "lineup_msrp_local": inp.lineup_msrp_local,
                            "lineup_promo_price_local": inp.lineup_promo_price_local,
                            "lineup_period_label": inp.lineup_period_label,
                            "target_srp_local": inp.target_srp_local,
                        },
                    },
                    {
                        "type": "promo_mix_pct",
                        "value": mix,
                        "reason": mix_reason,
                        "confidence": mix_conf,
                        "factors": {
                            "avg_sellout_units": inp.avg_sellout_units,
                            "forecast_units": inp.forecast_units,
                        },
                    },
                ],
                "_meta": {
                    "lineup_job_id": inp.lineup_job_id,
                    "lineup_period_label": inp.lineup_period_label,
                    "data_sources": {
                        "sellout": inp.avg_sellout_units > 0,
                        "prior_planned": inp.prior_planned_units is not None,
                        "forecast": inp.forecast_units is not None,
                        "net_price": inp.latest_net_price is not None,
                        "lineup": inp.lineup_job_id is not None,
                    },
                },
            }
        )
    return out


@router.get("/plans/{plan_id}/readiness")
async def get_plan_readiness(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Return a data-readiness gate summary for a plan (read-only).

    Reports how many lines are missing customer terms, distributor terms, and SKU
    assumptions.  These gaps cause the calculator to fall back to zeroed inputs and
    suggestions to be low-confidence or empty.  No writes are performed.
    """
    plan = await db.get(CommercialPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    rows = (
        await db.execute(select(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id))
    ).scalars().all()

    if not rows:
        open_channel_dim_ok = await get_open_channel_customer_id(db) is not None
        unassigned_dim_ok = await get_unassigned_distributor_id(db) is not None
        parts0: list[str] = []
        if not open_channel_dim_ok:
            parts0.append(
                "Admin/setup: dim_customer OPEN_CHANNEL missing — run `alembic upgrade head` or "
                "`python scripts/seed.py --commercial-system-reference-only`."
            )
        if not unassigned_dim_ok:
            parts0.append(
                "Admin/setup: dim_distributor UNASSIGNED missing — run `alembic upgrade head` or "
                "`python scripts/seed.py --commercial-system-reference-only`."
            )
        return {
            "plan_id": plan_id,
            "line_count": 0,
            "missing_customer_term": 0,
            "missing_distributor_term": 0,
            "missing_sku_assumption": 0,
            "lines_with_calc_flags": 0,
            "ready": open_channel_dim_ok and unassigned_dim_ok,
            "system_reference_open_channel_dim_ok": open_channel_dim_ok,
            "system_reference_unassigned_distributor_dim_ok": unassigned_dim_ok,
            "readiness_summary": (
                "; ".join(parts0) if parts0 else "No lines in plan."
            ),
        }

    product_ids = list({r.product_id for r in rows})
    customer_ids = list({r.customer_id for r in rows})
    distributor_ids = list({r.distributor_id for r in rows})

    existing_cterms: set[int] = set(
        (await db.execute(
            select(CommercialCustomerTerm.customer_id).where(CommercialCustomerTerm.customer_id.in_(customer_ids))
        )).scalars().all()
    )
    existing_dterms: set[int] = set(
        (await db.execute(
            select(CommercialDistributorTerm.distributor_id).where(
                CommercialDistributorTerm.distributor_id.in_(distributor_ids)
            )
        )).scalars().all()
    )
    existing_skus: set[int] = set(
        (await db.execute(
            select(CommercialSkuAssumption.product_id).where(CommercialSkuAssumption.product_id.in_(product_ids))
        )).scalars().all()
    )

    missing_ct = sum(1 for r in rows if r.customer_id not in existing_cterms)
    missing_dt = sum(1 for r in rows if r.distributor_id not in existing_dterms)
    missing_sku = sum(1 for r in rows if r.product_id not in existing_skus)
    lines_with_flags = sum(1 for r in rows if r.calc_flags)

    parts: list[str] = []

    open_channel_dim_ok = await get_open_channel_customer_id(db) is not None
    unassigned_dim_ok = await get_unassigned_distributor_id(db) is not None
    if not open_channel_dim_ok:
        parts.append(
            "Admin/setup: dim_customer OPEN_CHANNEL missing — run `alembic upgrade head` or "
            "`python scripts/seed.py --commercial-system-reference-only` (not created from uploads)."
        )
    if not unassigned_dim_ok:
        parts.append(
            "Admin/setup: dim_distributor UNASSIGNED missing — run `alembic upgrade head` or "
            "`python scripts/seed.py --commercial-system-reference-only` (not created from uploads)."
        )

    ready = (
        missing_ct == 0
        and missing_dt == 0
        and missing_sku == 0
        and open_channel_dim_ok
        and unassigned_dim_ok
    )
    if missing_ct:
        parts.append(f"{missing_ct} line(s) missing customer terms")
    if missing_dt:
        parts.append(f"{missing_dt} line(s) missing distributor terms")
    if missing_sku:
        parts.append(f"{missing_sku} line(s) missing SKU assumptions")
    if lines_with_flags:
        parts.append(f"{lines_with_flags} line(s) have economics flags")

    return {
        "plan_id": plan_id,
        "line_count": len(rows),
        "missing_customer_term": missing_ct,
        "missing_distributor_term": missing_dt,
        "missing_sku_assumption": missing_sku,
        "lines_with_calc_flags": lines_with_flags,
        "ready": ready,
        "system_reference_open_channel_dim_ok": open_channel_dim_ok,
        "system_reference_unassigned_distributor_dim_ok": unassigned_dim_ok,
        "readiness_summary": "; ".join(parts) if parts else "All defaults present.",
    }


@router.get("/lineup-evidence")
async def get_lineup_evidence(
    product_id: int = Query(..., description="DimProduct.id to fetch lineup evidence for"),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated lineup evidence for a single product from the latest apply job (read-only).

    DAP (Distributor Acquisition Price) is the source/import value from the historical lineup.
    It is NOT equivalent to landed_cost_usd and must never be mapped directly as a cost input.
    Returns evidence=null when no apply job has a line for this product.
    """
    latest_job_id = await db.scalar(
        select(func.max(HistoricalLineupImportHeader.import_job_id))
        .join(HistoricalLineupImportLine, HistoricalLineupImportLine.header_id == HistoricalLineupImportHeader.id)
        .join(ImportJob, ImportJob.id == HistoricalLineupImportHeader.import_job_id)
        .where(
            HistoricalLineupImportLine.product_id == product_id,
            ImportJob.import_mode == "apply",
            ImportJob.template_slug == "historical_lineup",
        )
    )
    if latest_job_id is None:
        return {
            "product_id": product_id,
            "lineup_job_id": None,
            "evidence": None,
            "cost_semantics_note": _COST_SEMANTICS_NOTE,
        }

    r = (
        await db.execute(
            select(
                func.max(HistoricalLineupImportLine.msrp_local).label("msrp_local"),
                func.max(HistoricalLineupImportLine.promo_price_local).label("promo_price_local"),
                func.max(HistoricalLineupImportLine.dap_local).label("dap_local"),
                func.max(HistoricalLineupImportLine.actual_dap_local).label("actual_dap_local"),
                func.max(HistoricalLineupImportLine.disti_margin_pct).label("disti_margin_pct"),
                func.max(HistoricalLineupImportLine.vat_pct).label("vat_pct"),
                func.max(HistoricalLineupImportLine.rebate_pct).label("rebate_pct"),
                func.sum(HistoricalLineupImportLine.quantity_units).label("total_quantity_units"),
                func.count(HistoricalLineupImportLine.id).label("line_count"),
                func.max(HistoricalLineupImportHeader.period_label).label("period_label"),
            )
            .join(
                HistoricalLineupImportHeader,
                HistoricalLineupImportHeader.id == HistoricalLineupImportLine.header_id,
            )
            .where(
                HistoricalLineupImportHeader.import_job_id == latest_job_id,
                HistoricalLineupImportLine.product_id == product_id,
            )
        )
    ).one()

    return {
        "product_id": product_id,
        "lineup_job_id": latest_job_id,
        "evidence": {
            "msrp_local": float(r.msrp_local) if r.msrp_local is not None else None,
            "promo_price_local": float(r.promo_price_local) if r.promo_price_local is not None else None,
            "dap_local": float(r.dap_local) if r.dap_local is not None else None,
            "actual_dap_local": float(r.actual_dap_local) if r.actual_dap_local is not None else None,
            "disti_margin_pct": float(r.disti_margin_pct) if r.disti_margin_pct is not None else None,
            "vat_pct": float(r.vat_pct) if r.vat_pct is not None else None,
            "rebate_pct": float(r.rebate_pct) if r.rebate_pct is not None else None,
            "total_quantity_units": float(r.total_quantity_units) if r.total_quantity_units is not None else None,
            "line_count": int(r.line_count),
            "period_label": r.period_label,
        },
        "cost_semantics_note": _COST_SEMANTICS_NOTE,
    }


class ApplySuggestionBody(BaseModel):
    line_id: int
    suggestion_type: str
    value: float | int | dict


@router.post("/apply-suggestion")
async def apply_suggestion(body: ApplySuggestionBody, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialPlanLine, body.line_id)
    if not row:
        raise HTTPException(status_code=404, detail="Line not found")
    if body.suggestion_type == "target_units":
        if not isinstance(body.value, (int, float)):
            raise HTTPException(status_code=400, detail="target_units suggestion requires numeric value")
        row.target_units = float(body.value)
    elif body.suggestion_type == "promo_mix_pct":
        if not isinstance(body.value, (int, float)):
            raise HTTPException(status_code=400, detail="promo_mix_pct suggestion requires numeric value")
        row.promo_mix_pct = float(body.value)
    elif body.suggestion_type == "pricing_band":
        if not isinstance(body.value, dict):
            raise HTTPException(status_code=400, detail="pricing_band suggestion requires object value")
        target = body.value.get("target_srp_local")
        promo = body.value.get("promo_srp_local")
        if target is not None:
            row.target_srp_local = float(target)
        if promo is not None:
            row.promo_srp_local = float(promo)
    else:
        raise HTTPException(status_code=400, detail="Unsupported suggestion_type")
    await db.commit()
    await db.refresh(row)
    return await _line_payload_for_row(db, row)


# --- Planner defaults: commercial terms & SKU assumptions (bounded maintenance) ---


class CustomerTermCreate(BaseModel):
    customer_id: int
    customer_margin_pct: float = Field(ge=0.0, le=0.95)
    customer_rebate_pct: float = Field(ge=0.0, le=0.95)

    @model_validator(mode="after")
    def margin_stack(self):
        if self.customer_margin_pct + self.customer_rebate_pct >= 0.92:
            raise ValueError("customer_margin_pct + customer_rebate_pct must stay below 0.92 for a viable channel stack")
        return self


class CustomerTermPatch(BaseModel):
    customer_margin_pct: float | None = Field(default=None, ge=0.0, le=0.95)
    customer_rebate_pct: float | None = Field(default=None, ge=0.0, le=0.95)


class DistributorTermCreate(BaseModel):
    distributor_id: int
    distributor_margin_pct: float = Field(ge=0.0, le=0.92)


class DistributorTermPatch(BaseModel):
    distributor_margin_pct: float | None = Field(default=None, ge=0.0, le=0.92)


class SkuAssumptionCreate(BaseModel):
    product_id: int
    landed_cost_usd: float = Field(gt=0)
    vat_rate_pct: float = Field(ge=0.0, le=1.0)
    fx_rate_to_usd: float = Field(gt=0)
    reserve_total_pct: float = Field(ge=0.0, le=1.0)
    promo_reserve_split_pct: float = Field(ge=0.0, le=1.0)


class SkuAssumptionPatch(BaseModel):
    landed_cost_usd: float | None = Field(default=None, gt=0)
    vat_rate_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    fx_rate_to_usd: float | None = Field(default=None, gt=0)
    reserve_total_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    promo_reserve_split_pct: float | None = Field(default=None, ge=0.0, le=1.0)


def _customer_term_json(row: CommercialCustomerTerm, customer_code: str, customer_name: str) -> dict:
    return {
        "id": row.id,
        "customer_id": row.customer_id,
        "customer_code": customer_code,
        "customer_name": customer_name,
        "customer_margin_pct": float(row.customer_margin_pct),
        "customer_rebate_pct": float(row.customer_rebate_pct),
    }


def _distributor_term_json(row: CommercialDistributorTerm, distributor_code: str, distributor_name: str) -> dict:
    return {
        "id": row.id,
        "distributor_id": row.distributor_id,
        "distributor_code": distributor_code,
        "distributor_name": distributor_name,
        "distributor_margin_pct": float(row.distributor_margin_pct),
    }


def _sku_assumption_json(row: CommercialSkuAssumption, sku: str, product_name: str) -> dict:
    return {
        "id": row.id,
        "product_id": row.product_id,
        "product_sku": sku,
        "product_name": product_name,
        "landed_cost_usd": float(row.landed_cost_usd),
        "vat_rate_pct": float(row.vat_rate_pct),
        "fx_rate_to_usd": float(row.fx_rate_to_usd),
        "reserve_total_pct": float(row.reserve_total_pct),
        "promo_reserve_split_pct": float(row.promo_reserve_split_pct),
    }


@router.get("/customer-terms")
async def list_customer_terms(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None, description="Filter by customer code or name"),
    customer_id: int | None = Query(default=None, description="Exact dim_customer.id (non-breaking filter)"),
):
    stmt = (
        select(CommercialCustomerTerm, DimCustomer.code, DimCustomer.name)
        .join(DimCustomer, DimCustomer.id == CommercialCustomerTerm.customer_id)
        .order_by(DimCustomer.code)
    )
    if customer_id is not None:
        stmt = stmt.where(CommercialCustomerTerm.customer_id == customer_id)
    elif q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(DimCustomer.code.ilike(needle), DimCustomer.name.ilike(needle)))
    rows = (await db.execute(stmt)).all()
    return [_customer_term_json(t, code, name) for t, code, name in rows]


@router.post("/customer-terms", status_code=201)
async def create_customer_term(body: CustomerTermCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(DimCustomer, body.customer_id):
        raise HTTPException(status_code=400, detail=f"Unknown customer_id={body.customer_id}")
    dup = (
        await db.execute(select(CommercialCustomerTerm).where(CommercialCustomerTerm.customer_id == body.customer_id))
    ).scalars().first()
    if dup:
        raise HTTPException(status_code=409, detail="A commercial term already exists for this customer")
    row = CommercialCustomerTerm(
        customer_id=body.customer_id,
        customer_margin_pct=body.customer_margin_pct,
        customer_rebate_pct=body.customer_rebate_pct,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create customer term (duplicate or constraint violation)")
    await db.refresh(row)
    cust = await db.get(DimCustomer, row.customer_id)
    assert cust
    return _customer_term_json(row, cust.code, cust.name)


@router.patch("/customer-terms/{term_id}")
async def patch_customer_term(term_id: int, body: CustomerTermPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialCustomerTerm, term_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer term not found")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    eff_margin = float(data["customer_margin_pct"]) if "customer_margin_pct" in data else float(row.customer_margin_pct)
    eff_rebate = float(data["customer_rebate_pct"]) if "customer_rebate_pct" in data else float(row.customer_rebate_pct)
    if eff_margin + eff_rebate >= 0.92:
        raise HTTPException(
            status_code=400,
            detail="customer_margin_pct + customer_rebate_pct must stay below 0.92 for a viable channel stack",
        )
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    cust = await db.get(DimCustomer, row.customer_id)
    assert cust
    return _customer_term_json(row, cust.code, cust.name)


@router.delete("/customer-terms/{term_id}", status_code=204)
async def delete_customer_term(term_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialCustomerTerm, term_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer term not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.get("/distributor-terms")
async def list_distributor_terms(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None),
    distributor_id: int | None = Query(default=None, description="Exact dim_distributor.id (non-breaking filter)"),
):
    stmt = (
        select(CommercialDistributorTerm, DimDistributor.code, DimDistributor.name)
        .join(DimDistributor, DimDistributor.id == CommercialDistributorTerm.distributor_id)
        .order_by(DimDistributor.code)
    )
    if distributor_id is not None:
        stmt = stmt.where(CommercialDistributorTerm.distributor_id == distributor_id)
    elif q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(DimDistributor.code.ilike(needle), DimDistributor.name.ilike(needle)))
    rows = (await db.execute(stmt)).all()
    return [_distributor_term_json(t, code, name) for t, code, name in rows]


@router.post("/distributor-terms", status_code=201)
async def create_distributor_term(body: DistributorTermCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(DimDistributor, body.distributor_id):
        raise HTTPException(status_code=400, detail=f"Unknown distributor_id={body.distributor_id}")
    dup = (
        await db.execute(
            select(CommercialDistributorTerm).where(CommercialDistributorTerm.distributor_id == body.distributor_id)
        )
    ).scalars().first()
    if dup:
        raise HTTPException(status_code=409, detail="A commercial term already exists for this distributor")
    row = CommercialDistributorTerm(distributor_id=body.distributor_id, distributor_margin_pct=body.distributor_margin_pct)
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create distributor term (duplicate or constraint violation)")
    await db.refresh(row)
    dist = await db.get(DimDistributor, row.distributor_id)
    assert dist
    return _distributor_term_json(row, dist.code, dist.name)


@router.patch("/distributor-terms/{term_id}")
async def patch_distributor_term(term_id: int, body: DistributorTermPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialDistributorTerm, term_id)
    if not row:
        raise HTTPException(status_code=404, detail="Distributor term not found")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    dist = await db.get(DimDistributor, row.distributor_id)
    assert dist
    return _distributor_term_json(row, dist.code, dist.name)


@router.delete("/distributor-terms/{term_id}", status_code=204)
async def delete_distributor_term(term_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialDistributorTerm, term_id)
    if not row:
        raise HTTPException(status_code=404, detail="Distributor term not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


@router.get("/sku-assumptions")
async def list_sku_assumptions(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None),
):
    stmt = (
        select(CommercialSkuAssumption, DimProduct.sku, DimProduct.name)
        .join(DimProduct, DimProduct.id == CommercialSkuAssumption.product_id)
        .order_by(DimProduct.sku)
    )
    if q and q.strip():
        needle = f"%{q.strip()}%"
        stmt = stmt.where(or_(DimProduct.sku.ilike(needle), DimProduct.name.ilike(needle)))
    rows = (await db.execute(stmt)).all()
    return [_sku_assumption_json(t, sku, name) for t, sku, name in rows]


@router.post("/sku-assumptions", status_code=201)
async def create_sku_assumption(body: SkuAssumptionCreate, db: AsyncSession = Depends(get_db)):
    if not await db.get(DimProduct, body.product_id):
        raise HTTPException(status_code=400, detail=f"Unknown product_id={body.product_id}")
    dup = (
        await db.execute(select(CommercialSkuAssumption).where(CommercialSkuAssumption.product_id == body.product_id))
    ).scalars().first()
    if dup:
        raise HTTPException(status_code=409, detail="A SKU assumption already exists for this product")
    row = CommercialSkuAssumption(
        product_id=body.product_id,
        landed_cost_usd=body.landed_cost_usd,
        vat_rate_pct=body.vat_rate_pct,
        fx_rate_to_usd=body.fx_rate_to_usd,
        reserve_total_pct=body.reserve_total_pct,
        promo_reserve_split_pct=body.promo_reserve_split_pct,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Could not create SKU assumption (duplicate or constraint violation)")
    await db.refresh(row)
    prod = await db.get(DimProduct, row.product_id)
    assert prod
    return _sku_assumption_json(row, prod.sku or "", prod.name or "")


@router.patch("/sku-assumptions/{assumption_id}")
async def patch_sku_assumption(assumption_id: int, body: SkuAssumptionPatch, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialSkuAssumption, assumption_id)
    if not row:
        raise HTTPException(status_code=404, detail="SKU assumption not found")
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    prod = await db.get(DimProduct, row.product_id)
    assert prod
    return _sku_assumption_json(row, prod.sku or "", prod.name or "")


@router.delete("/sku-assumptions/{assumption_id}", status_code=204)
async def delete_sku_assumption(assumption_id: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(CommercialSkuAssumption, assumption_id)
    if not row:
        raise HTTPException(status_code=404, detail="SKU assumption not found")
    await db.delete(row)
    await db.commit()
    return Response(status_code=204)


# ─── Lineup Coverage (read-only) ─────────────────────────────────────────────
# Diagnostic codes that are informational-only and do not constitute a commercial
# warning in the Lineup Coverage view.
_COVERAGE_NON_WARNING_CODES: frozenset[str] = frozenset(
    {"historical_lineup_processed", "historical_lineup_sheet_summary"}
)

# Included verbatim in lineup-product-gaps responses.  DAP is NOT equivalent to landed_cost_usd.
# Never map dap_local directly to landed_cost_usd without explicit cost-basis verification.
_COST_SEMANTICS_NOTE = (
    "DAP (Distributor Acquisition Price) is the source/import value from the historical lineup. "
    "It is not equivalent to landed_cost_usd and must not be used as a cost input to the planner "
    "without verification of the cost basis."
)


@router.get("/lineup-jobs")
async def list_lineup_jobs(db: AsyncSession = Depends(get_db)):
    """List apply-mode historical_lineup import jobs with line counts for the Lineup Coverage view.

    Only jobs that produced a persisted header (i.e. the apply succeeded and wrote at least
    a header record) are included.  Ordered newest-first.
    """
    stmt = (
        select(
            ImportJob.id,
            ImportJob.file_name,
            ImportJob.status,
            ImportJob.stage,
            HistoricalLineupImportHeader.period_label,
            HistoricalLineupImportHeader.country_code,
            HistoricalLineupImportHeader.currency_code,
            func.count(HistoricalLineupImportLine.id).label("line_count"),
        )
        .join(HistoricalLineupImportHeader, HistoricalLineupImportHeader.import_job_id == ImportJob.id)
        .outerjoin(
            HistoricalLineupImportLine,
            HistoricalLineupImportLine.header_id == HistoricalLineupImportHeader.id,
        )
        .where(ImportJob.template_slug == "historical_lineup", ImportJob.import_mode == "apply")
        .group_by(
            ImportJob.id,
            ImportJob.file_name,
            ImportJob.status,
            ImportJob.stage,
            HistoricalLineupImportHeader.period_label,
            HistoricalLineupImportHeader.country_code,
            HistoricalLineupImportHeader.currency_code,
        )
        .order_by(ImportJob.id.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": r.id,
            "file_name": r.file_name,
            "status": r.status,
            "stage": r.stage,
            "period_label": r.period_label,
            "country_code": r.country_code,
            "currency_code": r.currency_code,
            "line_count": int(r.line_count),
        }
        for r in rows
    ]


@router.get("/lineup-coverage")
async def get_lineup_coverage(
    job_id: int = Query(..., description="ImportJob.id for a historical_lineup apply job"),
    db: AsyncSession = Depends(get_db),
):
    """Return enriched lineup lines for a historical_lineup apply job (Lineup Coverage view).

    Returns 400 when job_id does not resolve to a historical_lineup apply job with a persisted
    header.  Each line includes pre-computed has_warnings and has_unknown_customer flags so the
    frontend does not need to parse diagnostic_codes for conditional rendering.
    """
    header = await db.scalar(
        select(HistoricalLineupImportHeader)
        .join(ImportJob, ImportJob.id == HistoricalLineupImportHeader.import_job_id)
        .where(
            HistoricalLineupImportHeader.import_job_id == job_id,
            ImportJob.template_slug == "historical_lineup",
            ImportJob.import_mode == "apply",
        )
    )
    if header is None:
        raise HTTPException(
            status_code=400,
            detail=f"job_id={job_id} is not a historical_lineup apply job or has no persisted header.",
        )

    header_customer = aliased(DimCustomer, name="header_customer")
    header_dist = aliased(DimDistributor, name="header_distributor")
    stmt = (
        select(
            HistoricalLineupImportLine,
            HistoricalLineupImportHeader.period_label,
            HistoricalLineupImportHeader.country_code,
            HistoricalLineupImportHeader.currency_code,
            DimProduct.sku.label("product_sku"),
            DimProduct.name.label("product_name"),
            HistoricalLineupImportHeader.customer_id.label("header_customer_id"),
            header_customer.code.label("header_customer_code"),
            header_customer.name.label("header_customer_name"),
            HistoricalLineupImportHeader.distributor_id.label("header_distributor_id"),
            header_dist.code.label("header_distributor_code"),
            header_dist.name.label("header_distributor_name"),
        )
        .join(
            HistoricalLineupImportHeader,
            HistoricalLineupImportHeader.id == HistoricalLineupImportLine.header_id,
        )
        .outerjoin(DimProduct, DimProduct.id == HistoricalLineupImportLine.product_id)
        .outerjoin(header_customer, header_customer.id == HistoricalLineupImportHeader.customer_id)
        .outerjoin(header_dist, header_dist.id == HistoricalLineupImportHeader.distributor_id)
        .where(HistoricalLineupImportHeader.import_job_id == job_id)
        .order_by(HistoricalLineupImportLine.source_row_number)
    )
    rows = (await db.execute(stmt)).all()

    result: list[dict] = []
    for (
        ln,
        period_label,
        country_code,
        currency_code,
        product_sku,
        product_name,
        header_customer_id,
        header_customer_code,
        header_customer_name,
        header_distributor_id,
        header_distributor_code,
        header_distributor_name,
    ) in rows:
        codes: list[str] = ln.diagnostic_codes or []
        has_warnings = any(c not in _COVERAGE_NON_WARNING_CODES for c in codes)
        has_unknown_customer = "unknown_customer" in codes
        customer_token = (ln.raw_row_payload or {}).get("customer_token")
        result.append(
            {
                "id": ln.id,
                "source_row_number": ln.source_row_number,
                "product_id": ln.product_id,
                "product_sku": product_sku,
                "product_name": product_name,
                "part_number_raw": ln.part_number_raw,
                "model_raw": ln.model_raw,
                "base_unit_raw": ln.base_unit_raw,
                "quantity_units": float(ln.quantity_units) if ln.quantity_units is not None else None,
                "msrp_local": float(ln.msrp_local) if ln.msrp_local is not None else None,
                "promo_price_local": float(ln.promo_price_local) if ln.promo_price_local is not None else None,
                "dap_local": float(ln.dap_local) if ln.dap_local is not None else None,
                "disti_margin_pct": float(ln.disti_margin_pct) if ln.disti_margin_pct is not None else None,
                "customer_token": customer_token,
                "diagnostic_codes": codes,
                "has_warnings": has_warnings,
                "has_unknown_customer": has_unknown_customer,
                "month_split_json": ln.month_split_json,
                "actual_dap_local": float(ln.actual_dap_local) if ln.actual_dap_local is not None else None,
                "disti_cost_local": float(ln.disti_cost_local) if ln.disti_cost_local is not None else None,
                "rebate_pct": float(ln.rebate_pct) if ln.rebate_pct is not None else None,
                "dealer_margin_pct": float(ln.dealer_margin_pct) if ln.dealer_margin_pct is not None else None,
                "vat_pct": float(ln.vat_pct) if ln.vat_pct is not None else None,
                "header_customer_id": header_customer_id,
                "header_customer_code": header_customer_code,
                "header_customer_name": header_customer_name,
                "header_distributor_id": int(header_distributor_id) if header_distributor_id is not None else None,
                "header_distributor_code": header_distributor_code,
                "header_distributor_name": header_distributor_name,
                "period_label": period_label,
                "country_code": country_code,
                "currency_code": currency_code,
            }
        )
    return result


@router.get("/lineup-product-gaps")
async def get_lineup_product_gaps(
    job_id: int = Query(..., description="ImportJob.id for a historical_lineup apply job"),
    db: AsyncSession = Depends(get_db),
):
    """Per-product evidence and gap summary for a historical_lineup apply job (read-only).

    Returns one record per resolved product in the job, aggregating lineup evidence fields and
    flagging which planner defaults are missing.  The cost_semantics_note field on each record
    makes explicit that DAP is NOT landed_cost_usd and must never be mapped directly as a cost
    input to the commercial planner.

    Returns 400 when job_id does not resolve to a historical_lineup apply job with a persisted
    header.
    """
    header = await db.scalar(
        select(HistoricalLineupImportHeader)
        .join(ImportJob, ImportJob.id == HistoricalLineupImportHeader.import_job_id)
        .where(
            HistoricalLineupImportHeader.import_job_id == job_id,
            ImportJob.template_slug == "historical_lineup",
            ImportJob.import_mode == "apply",
        )
    )
    if header is None:
        raise HTTPException(
            status_code=400,
            detail=f"job_id={job_id} is not a historical_lineup apply job or has no persisted header.",
        )

    stmt = (
        select(
            HistoricalLineupImportLine.product_id,
            DimProduct.sku.label("product_sku"),
            DimProduct.name.label("product_name"),
            func.max(HistoricalLineupImportLine.dap_local).label("dap_local"),
            func.max(HistoricalLineupImportLine.actual_dap_local).label("actual_dap_local"),
            func.max(HistoricalLineupImportLine.disti_cost_local).label("disti_cost_local"),
            func.max(HistoricalLineupImportLine.vat_pct).label("vat_pct"),
            func.max(HistoricalLineupImportLine.disti_margin_pct).label("disti_margin_pct"),
            func.max(HistoricalLineupImportLine.rebate_pct).label("rebate_pct"),
            func.max(HistoricalLineupImportLine.dealer_margin_pct).label("dealer_margin_pct"),
            func.sum(HistoricalLineupImportLine.quantity_units).label("total_quantity_units"),
            func.max(HistoricalLineupImportLine.msrp_local).label("msrp_local"),
            func.max(HistoricalLineupImportLine.promo_price_local).label("promo_price_local"),
            func.max(HistoricalLineupImportHeader.period_label).label("period_label"),
            func.max(CommercialSkuAssumption.id).label("sku_assumption_id"),
        )
        .join(HistoricalLineupImportHeader, HistoricalLineupImportHeader.id == HistoricalLineupImportLine.header_id)
        .join(DimProduct, DimProduct.id == HistoricalLineupImportLine.product_id)
        .outerjoin(CommercialSkuAssumption, CommercialSkuAssumption.product_id == HistoricalLineupImportLine.product_id)
        .where(
            HistoricalLineupImportHeader.import_job_id == job_id,
            HistoricalLineupImportLine.product_id.isnot(None),
        )
        .group_by(HistoricalLineupImportLine.product_id, DimProduct.sku, DimProduct.name)
        .order_by(DimProduct.sku)
    )
    rows = (await db.execute(stmt)).all()

    result: list[dict] = []
    for r in rows:
        gaps: list[str] = []
        if r.sku_assumption_id is None:
            gaps.append("missing_sku_assumption")
        if r.dap_local is None and r.actual_dap_local is None and r.disti_cost_local is None:
            gaps.append("no_cost_evidence_in_lineup")
        if r.vat_pct is None:
            gaps.append("no_vat_pct_in_lineup")
        if r.disti_margin_pct is None:
            gaps.append("no_disti_margin_pct_in_lineup")

        result.append(
            {
                "product_id": r.product_id,
                "product_sku": r.product_sku,
                "product_name": r.product_name,
                "has_sku_assumption": r.sku_assumption_id is not None,
                "lineup_evidence": {
                    "dap_local": float(r.dap_local) if r.dap_local is not None else None,
                    "actual_dap_local": float(r.actual_dap_local) if r.actual_dap_local is not None else None,
                    "disti_cost_local": float(r.disti_cost_local) if r.disti_cost_local is not None else None,
                    "vat_pct": float(r.vat_pct) if r.vat_pct is not None else None,
                    "disti_margin_pct": float(r.disti_margin_pct) if r.disti_margin_pct is not None else None,
                    "rebate_pct": float(r.rebate_pct) if r.rebate_pct is not None else None,
                    "dealer_margin_pct": float(r.dealer_margin_pct) if r.dealer_margin_pct is not None else None,
                    "total_quantity_units": float(r.total_quantity_units) if r.total_quantity_units is not None else None,
                    "msrp_local": float(r.msrp_local) if r.msrp_local is not None else None,
                    "promo_price_local": float(r.promo_price_local) if r.promo_price_local is not None else None,
                    "period_label": r.period_label,
                },
                "assumption_gaps": gaps,
                "cost_semantics_note": _COST_SEMANTICS_NOTE,
            }
        )
    return result


# ─── Commercial Lineup Cases ──────────────────────────────────────────────────

ALLOWED_CASE_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "draft_imported": ["validated", "cancelled"],
    "validated": ["pending_review", "cancelled"],
    "pending_review": ["accepted", "validated", "cancelled"],
    "accepted": ["po_pending", "cancelled"],
    "po_pending": ["po_issued", "cancelled"],
    "po_issued": ["in_fulfillment"],
    "in_fulfillment": ["received_closed"],
    "received_closed": [],
    "cancelled": [],
}

_LINEUP_DAP_SEMANTICS_NOTE = (
    "dap_evidence_local is sourced from the uploaded lineup file. "
    "It is NOT equivalent to landed_cost_usd and must not be used as a cost input "
    "to the commercial planner without explicit cost-basis verification."
)


class LineupCaseCreate(BaseModel):
    commercial_plan_id: int | None = None
    period_label: str | None = None
    currency_code: str | None = None
    country_code: str | None = None
    notes: str | None = None


class LineupCaseStatusPatch(BaseModel):
    status: str
    notes: str | None = None
    accepted_by: str | None = None


class CommercialLineupLinePatch(BaseModel):
    quantity_units: float | None = None
    msrp_local: float | None = None
    promo_price_evidence_local: float | None = None


class EntityResolutionItem(BaseModel):
    kind: Literal[
        "customer",
        "distributor",
        "customer_token_as_distributor",
        "distributor_token_as_customer",
    ]
    token: str = Field(min_length=1, max_length=512)
    action: Literal["map_existing", "create_dim", "mark_open_channel_staging"] = "map_existing"
    dim_id: int | None = Field(default=None, ge=1)
    new_code: str | None = Field(default=None, max_length=64)
    new_name: str | None = Field(default=None, max_length=256)
    confirm_create: bool = False

    @model_validator(mode="after")
    def _validate_action(self) -> EntityResolutionItem:
        if self.action == "mark_open_channel_staging":
            if self.kind != "customer":
                raise ValueError("mark_open_channel_staging requires kind=customer")
            return self
        if self.action == "create_dim":
            if not self.confirm_create:
                raise ValueError("confirm_create must be true for create_dim")
            if not (self.new_code and self.new_name):
                raise ValueError("new_code and new_name are required for create_dim")
            if self.kind not in ("customer", "distributor"):
                raise ValueError("create_dim requires kind=customer or kind=distributor")
            return self
        if self.dim_id is None:
            raise ValueError("dim_id is required for map_existing and redirect kinds")
        return self


class EntityResolutionApplyBody(BaseModel):
    resolutions: list[EntityResolutionItem] = Field(min_length=1)


def _case_payload(case: CommercialLineupCase, line_count: int) -> dict:
    return {
        "id": case.id,
        "import_job_id": case.import_job_id,
        "commercial_plan_id": case.commercial_plan_id,
        "file_name": case.file_name,
        "period_label": case.period_label,
        "country_code": case.country_code,
        "currency_code": case.currency_code,
        "import_intent": case.import_intent,
        "source_context": case.source_context,
        "commercial_status": case.commercial_status,
        "notes": case.notes,
        "accepted_at": case.accepted_at.isoformat() if case.accepted_at else None,
        "accepted_by": case.accepted_by,
        "line_count": line_count,
        "created_at": case.created_at.isoformat() if case.created_at else None,
    }


@router.get("/lineup-cases")
async def list_lineup_cases(
    plan_id: int | None = Query(default=None, description="Filter by commercial_plan_id"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CommercialLineupCase).order_by(CommercialLineupCase.id.desc())
    if plan_id is not None:
        stmt = stmt.where(CommercialLineupCase.commercial_plan_id == plan_id)
    cases = (await db.execute(stmt)).scalars().all()
    out = []
    for case in cases:
        line_count = (
            await db.execute(
                select(func.count(CommercialLineupLine.id)).where(CommercialLineupLine.case_id == case.id)
            )
        ).scalar_one()
        out.append(_case_payload(case, int(line_count)))
    return out


@router.post("/lineup-cases", status_code=201)
async def create_lineup_case(body: LineupCaseCreate, db: AsyncSession = Depends(get_db)):
    if body.commercial_plan_id is not None and not await db.get(CommercialPlan, body.commercial_plan_id):
        raise HTTPException(status_code=400, detail=f"Unknown commercial_plan_id={body.commercial_plan_id}")
    case = CommercialLineupCase(
        commercial_plan_id=body.commercial_plan_id,
        period_label=body.period_label,
        currency_code=body.currency_code,
        country_code=body.country_code,
        notes=body.notes,
        commercial_status="draft_imported",
        import_intent="current_working_lineup",
        source_context="commercial_planner",
    )
    db.add(case)
    await db.commit()
    await db.refresh(case)
    return _case_payload(case, 0)


@router.get("/lineup-cases/{case_id}")
async def get_lineup_case(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    line_count = (
        await db.execute(
            select(func.count(CommercialLineupLine.id)).where(CommercialLineupLine.case_id == case_id)
        )
    ).scalar_one()
    return _case_payload(case, int(line_count))


@router.get("/lineup-cases/{case_id}/entity-resolution-candidates")
async def get_lineup_entity_resolution_candidates(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status == "cancelled":
        raise HTTPException(status_code=409, detail="Case is cancelled")
    return await collect_entity_resolution_candidates(db, case_id)


def _workbench_parsed_field_metadata() -> list[dict[str, str]]:
    """Stable ids for lineup staging fields (not DB migration — API contract only)."""
    specs = [
        ("source_row_number", "Source row #"),
        ("sku_raw", "SKU (raw)"),
        ("part_number_raw", "Part # (raw)"),
        ("model_raw", "Model (raw)"),
        ("base_unit_raw", "Base unit (raw)"),
        ("quantity_units", "Quantity"),
        ("msrp_local", "MSRP / list (local)"),
        ("promo_price_evidence_local", "Promo price (evidence)"),
        ("dap_evidence_local", "DAP (evidence only)"),
        ("rebate_pct_evidence", "Rebate % (evidence)"),
        ("distributor_margin_pct_evidence", "Dealer margin % (evidence)"),
        ("vat_pct_evidence", "VAT % (evidence)"),
        ("customer_token", "Customer token (parsed column)"),
        ("distributor_token_raw", "Distributor token (from upload)"),
        ("row_status", "Row status"),
        ("mapping_confidence", "Mapping confidence"),
        ("diagnostic_codes", "Diagnostics"),
    ]
    return [{"id": f"parsed:{k}", "group": "parsed", "label": lab, "field": k} for k, lab in specs]


def _workbench_sync_field_metadata() -> list[dict[str, str]]:
    return [
        {"id": "sync:sync_eligible", "group": "sync", "label": "Sync eligible", "field": "sync_eligible"},
        {"id": "sync:sync_skip_reason", "group": "sync", "label": "Sync skip reason", "field": "sync_skip_reason"},
        {"id": "sync:sync_skip_detail", "group": "sync", "label": "Sync detail", "field": "sync_skip_detail"},
        {"id": "sync:sync_ui_severity", "group": "sync", "label": "Sync severity (UI)", "field": "sync_ui_severity"},
        {
            "id": "sync:sync_customer_resolution_note",
            "group": "sync",
            "label": "Sync customer resolution note",
            "field": "sync_customer_resolution_note",
        },
    ]


def _workbench_catalogue_product_field_metadata() -> list[dict[str, str]]:
    """Matched dim_product fields exposed on lineup lines when product is resolved (API keys on line dict)."""
    specs = [
        ("product_sku", "SKU (matched product)"),
        ("product_part_number", "Part # (matched product)"),
        ("product_name", "Product name (catalogue)"),
        ("product_model_name", "Model name (catalogue)"),
        ("product_sales_model_name", "Sales model (catalogue)"),
        ("catalogue_category", "Category (catalogue)"),
        ("catalogue_form_factor", "Form factor (catalogue)"),
        ("catalogue_product_line", "Product line (catalogue)"),
        ("catalogue_series_name", "Series (catalogue)"),
        ("catalogue_lifecycle_status", "Lifecycle (catalogue)"),
        ("catalogue_business_unit", "Business unit (catalogue)"),
        ("catalogue_marketing_name", "Marketing name (catalogue)"),
        ("catalogue_ean", "EAN (catalogue)"),
        ("catalogue_upc", "UPC (catalogue)"),
        ("product_spec_processor", "Processor (catalogue spec)"),
        ("product_spec_cpu", "CPU / chipset (catalogue spec)"),
    ]
    return [{"id": f"cat:{k}", "group": "catalogue", "label": lab, "field": k} for k, lab in specs]


@router.get("/lineup-cases/{case_id}/workbench-column-metadata")
async def get_lineup_workbench_column_metadata(case_id: int, db: AsyncSession = Depends(get_db)):
    """Union of raw upload headers, parsed field ids, DimProduct.specs_json keys, and sync field ids."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    lines = (
        (await db.execute(select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id)))
        .scalars()
        .all()
    )
    raw_columns: set[str] = set()
    product_ids: set[int] = set()
    for ln in lines:
        payload = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else None
        raw_columns.update(uploaded_columns_from_payload(payload).keys())
        if ln.product_id:
            product_ids.add(int(ln.product_id))
    spec_keys: set[str] = set()
    if product_ids:
        sjs = (
            await db.execute(select(DimProduct.specs_json).where(DimProduct.id.in_(list(product_ids))))
        ).scalars().all()
        for sj in sjs:
            flat = specs_json_flat_string_map(sj if isinstance(sj, dict) else None)
            spec_keys.update(flat.keys())
    proc_hints = sorted(k for k in spec_keys if re.search(r"cpu|processor", k, re.IGNORECASE))
    return {
        "case_id": case_id,
        "raw_columns": sorted(raw_columns),
        "parsed_fields": _workbench_parsed_field_metadata(),
        "catalogue_product_fields": _workbench_catalogue_product_field_metadata(),
        "catalogue_spec_keys": sorted(spec_keys),
        "processor_spec_key_hints": proc_hints,
        "sync_fields": _workbench_sync_field_metadata(),
    }


@router.post("/lineup-cases/{case_id}/entity-resolutions/apply", status_code=200)
async def post_lineup_entity_resolutions_apply(
    case_id: int,
    body: EntityResolutionApplyBody,
    db: AsyncSession = Depends(get_db),
):
    """Apply case-scoped token → DimCustomer / DimDistributor mappings. Does not touch DAP or cost fields."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status not in RESOLUTION_ALLOWED_CASE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                "Entity resolutions are only allowed while the case is in draft/review "
                f"(statuses: {', '.join(sorted(RESOLUTION_ALLOWED_CASE_STATUSES))}). "
                f"Current: '{case.commercial_status}'"
            ),
        )
    for item in body.resolutions:
        if item.action == "mark_open_channel_staging":
            continue
        if item.action == "create_dim":
            code = (item.new_code or "").strip()
            if item.kind == "customer":
                exists = await db.scalar(select(func.count()).select_from(DimCustomer).where(DimCustomer.code == code[:64]))
                if exists:
                    raise HTTPException(status_code=400, detail=f"Customer code already exists: {code[:64]}")
            else:
                exists = await db.scalar(
                    select(func.count()).select_from(DimDistributor).where(DimDistributor.code == code[:32])
                )
                if exists:
                    raise HTTPException(status_code=400, detail=f"Distributor code already exists: {code[:32]}")
            continue
        assert item.dim_id is not None
        if item.kind in ("customer", "distributor_token_as_customer"):
            if not await db.get(DimCustomer, item.dim_id):
                raise HTTPException(status_code=400, detail=f"Unknown customer_id={item.dim_id}")
        if item.kind in ("distributor", "customer_token_as_distributor"):
            if not await db.get(DimDistributor, item.dim_id):
                raise HTTPException(status_code=400, detail=f"Unknown distributor_id={item.dim_id}")
    raw = [item.model_dump() for item in body.resolutions]
    out = await apply_entity_resolutions(db, case_id, raw)
    await db.commit()
    return out


@router.patch("/lineup-cases/{case_id}/status")
async def patch_lineup_case_status(case_id: int, body: LineupCaseStatusPatch, db: AsyncSession = Depends(get_db)):
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if body.status not in COMMERCIAL_LINEUP_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status '{body.status}' is not a valid lineup case status",
        )
    allowed = ALLOWED_CASE_STATUS_TRANSITIONS.get(case.commercial_status, [])
    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot transition from '{case.commercial_status}' to '{body.status}'. "
                f"Allowed: {allowed or 'none (terminal state)'}"
            ),
        )
    case.commercial_status = body.status
    if body.notes is not None:
        case.notes = body.notes
    if body.status == "accepted":
        case.accepted_at = datetime.now(tz=timezone.utc)
        case.accepted_by = body.accepted_by
    await db.commit()
    await db.refresh(case)
    line_count = (
        await db.execute(
            select(func.count(CommercialLineupLine.id)).where(CommercialLineupLine.case_id == case_id)
        )
    ).scalar_one()
    return _case_payload(case, int(line_count))


def _lineup_row_needs_resolution(ln: CommercialLineupLine, raw_payload: dict) -> bool:
    """Heuristic: unsynced rows that still need product or entity work before sync."""
    if not ln.product_id or (ln.row_status or "").strip().lower() == "unresolved":
        return True
    if managed_customer_token_unresolved(ln):
        return True
    dist_tok = raw_payload.get("distributor_token")
    if ln.distributor_id is None and isinstance(dist_tok, str) and dist_tok.strip():
        return True
    return False


def _is_duplicate_in_planner(d: dict, *, need_eligibility: bool) -> bool:
    """Row already represented in plan by dedupe-key match (not via _cip marker)."""
    if not need_eligibility:
        return False
    return not bool(d.get("sync_eligible")) and d.get("sync_skip_reason") == "duplicate"


def _workbench_counts_payload(
    rows_payload: list[tuple[CommercialLineupLine, dict]],
    *,
    need_eligibility: bool,
) -> dict[str, int]:
    out: dict[str, int] = {
        "all_lines": len(rows_payload),
        "synced_to_planner": 0,
        "already_in_planner": 0,
        "ready_to_sync": 0,
        "blocked_from_sync": 0,
        "needs_resolution": 0,
    }
    for ln, d in rows_payload:
        raw = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
        if d.get("synced_commercial_plan_line_id"):
            out["synced_to_planner"] += 1
            continue
        if need_eligibility and "sync_eligible" in d:
            if d["sync_eligible"]:
                out["ready_to_sync"] += 1
            elif d.get("sync_skip_reason") == "duplicate":
                out["already_in_planner"] += 1
            else:
                out["blocked_from_sync"] += 1
        if _lineup_row_needs_resolution(ln, raw):
            out["needs_resolution"] += 1
    return out


def _workbench_scope_keep_line(d: dict, scope: str, *, need_eligibility: bool) -> bool:
    sid = d.get("synced_commercial_plan_line_id")
    if scope == "all":
        return True
    if scope == "active":
        if sid is not None:
            return False
        # Rows already represented in plan by dedupe key are not active work
        if _is_duplicate_in_planner(d, need_eligibility=need_eligibility):
            return False
        return True
    if scope == "synced":
        return sid is not None
    if not need_eligibility:
        return True
    if scope == "ready":
        return sid is None and bool(d.get("sync_eligible"))
    if scope == "blocked":
        return sid is None and not bool(d.get("sync_eligible"))
    return True


@router.get("/lineup-cases/{case_id}/lines")
async def list_lineup_case_lines(
    case_id: int,
    db: AsyncSession = Depends(get_db),
    include_sync_eligibility: bool = Query(default=False),
    include_raw_row_payload: bool = Query(default=False),
    include_product_specs: bool = Query(default=False),
    include_line_uploaded: bool = Query(default=False),
    fallback_customer_id: int | None = Query(default=None),
    fallback_distributor_id: int | None = Query(default=None),
    default_srp_local: float | None = Query(default=None),
    allow_zero_quantity: bool = Query(default=False),
    workbench_scope: Literal["active", "synced", "ready", "blocked", "all"] = Query(default="active"),
):
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if workbench_scope in ("ready", "blocked") and not case.commercial_plan_id:
        raise HTTPException(
            status_code=400,
            detail="workbench_scope 'ready' or 'blocked' requires commercial_plan_id on the lineup case.",
        )
    if include_sync_eligibility and not case.commercial_plan_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot compute sync eligibility: case has no commercial_plan_id.",
        )
    need_eligibility = bool(case.commercial_plan_id) and (
        include_sync_eligibility or workbench_scope in ("ready", "blocked")
    )
    stmt = (
        select(
            CommercialLineupLine,
            DimProduct.sku.label("product_sku"),
            DimProduct.name.label("product_name"),
            DimProduct.part_number.label("product_part_number"),
            DimProduct.model_name.label("product_model_name"),
            DimProduct.sales_model_name.label("product_sales_model_name"),
            DimProduct.specs_json.label("product_specs_json"),
            DimProduct.category.label("catalogue_category"),
            DimProduct.form_factor.label("catalogue_form_factor"),
            DimProduct.product_line.label("catalogue_product_line"),
            DimProduct.series_name.label("catalogue_series_name"),
            DimProduct.lifecycle_status.label("catalogue_lifecycle_status"),
            DimProduct.business_unit.label("catalogue_business_unit"),
            DimProduct.marketing_name.label("catalogue_marketing_name"),
            DimProduct.ean.label("catalogue_ean"),
            DimProduct.upc.label("catalogue_upc"),
            DimCustomer.code.label("customer_code"),
            DimCustomer.name.label("customer_name"),
            DimDistributor.code.label("distributor_code"),
            DimDistributor.name.label("distributor_name"),
        )
        .outerjoin(DimProduct, DimProduct.id == CommercialLineupLine.product_id)
        .outerjoin(DimCustomer, DimCustomer.id == CommercialLineupLine.customer_id)
        .outerjoin(DimDistributor, DimDistributor.id == CommercialLineupLine.distributor_id)
        .where(CommercialLineupLine.case_id == case_id)
        .order_by(CommercialLineupLine.source_row_number, CommercialLineupLine.id)
    )
    rows = (await db.execute(stmt)).all()
    rows_payload: list[tuple[CommercialLineupLine, dict]] = []
    for (
        ln,
        product_sku,
        product_name,
        product_part_number,
        product_model_name,
        product_sales_model_name,
        product_specs_json,
        catalogue_category,
        catalogue_form_factor,
        catalogue_product_line,
        catalogue_series_name,
        catalogue_lifecycle_status,
        catalogue_business_unit,
        catalogue_marketing_name,
        catalogue_ean,
        catalogue_upc,
        customer_code,
        customer_name,
        distributor_code,
        distributor_name,
    ) in rows:
        raw_payload = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
        distributor_token_raw = raw_payload.get("distributor_token")
        if distributor_token_raw is not None:
            distributor_token_raw = str(distributor_token_raw).strip() or None
        d: dict = {
            "id": ln.id,
            "case_id": ln.case_id,
            "source_row_number": ln.source_row_number,
            "product_id": ln.product_id,
            "product_sku": product_sku,
            "product_name": product_name,
            "product_part_number": product_part_number,
            "product_model_name": product_model_name,
            "product_sales_model_name": product_sales_model_name,
            "customer_id": ln.customer_id,
            "customer_code": customer_code,
            "customer_name": customer_name,
            "distributor_id": ln.distributor_id,
            "distributor_code": distributor_code,
            "distributor_name": distributor_name,
            "customer_token": ln.customer_token,
            "distributor_token_raw": distributor_token_raw,
            "sku_raw": ln.sku_raw,
            "part_number_raw": ln.part_number_raw,
            "model_raw": ln.model_raw,
            "base_unit_raw": ln.base_unit_raw,
            "quantity_units": float(ln.quantity_units) if ln.quantity_units is not None else None,
            "msrp_local": float(ln.msrp_local) if ln.msrp_local is not None else None,
            "promo_price_evidence_local": float(ln.promo_price_evidence_local)
            if ln.promo_price_evidence_local is not None
            else None,
            "dap_evidence_local": float(ln.dap_evidence_local) if ln.dap_evidence_local is not None else None,
            "rebate_pct_evidence": float(ln.rebate_pct_evidence) if ln.rebate_pct_evidence is not None else None,
            "distributor_margin_pct_evidence": float(ln.distributor_margin_pct_evidence)
            if ln.distributor_margin_pct_evidence is not None
            else None,
            "vat_pct_evidence": float(ln.vat_pct_evidence) if ln.vat_pct_evidence is not None else None,
            "diagnostic_codes": ln.diagnostic_codes or [],
            "row_status": ln.row_status,
            "mapping_confidence": float(ln.mapping_confidence) if ln.mapping_confidence is not None else None,
            "dap_semantics_note": _LINEUP_DAP_SEMANTICS_NOTE,
            "staging_open_channel": raw_payload.get(STAGING_OPEN_CHANNEL_KEY) is True,
            "channel_route_uploaded_cell": raw_payload.get(CHANNEL_ROUTE_UPLOADED_CELL_KEY)
            if isinstance(raw_payload.get(CHANNEL_ROUTE_UPLOADED_CELL_KEY), str)
            else None,
            "synced_commercial_plan_line_id": synced_commercial_plan_line_id(ln.raw_row_payload),
        }
        if include_product_specs:
            safe_specs_json = product_specs_json if isinstance(product_specs_json, dict) else None
            d["product_specs"] = safe_specs_json or {}
            # product_specs_flat is the flattened, non-empty-value map used by the column selector
            # and workbench spec: column rendering — same keys reported by workbench-column-metadata
            d["product_specs_flat"] = specs_json_flat_string_map(safe_specs_json)
            d["catalogue_category"] = catalogue_category
            d["catalogue_form_factor"] = catalogue_form_factor
            d["catalogue_product_line"] = catalogue_product_line
            d["catalogue_series_name"] = catalogue_series_name
            d["catalogue_lifecycle_status"] = catalogue_lifecycle_status
            d["catalogue_business_unit"] = catalogue_business_unit
            d["catalogue_marketing_name"] = catalogue_marketing_name
            d["catalogue_ean"] = catalogue_ean
            d["catalogue_upc"] = catalogue_upc
            spec_bits = product_specs_from_json(safe_specs_json)
            for k, v in spec_bits.items():
                if v is not None:
                    d[k] = v
        if include_line_uploaded:
            up = raw_payload.get("uploaded")
            d["uploaded"] = up if isinstance(up, dict) else {}
        if include_raw_row_payload:
            d["raw_row_payload"] = ln.raw_row_payload if isinstance(ln.raw_row_payload, dict) else {}
        rows_payload.append((ln, d))

    if need_eligibility:
        plan_id = case.commercial_plan_id
        if not plan_id:
            raise HTTPException(
                status_code=400,
                detail="Cannot compute sync eligibility: case has no commercial_plan_id.",
            )
        body = SyncToPlanRequest(
            commercial_plan_id=plan_id,
            fallback_customer_id=fallback_customer_id,
            fallback_distributor_id=fallback_distributor_id,
            default_srp_local=default_srp_local,
            allow_zero_quantity=allow_zero_quantity,
        )
        existing_stmt = select(
            CommercialPlanLine.customer_id,
            CommercialPlanLine.distributor_id,
            CommercialPlanLine.product_id,
        ).where(CommercialPlanLine.commercial_plan_id == plan_id)
        existing_rows = (await db.execute(existing_stmt)).all()
        keys_sim: set[tuple] = {(r.customer_id, r.distributor_id, r.product_id) for r in existing_rows}
        open_channel_customer_id = await get_open_channel_customer_id(db)
        unassigned_distributor_id = await get_unassigned_distributor_id(db)
        for ln, d in rows_payload:
            eligible, reason, cust_res, dist_res, _, _ = _sync_eligibility(
                ln,
                body,
                keys_sim,
                open_channel_customer_id=open_channel_customer_id,
                unassigned_distributor_id=unassigned_distributor_id,
            )
            d["sync_eligible"] = eligible
            if eligible:
                d["sync_skip_reason"] = None
                warn_parts: list[str] = []
                if ln.customer_id is None and body.fallback_customer_id:
                    warn_parts.append("Customer unassigned on row — sync will use fallback customer.")
                if ln.distributor_id is None and body.fallback_distributor_id:
                    warn_parts.append("Distributor unassigned on row — sync will use fallback distributor.")
                if (
                    distributor_unassigned_soft(ln)
                    and unassigned_distributor_id
                    and dist_res == unassigned_distributor_id
                    and ln.distributor_id is None
                    and not body.fallback_distributor_id
                ):
                    warn_parts.append(
                        "Distributor intentionally unassigned — sync will use placeholder dim_distributor UNASSIGNED."
                    )
                if (
                    lineup_line_is_open_channel_staging(ln)
                    and open_channel_customer_id
                    and ln.customer_id is None
                    and not body.fallback_customer_id
                ):
                    d["sync_customer_resolution_note"] = (
                        "Sync will use Open Channel account (dim_customer code OPEN_CHANNEL)."
                    )
                else:
                    d["sync_customer_resolution_note"] = None
                if warn_parts:
                    d["sync_ui_severity"] = "warning"
                    d["sync_skip_detail"] = " ".join(warn_parts)
                else:
                    d["sync_ui_severity"] = None
                    d["sync_skip_detail"] = None
                if ln.product_id and cust_res and dist_res:
                    keys_sim.add((cust_res, dist_res, ln.product_id))
            else:
                d["sync_skip_reason"] = reason
                d["sync_skip_detail"] = sync_skip_detail_message(ln, reason)
                d["sync_ui_severity"] = sync_ui_severity_for_line(ln, reason)

    counts = _workbench_counts_payload(rows_payload, need_eligibility=need_eligibility)
    filtered = [
        d
        for ln, d in rows_payload
        if _workbench_scope_keep_line(d, workbench_scope, need_eligibility=need_eligibility)
    ]
    return {"lines": filtered, "workbench_counts": counts, "dap_semantics_note": _LINEUP_DAP_SEMANTICS_NOTE}


@router.patch("/lineup-cases/{case_id}/lines/{line_id}", status_code=200)
async def patch_lineup_case_line(
    case_id: int,
    line_id: int,
    body: CommercialLineupLinePatch,
    db: AsyncSession = Depends(get_db),
):
    """Edit draft current-lineup row fields (units, MSRP, promo evidence). Safe for pre-sync staging only."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status != "draft_imported":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Can only edit lineup lines on cases with status 'draft_imported'. "
                f"Current: '{case.commercial_status}'"
            ),
        )
    ln = await db.get(CommercialLineupLine, line_id)
    if ln is None or ln.case_id != case_id:
        raise HTTPException(status_code=404, detail="Lineup line not found")

    if body.quantity_units is not None:
        ln.quantity_units = body.quantity_units
    if body.msrp_local is not None:
        ln.msrp_local = body.msrp_local
    if body.promo_price_evidence_local is not None:
        ln.promo_price_evidence_local = body.promo_price_evidence_local

    await db.commit()
    await db.refresh(ln)

    stmt = (
        select(
            CommercialLineupLine,
            DimProduct.sku.label("product_sku"),
            DimProduct.name.label("product_name"),
            DimProduct.part_number.label("product_part_number"),
            DimProduct.model_name.label("product_model_name"),
            DimProduct.sales_model_name.label("product_sales_model_name"),
            DimCustomer.code.label("customer_code"),
            DimCustomer.name.label("customer_name"),
            DimDistributor.code.label("distributor_code"),
            DimDistributor.name.label("distributor_name"),
        )
        .outerjoin(DimProduct, DimProduct.id == CommercialLineupLine.product_id)
        .outerjoin(DimCustomer, DimCustomer.id == CommercialLineupLine.customer_id)
        .outerjoin(DimDistributor, DimDistributor.id == CommercialLineupLine.distributor_id)
        .where(CommercialLineupLine.id == line_id)
        .limit(1)
    )
    row = (await db.execute(stmt)).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Lineup line not found")
    (
        ln2,
        product_sku,
        product_name,
        product_part_number,
        product_model_name,
        product_sales_model_name,
        customer_code,
        customer_name,
        distributor_code,
        distributor_name,
    ) = row
    raw_payload = ln2.raw_row_payload if isinstance(ln2.raw_row_payload, dict) else {}
    distributor_token_raw = raw_payload.get("distributor_token")
    if distributor_token_raw is not None:
        distributor_token_raw = str(distributor_token_raw).strip() or None
    return {
        "id": ln2.id,
        "case_id": ln2.case_id,
        "source_row_number": ln2.source_row_number,
        "product_id": ln2.product_id,
        "product_sku": product_sku,
        "product_name": product_name,
        "product_part_number": product_part_number,
        "product_model_name": product_model_name,
        "product_sales_model_name": product_sales_model_name,
        "customer_id": ln2.customer_id,
        "customer_code": customer_code,
        "customer_name": customer_name,
        "distributor_id": ln2.distributor_id,
        "distributor_code": distributor_code,
        "distributor_name": distributor_name,
        "customer_token": ln2.customer_token,
        "distributor_token_raw": distributor_token_raw,
        "sku_raw": ln2.sku_raw,
        "part_number_raw": ln2.part_number_raw,
        "model_raw": ln2.model_raw,
        "quantity_units": float(ln2.quantity_units) if ln2.quantity_units is not None else None,
        "msrp_local": float(ln2.msrp_local) if ln2.msrp_local is not None else None,
        "promo_price_evidence_local": float(ln2.promo_price_evidence_local)
        if ln2.promo_price_evidence_local is not None
        else None,
        "dap_evidence_local": float(ln2.dap_evidence_local) if ln2.dap_evidence_local is not None else None,
        "rebate_pct_evidence": float(ln2.rebate_pct_evidence) if ln2.rebate_pct_evidence is not None else None,
        "distributor_margin_pct_evidence": float(ln2.distributor_margin_pct_evidence)
        if ln2.distributor_margin_pct_evidence is not None
        else None,
        "vat_pct_evidence": float(ln2.vat_pct_evidence) if ln2.vat_pct_evidence is not None else None,
        "diagnostic_codes": ln2.diagnostic_codes or [],
        "row_status": ln2.row_status,
        "mapping_confidence": float(ln2.mapping_confidence) if ln2.mapping_confidence is not None else None,
        "dap_semantics_note": _LINEUP_DAP_SEMANTICS_NOTE,
    }


@router.delete("/lineup-cases/{case_id}", status_code=204)
async def delete_lineup_case(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status != "draft_imported":
        raise HTTPException(
            status_code=409,
            detail=f"Can only delete lineup cases with status 'draft_imported'. Current status: '{case.commercial_status}'",
        )
    await db.delete(case)
    await db.commit()
    return Response(status_code=204)


@router.post("/lineup-cases/{case_id}/parse-upload", status_code=200)
async def parse_lineup_case_upload(
    case_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Parse an uploaded lineup file, write CommercialLineupLine rows, and link an ImportJob audit record.

    DAP fields are stored as evidence (dap_evidence_local) only.
    Never mapped to landed_cost_usd.
    """
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status not in ("draft_imported",):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Can only parse-upload to cases with status 'draft_imported'. "
                f"Current: '{case.commercial_status}'"
            ),
        )

    existing_count = (
        await db.execute(
            select(func.count(CommercialLineupLine.id)).where(CommercialLineupLine.case_id == case_id)
        )
    ).scalar_one()
    if existing_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                f"This case already has {existing_count} lines. "
                "Delete the case and create a new one to re-upload."
            ),
        )

    filename = file.filename or "upload"
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = await parse_current_lineup_file(db, case_id, filename, file_bytes)
    except CurrentLineupSourceNotConfiguredError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "current_lineup_import_not_seeded",
                "message": str(exc),
                "remediation": exc.remediation,
            },
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parse failed: {exc}") from exc

    return {
        "case_id": result.case_id,
        "import_job_id": result.import_job_id,
        "total_rows": result.total_rows,
        "resolved_products": result.resolved_products,
        "unresolved_products": result.unresolved_products,
        "line_count": result.line_count,
        "warnings": result.warnings,
    }


@router.get("/plans/{plan_id}/column-metadata")
async def get_plan_column_metadata(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Return per-field coverage counts for the plan's products.

    Catalogue fields: count non-null values across DimProduct for products in the plan.
    Spec keys: aggregate flattened specs_json key names (includes nested import staging) across plan products.
    """
    if not await db.get(CommercialPlan, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")

    plan_line_count = (
        await db.execute(
            select(func.count(CommercialPlanLine.id)).where(CommercialPlanLine.commercial_plan_id == plan_id)
        )
    ).scalar_one()

    total_stmt = select(func.count(distinct(CommercialPlanLine.product_id))).where(
        CommercialPlanLine.commercial_plan_id == plan_id
    )
    total_products = (await db.execute(total_stmt)).scalar_one()

    if total_products == 0:
        return {
            "plan_id": plan_id,
            "plan_line_count": int(plan_line_count),
            "total_products": 0,
            "catalogue": {},
            "spec_keys": {},
            "coverage_note": "No products in plan.",
        }

    product_ids_subq = (
        select(distinct(CommercialPlanLine.product_id))
        .where(CommercialPlanLine.commercial_plan_id == plan_id)
        .scalar_subquery()
    )

    cat_stmt = select(
        func.count(DimProduct.category).label("category"),
        func.count(DimProduct.form_factor).label("form_factor"),
        func.count(DimProduct.lifecycle_status).label("lifecycle_status"),
        func.count(DimProduct.product_line).label("product_line"),
        func.count(DimProduct.series_name).label("series_name"),
        func.count(DimProduct.business_unit).label("business_unit"),
        func.count(DimProduct.part_number).label("part_number"),
        func.count(DimProduct.sales_model_name).label("sales_model_name"),
        func.count(DimProduct.model_name).label("model_name"),
    ).where(DimProduct.id.in_(product_ids_subq))

    cat_row = (await db.execute(cat_stmt)).one()
    catalogue = {
        "category": int(cat_row.category),
        "form_factor": int(cat_row.form_factor),
        "lifecycle_status": int(cat_row.lifecycle_status),
        "product_line": int(cat_row.product_line),
        "series_name": int(cat_row.series_name),
        "business_unit": int(cat_row.business_unit),
        "part_number": int(cat_row.part_number),
        "sales_model_name": int(cat_row.sales_model_name),
        "model_name": int(cat_row.model_name),
    }

    spec_rows = (
        await db.execute(select(DimProduct.specs_json).where(DimProduct.id.in_(product_ids_subq)))
    ).scalars().all()
    spec_keys_counter: Counter[str] = Counter()
    for sj in spec_rows:
        flat = specs_json_flat_string_map(sj if isinstance(sj, dict) else None)
        for k in flat:
            spec_keys_counter[k] += 1
    spec_keys = dict(sorted(spec_keys_counter.items(), key=lambda kv: (-kv[1], kv[0])))

    return {
        "plan_id": plan_id,
        "plan_line_count": int(plan_line_count),
        "total_products": int(total_products),
        "catalogue": catalogue,
        "spec_keys": spec_keys,
        "coverage_note": "Counts are distinct products in the plan with non-null values.",
    }


# ─── Sync lineup case → plan lines ───────────────────────────────────────────


def _sync_eligibility(
    ln: CommercialLineupLine,
    body: SyncToPlanRequest,
    existing_keys: set[tuple],
    *,
    open_channel_customer_id: int | None = None,
    unassigned_distributor_id: int | None = None,
) -> tuple[bool, str, int | None, int | None, float | None, float | None]:
    """Return (eligible, skip_reason, customer_id, distributor_id, srp, units).

    skip_reason is one of: '' (eligible), 'unresolved_product', 'missing_customer',
    'open_channel_account_missing' (Open Channel staging but OPEN_CHANNEL dim row missing),
    'missing_distributor', 'missing_srp', 'missing_quantity', 'duplicate'.
    """
    if not ln.product_id:
        return False, "unresolved_product", None, None, None, None

    if managed_customer_token_unresolved(ln):
        return False, "missing_customer", None, None, None, None

    customer_id = ln.customer_id or body.fallback_customer_id
    if not customer_id and lineup_line_is_open_channel_staging(ln):
        if open_channel_customer_id:
            customer_id = open_channel_customer_id
        else:
            return False, "open_channel_account_missing", None, None, None, None
    if not customer_id:
        return False, "missing_customer", None, None, None, None

    distributor_id = ln.distributor_id or body.fallback_distributor_id
    if not distributor_id and distributor_unassigned_soft(ln) and unassigned_distributor_id:
        distributor_id = unassigned_distributor_id
    if not distributor_id:
        return False, "missing_distributor", None, None, None, None

    srp = ln.msrp_local or body.default_srp_local
    if not srp:
        return False, "missing_srp", None, None, None, None

    units = ln.quantity_units
    if units is None:
        if body.allow_zero_quantity:
            units = 0.0
        else:
            return False, "missing_quantity", None, None, None, None

    key = (customer_id, distributor_id, ln.product_id)
    if key in existing_keys:
        return False, "duplicate", None, None, None, None

    return True, "", customer_id, distributor_id, srp, units


@router.get("/lineup-cases/{case_id}/sync-to-plan/preview")
async def preview_sync_lineup_case_to_plan(
    case_id: int,
    commercial_plan_id: int | None = None,
    fallback_customer_id: int | None = None,
    fallback_distributor_id: int | None = None,
    default_srp_local: float | None = None,
    allow_zero_quantity: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Preview what sync-to-plan would create/skip without committing any rows."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(404, "Lineup case not found")
    if case.commercial_status != "accepted":
        raise HTTPException(409, f"Sync requires case status 'accepted'. Current: '{case.commercial_status}'")

    plan_id = commercial_plan_id or case.commercial_plan_id
    if not plan_id:
        raise HTTPException(400, "commercial_plan_id required (set on case or in request body)")

    if not await db.get(CommercialPlan, plan_id):
        raise HTTPException(404, f"CommercialPlan id={plan_id} not found")

    body = SyncToPlanRequest(
        commercial_plan_id=commercial_plan_id,
        fallback_customer_id=fallback_customer_id,
        fallback_distributor_id=fallback_distributor_id,
        default_srp_local=default_srp_local,
        allow_zero_quantity=allow_zero_quantity,
    )

    lines_result = await db.execute(
        select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id)
    )
    lines = lines_result.scalars().all()

    existing_stmt = select(
        CommercialPlanLine.customer_id,
        CommercialPlanLine.distributor_id,
        CommercialPlanLine.product_id,
    ).where(CommercialPlanLine.commercial_plan_id == plan_id)
    existing_rows = (await db.execute(existing_stmt)).all()
    existing_keys: set[tuple] = {
        (r.customer_id, r.distributor_id, r.product_id) for r in existing_rows
    }

    will_create = 0
    skipped_duplicates = 0
    skipped_unresolved_product = 0
    skipped_missing_customer = 0
    skipped_missing_distributor = 0
    skipped_missing_quantity = 0
    skipped_missing_srp = 0
    skipped_open_channel_account_missing = 0

    open_channel_customer_id = await get_open_channel_customer_id(db)
    unassigned_distributor_id = await get_unassigned_distributor_id(db)

    for ln in lines:
        eligible, reason, cust_res, dist_res, _, _ = _sync_eligibility(
            ln,
            body,
            existing_keys,
            open_channel_customer_id=open_channel_customer_id,
            unassigned_distributor_id=unassigned_distributor_id,
        )
        if eligible:
            will_create += 1
            if cust_res is not None and dist_res is not None and ln.product_id:
                existing_keys.add((cust_res, dist_res, ln.product_id))
        elif reason == "duplicate":
            skipped_duplicates += 1
        elif reason == "missing_srp":
            skipped_missing_srp += 1
        elif reason == "unresolved_product":
            skipped_unresolved_product += 1
        elif reason == "missing_customer":
            skipped_missing_customer += 1
        elif reason == "open_channel_account_missing":
            skipped_open_channel_account_missing += 1
        elif reason == "missing_distributor":
            skipped_missing_distributor += 1
        elif reason == "missing_quantity":
            skipped_missing_quantity += 1
        else:
            skipped_unresolved_product += 1

    skipped_unresolved = (
        skipped_unresolved_product
        + skipped_missing_customer
        + skipped_missing_distributor
        + skipped_missing_quantity
        + skipped_open_channel_account_missing
    )

    return {
        "case_id": case_id,
        "plan_id": plan_id,
        "total_lines": len(lines),
        "will_create": will_create,
        "skipped_duplicates": skipped_duplicates,
        "skipped_unresolved": skipped_unresolved,
        "skipped_unresolved_product": skipped_unresolved_product,
        "skipped_missing_customer": skipped_missing_customer,
        "skipped_open_channel_account_missing": skipped_open_channel_account_missing,
        "skipped_missing_distributor": skipped_missing_distributor,
        "skipped_missing_quantity": skipped_missing_quantity,
        "skipped_missing_srp": skipped_missing_srp,
        "created": 0,
        "created_line_ids": [],
        "warnings": [],
    }


@router.post("/lineup-cases/{case_id}/sync-to-plan", status_code=200)
async def sync_lineup_case_to_plan(
    case_id: int,
    body: SyncToPlanRequest,
    db: AsyncSession = Depends(get_db),
):
    """Sync accepted lineup case lines to CommercialPlanLine rows.

    Only creates lines for resolved rows (product_id, customer_id/fallback, distributor_id/fallback set).
    Skips duplicates by plan_id + customer_id + distributor_id + product_id.
    Never writes dap_evidence_local to any cost field.
    Requires commercial_status = accepted.
    Writes a small sync linkage block into each synced row's ``raw_row_payload`` for audit and workbench filtering.
    Does not mutate historical lineup rows.
    """
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(404, "Lineup case not found")
    if case.commercial_status != "accepted":
        raise HTTPException(409, f"Sync requires case status 'accepted'. Current: '{case.commercial_status}'")

    plan_id = body.commercial_plan_id or case.commercial_plan_id
    if not plan_id:
        raise HTTPException(400, "commercial_plan_id required (set on case or in request body)")

    plan = await db.get(CommercialPlan, plan_id)
    if not plan:
        raise HTTPException(404, f"CommercialPlan id={plan_id} not found")

    lines_result = await db.execute(
        select(CommercialLineupLine).where(CommercialLineupLine.case_id == case_id)
    )
    lines = lines_result.scalars().all()

    existing_stmt = select(
        CommercialPlanLine.customer_id,
        CommercialPlanLine.distributor_id,
        CommercialPlanLine.product_id,
    ).where(CommercialPlanLine.commercial_plan_id == plan_id)
    existing_rows = (await db.execute(existing_stmt)).all()
    existing_keys: set[tuple] = {
        (r.customer_id, r.distributor_id, r.product_id) for r in existing_rows
    }

    created_ids: list[int] = []
    skipped_duplicates = 0
    skipped_unresolved_product = 0
    skipped_missing_customer = 0
    skipped_missing_distributor = 0
    skipped_missing_quantity = 0
    skipped_missing_srp = 0
    skipped_open_channel_account_missing = 0
    failed = 0
    warnings: list[str] = []

    open_channel_customer_id = await get_open_channel_customer_id(db)
    unassigned_distributor_id = await get_unassigned_distributor_id(db)

    for ln in lines:
        eligible, reason, customer_id, distributor_id, srp, units = _sync_eligibility(
            ln,
            body,
            existing_keys,
            open_channel_customer_id=open_channel_customer_id,
            unassigned_distributor_id=unassigned_distributor_id,
        )
        if not eligible:
            if reason == "duplicate":
                skipped_duplicates += 1
            elif reason == "missing_srp":
                skipped_missing_srp += 1
            elif reason == "unresolved_product":
                skipped_unresolved_product += 1
            elif reason == "missing_customer":
                skipped_missing_customer += 1
            elif reason == "open_channel_account_missing":
                skipped_open_channel_account_missing += 1
            elif reason == "missing_distributor":
                skipped_missing_distributor += 1
            elif reason == "missing_quantity":
                skipped_missing_quantity += 1
            else:
                skipped_unresolved_product += 1
            continue

        if ln.quantity_units is None and body.allow_zero_quantity:
            warnings.append(f"Row {ln.source_row_number}: quantity_units missing; using 0.")

        # Create plan line — NEVER write DAP as cost
        new_line = CommercialPlanLine(
            commercial_plan_id=plan_id,
            customer_id=customer_id,
            distributor_id=distributor_id,
            product_id=ln.product_id,
            target_units=units,
            target_srp_local=srp,
            promo_srp_local=ln.promo_price_evidence_local,  # evidence only; promo is suggested
        )
        db.add(new_line)
        try:
            await db.flush()
            created_ids.append(new_line.id)
            existing_keys.add((customer_id, distributor_id, ln.product_id))
            attach_plan_line_sync_to_lineup_row(
                ln,
                commercial_plan_id=plan_id,
                commercial_plan_line_id=new_line.id,
            )
        except Exception as exc:
            await db.rollback()
            failed += 1
            warnings.append(f"Row {ln.source_row_number}: failed to create plan line: {exc}")

    await db.commit()

    skipped_unresolved = (
        skipped_unresolved_product
        + skipped_missing_customer
        + skipped_missing_distributor
        + skipped_missing_quantity
        + skipped_open_channel_account_missing
    )

    return {
        "case_id": case_id,
        "plan_id": plan_id,
        "created": len(created_ids),
        "skipped_duplicates": skipped_duplicates,
        "skipped_unresolved": skipped_unresolved,
        "skipped_unresolved_product": skipped_unresolved_product,
        "skipped_missing_customer": skipped_missing_customer,
        "skipped_open_channel_account_missing": skipped_open_channel_account_missing,
        "skipped_missing_distributor": skipped_missing_distributor,
        "skipped_missing_quantity": skipped_missing_quantity,
        "skipped_missing_srp": skipped_missing_srp,
        "failed": failed,
        "created_line_ids": created_ids,
        "warnings": warnings,
    }
