from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timezone

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile

from app.core.feature_flags import commercial_planner_enabled
from pydantic import BaseModel, Field, field_validator, model_validator
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
from app.services.commercial_planner.economics_trust import (
    classify_line_economics_trust,
    plan_trust_from_line_tiers,
    summarize_recalculate_trust,
)
from app.services.commercial_planner.current_lineup_seed import CurrentLineupSourceNotConfiguredError
from app.services.commercial_planner.lineup_entity_resolution import (
    RESOLUTION_ALLOWED_CASE_STATUSES,
    apply_entity_resolutions,
    collect_entity_resolution_candidates,
)
from app.services.commercial_planner.intelligence.product_rankings import rank_products_for_customer
from app.services.commercial_planner.lineup_case_po_confirm import (
    CaseNotFoundError,
    CaseStatusNotConfirmableError,
    UnresolvedCaseDistributorError,
    confirm_case_with_po,
    list_case_pos,
    list_case_pos_bulk,
)
from app.services.commercial_planner.lineup_case_suggested_pos import (
    suggest_distributors_for_case,
    suggest_pos_for_case,
)
from app.services.commercial_planner.lineup_case_distributor_assign import (
    CaseNotFoundError as AssignCaseNotFoundError,
    CaseStatusNotResolvableError as AssignCaseStatusNotResolvableError,
    DistributorCodeExistsError,
    DistributorNotFoundError,
    assign_case_distributor,
)
from app.services.commercial_planner.lineup_po_reconciliation import (
    CaseNotFoundError as ReconCaseNotFoundError,
    reconcile_case,
)
from app.services.commercial_planner.lineup_po_gap import (
    PurchaseOrderNotFoundError,
    dismiss_gap_po,
    po_gap_worklist,
    restore_gap_po,
)
from app.services.commercial_planner.lineup_po_auto_link import po_auto_link_proposals
from app.services.commercial_planner.lineup_po_auto_link_actions import (
    ProposalNotFoundError,
    apply_auto_link_proposals,
    dismiss_auto_link_proposal,
    restore_auto_link_proposal,
)
from app.services.commercial_planner.lineup_case_parser import (
    parse_current_lineup_file,
    preview_current_lineup_file,
)
from app.services.commercial_planner.lineup_case_product_line import ensure_case_product_line_from_catalogue
from app.services.commercial_planner.lineup_header_mapping import lineup_evidence_from_uploaded
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
from app.services.commercial_planner.sku_economics_import import (
    apply_sku_economics_import,
    build_template_csv,
    preview_sku_economics_import,
)
from app.services.commercial_planner.suggestions import (
    SuggestionInputs,
    build_promo_mix_suggestion,
    build_pricing_suggestion,
    build_quantity_suggestion,
)

from app.api.v1.endpoints.commercial_planner_auth import require_commercial_planner_enabled


async def _require_commercial_planner_enabled() -> None:
    await require_commercial_planner_enabled()


router = APIRouter(dependencies=[Depends(_require_commercial_planner_enabled)])

ALLOWED_PLAN_STATUSES = {"draft", "review", "approved", "published"}


def _coerce_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _sku_assumption_invalid_controlled_cost(sku: CommercialSkuAssumption | None) -> bool:
    if sku is None:
        return False
    v = _coerce_float(sku.controlled_cost_amount)
    return v is None or v <= 0


def _sku_assumption_invalid_fx(sku: CommercialSkuAssumption | None) -> bool:
    if sku is None:
        return False
    v = _coerce_float(sku.fx_plan_currency_per_cost_currency)
    return v is None or v <= 0


def _sku_assumption_invalid_vat(sku: CommercialSkuAssumption | None) -> bool:
    """VAT stored as decimal fraction (e.g. 0.15); values outside [0, 1] are treated as invalid for readiness."""
    if sku is None:
        return False
    v = _coerce_float(sku.vat_rate_pct)
    if v is None:
        return True
    return v < 0 or v > 1.0


def _sku_assumption_invalid_reserve(sku: CommercialSkuAssumption | None) -> bool:
    if sku is None:
        return False
    rt = _coerce_float(sku.reserve_total_pct)
    ps = _coerce_float(sku.promo_reserve_split_pct)
    if rt is None or ps is None:
        return True
    if rt < 0 or rt > 1.0 or ps < 0 or ps > 1.0:
        return True
    return False


from app.services.commercial_planner.plan_readiness import (
    compute_plan_readiness_payload as _compute_plan_readiness_payload,
)


async def compute_plan_readiness_payload(db: AsyncSession, plan_id: int) -> dict:
    out = await _compute_plan_readiness_payload(db, plan_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Plan not found")
    return out


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
    country_code: str | None = Field(default=None, max_length=8)
    currency_code: str | None = Field(default=None, max_length=8)
    period_start: date | None = None
    period_end: date | None = None

    @field_validator("currency_code", mode="before")
    @classmethod
    def normalize_currency_code(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().upper()
            return s if s else None
        return v

    @field_validator("country_code", mode="before")
    @classmethod
    def normalize_country_code(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            s = v.strip().upper()
            return s if s else None
        return v


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
    override_controlled_cost_amount: float | None = None
    override_controlled_cost_currency_code: str | None = None
    override_vat_rate_pct: float | None = None
    override_fx_plan_currency_per_cost_currency: float | None = None
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
        "calc_oem_sell_in_amount": float(line.calc_oem_sell_in_amount) if line.calc_oem_sell_in_amount is not None else None,
        "calc_distributor_net_amount": float(line.calc_distributor_net_amount) if line.calc_distributor_net_amount is not None else None,
        "calc_campaign_support_reserve_amount": float(line.calc_campaign_support_reserve_amount) if line.calc_campaign_support_reserve_amount is not None else None,
        "calc_non_campaign_reserve_amount": float(line.calc_non_campaign_reserve_amount) if line.calc_non_campaign_reserve_amount is not None else None,
        "calc_internal_gp_amount": float(line.calc_internal_gp_amount) if line.calc_internal_gp_amount is not None else None,
        "calc_customer_margin_input_pct": float(line.calc_customer_margin_input_pct) if line.calc_customer_margin_input_pct is not None else None,
        "calc_distributor_margin_input_pct": float(line.calc_distributor_margin_input_pct) if line.calc_distributor_margin_input_pct is not None else None,
        "calc_flags": line.calc_flags or [],
        "calc_explanation": line.calc_explanation,
        "override_customer_margin_pct": float(line.override_customer_margin_pct) if line.override_customer_margin_pct is not None else None,
        "override_customer_rebate_pct": float(line.override_customer_rebate_pct) if line.override_customer_rebate_pct is not None else None,
        "override_distributor_margin_pct": float(line.override_distributor_margin_pct) if line.override_distributor_margin_pct is not None else None,
        "override_controlled_cost_amount": float(line.override_controlled_cost_amount) if line.override_controlled_cost_amount is not None else None,
        "override_vat_rate_pct": float(line.override_vat_rate_pct) if line.override_vat_rate_pct is not None else None,
        "override_fx_plan_currency_per_cost_currency": float(line.override_fx_plan_currency_per_cost_currency) if line.override_fx_plan_currency_per_cost_currency is not None else None,
        "override_reserve_total_pct": float(line.override_reserve_total_pct) if line.override_reserve_total_pct is not None else None,
        "override_promo_reserve_split_pct": float(line.override_promo_reserve_split_pct)
        if line.override_promo_reserve_split_pct is not None
        else None,
        "economics_calc_currency_code": (line.economics_calc_currency_code or "USD").strip(),
        "override_controlled_cost_currency_code": (line.override_controlled_cost_currency_code or "").strip() or None,
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
                CommercialSkuAssumption.fx_plan_currency_per_cost_currency,
                CommercialSkuAssumption.reserve_total_pct,
                CommercialSkuAssumption.promo_reserve_split_pct,
                CommercialSkuAssumption.controlled_cost_amount,
                CommercialSkuAssumption.controlled_cost_currency_code,
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
        sa_cc,
        sa_ccy,
    ) = r
    read_ext = plan_line_read_model_extensions(
        line,
        specs_json if isinstance(specs_json, dict) else None,
        customer_margin_pct=float(ct_margin) if ct_margin is not None else None,
        customer_rebate_pct=float(ct_rebate) if ct_rebate is not None else None,
        distributor_margin_pct=float(dt_margin) if dt_margin is not None else None,
        sku_vat_rate_pct=float(sa_vat) if sa_vat is not None else None,
        sku_fx_plan_currency_per_cost_currency=float(sa_fx) if sa_fx is not None else None,
        sku_reserve_total_pct=float(sa_reserve) if sa_reserve is not None else None,
        sku_promo_reserve_split_pct=float(sa_pr) if sa_pr is not None else None,
        sku_controlled_cost_amount=float(sa_cc) if sa_cc is not None else None,
        sku_controlled_cost_currency_code=str(sa_ccy).strip() if sa_ccy is not None else None,
        join_customer_term_present=ct_margin is not None,
        join_distributor_term_present=dt_margin is not None,
        join_sku_assumption_present=sa_cc is not None,
        distributor_code=dc,
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


async def _resolve_terms_and_calc(
    db: AsyncSession,
    line: CommercialPlanLine,
    *,
    unassigned_distributor_id: int | None = None,
) -> tuple[dict, list[str]]:
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
    if unassigned_distributor_id is not None and line.distributor_id == unassigned_distributor_id:
        missing.append("unassigned_distributor_placeholder")
    if sku is None and line.override_fx_plan_currency_per_cost_currency is None:
        missing.append("economics_placeholder_fx_without_sku")
    if sku is None and line.override_vat_rate_pct is None:
        missing.append("economics_placeholder_vat_without_sku")
    if sku is None and (
        line.override_reserve_total_pct is None or line.override_promo_reserve_split_pct is None
    ):
        missing.append("economics_placeholder_reserves_without_sku")

    inp = CommercialCalcInputs(
        target_units=float(line.target_units),
        target_srp_local=float(line.target_srp_local),
        promo_srp_local=float(line.promo_srp_local) if line.promo_srp_local is not None else None,
        promo_mix_pct=float(line.promo_mix_pct),
        fx_plan_currency_per_cost_currency=float(
            line.override_fx_plan_currency_per_cost_currency
            or (sku.fx_plan_currency_per_cost_currency if sku else 1.0)
        ),
        vat_rate_pct=float(line.override_vat_rate_pct or (sku.vat_rate_pct if sku else 0.15)),
        controlled_cost_amount=float(line.override_controlled_cost_amount or (sku.controlled_cost_amount if sku else 0.0)),
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
    if line.override_controlled_cost_amount is not None:
        econ_ccy = (line.override_controlled_cost_currency_code or "").strip() or "USD"
    else:
        econ_ccy = ((sku.controlled_cost_currency_code if sku else None) or "").strip() or "USD"
    payload = {
        "calc_oem_sell_in_amount": calc.calc_oem_sell_in_amount,
        "calc_distributor_net_amount": calc.calc_distributor_net_amount,
        "calc_campaign_support_reserve_amount": calc.calc_campaign_support_reserve_amount,
        "calc_non_campaign_reserve_amount": calc.calc_non_campaign_reserve_amount,
        "calc_internal_gp_amount": calc.calc_internal_gp_amount,
        "calc_customer_margin_input_pct": calc.calc_customer_margin_input_pct,
        "calc_distributor_margin_input_pct": calc.calc_distributor_margin_input_pct,
        "economics_calc_currency_code": econ_ccy,
        "calc_flags": list(dict.fromkeys([*missing, *calc.flags])),
        "calc_explanation": calc.explanation,
    }
    return payload, payload["calc_flags"]


def _commercial_plan_api_item(p: CommercialPlan, line_count: int) -> dict:
    return {
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


@router.get("/plans")
async def list_plans(db: AsyncSession = Depends(get_db)):
    plans = (await db.execute(select(CommercialPlan).order_by(CommercialPlan.id.desc()))).scalars().all()
    out = []
    for p in plans:
        line_count = (
            await db.execute(select(func.count(CommercialPlanLine.id)).where(CommercialPlanLine.commercial_plan_id == p.id))
        ).scalar_one()
        out.append(_commercial_plan_api_item(p, int(line_count)))
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
    if "currency_code" in data and data["currency_code"] is not None:
        ccy = data["currency_code"]
        if not re.fullmatch(r"[A-Z]{3,8}", ccy):
            raise HTTPException(
                status_code=400,
                detail="currency_code must be a 3–8 letter ISO-style code (A–Z only)",
            )
    for k, v in data.items():
        setattr(plan, k, v)
    await db.commit()
    await db.refresh(plan)
    line_count = (
        await db.execute(select(func.count(CommercialPlanLine.id)).where(CommercialPlanLine.commercial_plan_id == plan.id))
    ).scalar_one()
    return _commercial_plan_api_item(plan, int(line_count))


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
                CommercialSkuAssumption.fx_plan_currency_per_cost_currency.label("row_sa_fx"),
                CommercialSkuAssumption.reserve_total_pct.label("row_sa_reserve"),
                CommercialSkuAssumption.promo_reserve_split_pct.label("row_sa_pr"),
                CommercialSkuAssumption.controlled_cost_amount.label("row_sa_cc"),
                CommercialSkuAssumption.controlled_cost_currency_code.label("row_sa_ccy"),
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
        sa_cc,
        sa_ccy,
    ) in rows:
        read_ext = plan_line_read_model_extensions(
            line,
            specs_json if isinstance(specs_json, dict) else None,
            customer_margin_pct=float(ct_margin) if ct_margin is not None else None,
            customer_rebate_pct=float(ct_rebate) if ct_rebate is not None else None,
            distributor_margin_pct=float(dt_margin) if dt_margin is not None else None,
            sku_vat_rate_pct=float(sa_vat) if sa_vat is not None else None,
            sku_fx_plan_currency_per_cost_currency=float(sa_fx) if sa_fx is not None else None,
            sku_reserve_total_pct=float(sa_reserve) if sa_reserve is not None else None,
            sku_promo_reserve_split_pct=float(sa_pr) if sa_pr is not None else None,
            sku_controlled_cost_amount=float(sa_cc) if sa_cc is not None else None,
            sku_controlled_cost_currency_code=str(sa_ccy).strip() if sa_ccy is not None else None,
            join_customer_term_present=ct_margin is not None,
            join_distributor_term_present=dt_margin is not None,
            join_sku_assumption_present=sa_cc is not None,
            distributor_code=dc,
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
    rd = await compute_plan_readiness_payload(db, plan_id)
    if not rows:
        return {
            "updated": 0,
            "plan_id": plan_id,
            "flags": [],
            "readiness": rd,
            "economics_trust": "ok",
            "economics_trust_note": None,
            "economics_plan_trust": "ok",
            "recalculate_trust_summary": {
                "lines_trusted_ok": 0,
                "lines_warning": 0,
                "lines_blocked": 0,
                "top_blocker_flags": [],
            },
        }
    all_flags: list[str] = []
    unassigned_id = await get_unassigned_distributor_id(db)
    line_trust_rows: list[tuple[int, list[str], str]] = []
    for row in rows:
        payload, flags = await _resolve_terms_and_calc(db, row, unassigned_distributor_id=unassigned_id)
        for k, v in payload.items():
            setattr(row, k, v)
        all_flags.extend(flags)
        tier, _reasons = classify_line_economics_trust(flags)
        line_trust_rows.append((row.id, flags, tier))
    await db.commit()
    rd2 = await compute_plan_readiness_payload(db, plan_id)
    plan_tier = plan_trust_from_line_tiers([t for _, _, t in line_trust_rows])
    summary = summarize_recalculate_trust(line_trust_rows)
    trust = "ok"
    note: str | None = None
    base_summary = (
        f"Recalculated {len(rows)} line(s): {summary['lines_trusted_ok']} ok, "
        f"{summary['lines_warning']} warning, {summary['lines_blocked']} blocked."
    )
    if plan_tier == "blocked":
        trust = "low"
        note = (
            f"{base_summary} Blocked lines are not decision-grade. "
            f"Top flags: {', '.join(summary['top_blocker_flags']) or 'see Issues column on lines'}."
        )
    elif plan_tier == "warning":
        trust = "attention"
        note = f"{base_summary} Review warnings and placeholders before trusting totals."
    else:
        note = base_summary

    if rd2["line_count"] > 0:
        if (
            not rd2["ready"]
            or rd2.get("invalid_controlled_cost", 0)
            or rd2.get("invalid_fx", 0)
            or rd2.get("invalid_vat", 0)
            or rd2.get("invalid_reserve", 0)
        ):
            trust = "low"
            extra = (
                "Plan readiness: missing defaults or invalid SKU economics remain — "
                "outputs may be unreliable until fixed."
            )
            note = f"{note} {extra}" if note else extra
        if rd2.get("using_unassigned_distributor", 0) > 0:
            extra = (
                f"{rd2['using_unassigned_distributor']} line(s) use the UNASSIGNED distributor placeholder; "
                "resolve distributor for trusted channel economics."
            )
            if trust == "ok":
                trust = "attention"
                note = f"{note} {extra}" if note else extra
            else:
                note = f"{note} {extra}" if note else extra
    return {
        "updated": len(rows),
        "plan_id": plan_id,
        "flags": sorted(set(all_flags)),
        "readiness": rd2,
        "economics_trust": trust,
        "economics_trust_note": note,
        "economics_plan_trust": plan_tier,
        "recalculate_trust_summary": summary,
    }


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
        total_gp += float(row.calc_internal_gp_amount or 0.0)
        total_promo_reserve += float(row.calc_campaign_support_reserve_amount or 0.0)
        total_nonpromo_reserve += float(row.calc_non_campaign_reserve_amount or 0.0)
        for f in row.calc_flags or []:
            flags.add(str(f))
    return {
        "plan_id": plan_id,
        "line_count": len(rows),
        "total_units": round(total_units, 4),
        "total_internal_gp_amount": round(total_gp, 4),
        "total_campaign_support_reserve_amount": round(total_promo_reserve, 4),
        "total_non_campaign_reserve_amount": round(total_nonpromo_reserve, 4),
        "economics_calc_currency_code": rows[0].economics_calc_currency_code if rows else "USD",
        "flags": sorted(flags),
    }


@router.get("/plans/{plan_id}/suggestions")
async def get_plan_suggestions(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Return suggestions for every line in a plan.

    Queries are batched: 5 SQL round-trips total regardless of line count.
    Prior-planned uses data from *other* plans only (same product+customer pair).
    Lineup evidence is sourced from the latest historical_lineup apply job — DAP is
    never used as SKU controlled cost (PM bottom).
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
    current_lineup_map: dict[int, dict] = {}
    cl_rows = (
        await db.execute(
            select(
                CommercialLineupLine.product_id,
                func.max(CommercialLineupLine.msrp_local).label("msrp_local"),
                func.max(CommercialLineupLine.promo_price_evidence_local).label("promo_price_local"),
                func.sum(CommercialLineupLine.quantity_units).label("total_quantity_units"),
            )
            .join(CommercialLineupCase, CommercialLineupCase.id == CommercialLineupLine.case_id)
            .where(
                CommercialLineupCase.commercial_plan_id == plan_id,
                CommercialLineupLine.product_id.in_(product_ids),
            )
            .group_by(CommercialLineupLine.product_id)
        )
    ).all()
    for clr in cl_rows:
        if clr.product_id is None:
            continue
        current_lineup_map[int(clr.product_id)] = {
            "msrp_local": float(clr.msrp_local) if clr.msrp_local is not None else None,
            "promo_price_local": float(clr.promo_price_local) if clr.promo_price_local is not None else None,
            "total_quantity_units": float(clr.total_quantity_units) if clr.total_quantity_units is not None else None,
            "source": "current_lineup_case",
        }

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
        cle = current_lineup_map.get(row.product_id, {})
        lineup_msrp = cle.get("msrp_local") if cle else le.get("msrp_local")
        lineup_promo = cle.get("promo_price_local") if cle else le.get("promo_price_local")
        lineup_qty = cle.get("total_quantity_units") if cle else le.get("total_quantity_units")
        lineup_job = None if cle else le.get("job_id")
        lineup_period = le.get("period_label") if le else None
        inp = SuggestionInputs(
            avg_sellout_units=avg_sellout_map.get(key, 0.0),
            prior_planned_units=prior_planned_map.get(key),
            forecast_units=forecast_map.get(row.product_id),
            latest_net_price=pricing_map.get(row.product_id),
            target_srp_local=float(row.target_srp_local),
            promo_mix_pct=float(row.promo_mix_pct),
            lineup_msrp_local=lineup_msrp,
            lineup_promo_price_local=lineup_promo,
            lineup_quantity_units=lineup_qty,
            lineup_period_label=lineup_period,
            lineup_job_id=lineup_job,
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
                        "current_lineup_case": bool(cle),
                    },
                },
            }
        )
    return out


@router.get("/plans/{plan_id}/readiness")
async def get_plan_readiness(plan_id: int, db: AsyncSession = Depends(get_db)):
    """Return a data-readiness gate summary for a plan (read-only)."""
    return await compute_plan_readiness_payload(db, plan_id)


@router.get("/plans/{plan_id}/intelligence/customer/{customer_id}/product-rankings")
async def get_customer_product_rankings(
    plan_id: int,
    customer_id: int,
    distributor_id: int = Query(..., description="Distributor context for economics scoring"),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Rank products for a customer on this plan (deterministic opportunity score)."""
    if not await db.get(CommercialPlan, plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    if not await db.get(DimCustomer, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    if not await db.get(DimDistributor, distributor_id):
        raise HTTPException(status_code=404, detail="Distributor not found")
    items = await rank_products_for_customer(
        db,
        plan_id=plan_id,
        customer_id=customer_id,
        distributor_id=distributor_id,
        limit=limit,
    )
    return {
        "plan_id": plan_id,
        "customer_id": customer_id,
        "distributor_id": distributor_id,
        "items": items,
    }


@router.get("/lineup-evidence")
async def get_lineup_evidence(
    product_id: int = Query(..., description="DimProduct.id to fetch lineup evidence for"),
    db: AsyncSession = Depends(get_db),
):
    """Return aggregated lineup evidence for a single product from the latest apply job (read-only).

    DAP (Distributor Acquisition Price) is the source/import value from the historical lineup.
    It is NOT equivalent to SKU controlled cost (PM bottom) and must never be mapped directly as a cost input.
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
                func.max(HistoricalLineupImportLine.disti_cost_local).label("disti_cost_local"),
                func.max(HistoricalLineupImportLine.disti_margin_pct).label("disti_margin_pct"),
                func.max(HistoricalLineupImportLine.vat_pct).label("vat_pct"),
                func.max(HistoricalLineupImportLine.rebate_pct).label("rebate_pct"),
                func.sum(HistoricalLineupImportLine.quantity_units).label("total_quantity_units"),
                func.count(HistoricalLineupImportLine.id).label("line_count"),
                func.max(HistoricalLineupImportHeader.period_label).label("period_label"),
                func.max(HistoricalLineupImportHeader.currency_code).label("evidence_currency_code"),
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
            "disti_cost_local": float(r.disti_cost_local) if r.disti_cost_local is not None else None,
            "disti_margin_pct": float(r.disti_margin_pct) if r.disti_margin_pct is not None else None,
            "vat_pct": float(r.vat_pct) if r.vat_pct is not None else None,
            "rebate_pct": float(r.rebate_pct) if r.rebate_pct is not None else None,
            "total_quantity_units": float(r.total_quantity_units) if r.total_quantity_units is not None else None,
            "line_count": int(r.line_count),
            "period_label": r.period_label,
            "evidence_currency_code": (str(r.evidence_currency_code).strip() if r.evidence_currency_code else None)
            or None,
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
    controlled_cost_amount: float = Field(gt=0)
    controlled_cost_currency_code: str = Field(default="USD", min_length=3, max_length=8)
    vat_rate_pct: float = Field(ge=0.0, le=1.0)
    fx_plan_currency_per_cost_currency: float = Field(gt=0)
    reserve_total_pct: float = Field(ge=0.0, le=1.0)
    promo_reserve_split_pct: float = Field(ge=0.0, le=1.0)


class SkuAssumptionPatch(BaseModel):
    controlled_cost_amount: float | None = Field(default=None, gt=0)
    controlled_cost_currency_code: str | None = Field(default=None, min_length=3, max_length=8)
    vat_rate_pct: float | None = Field(default=None, ge=0.0, le=1.0)
    fx_plan_currency_per_cost_currency: float | None = Field(default=None, gt=0)
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
        "controlled_cost_amount": float(row.controlled_cost_amount),
        "controlled_cost_currency_code": str(row.controlled_cost_currency_code or "USD").strip(),
        "vat_rate_pct": float(row.vat_rate_pct),
        "fx_plan_currency_per_cost_currency": float(row.fx_plan_currency_per_cost_currency),
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


@router.get("/sku-assumptions/import-template")
async def sku_economics_import_template():
    return Response(
        content=build_template_csv().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="sku_economics_template.csv"'},
    )


@router.post("/sku-assumptions/import-preview")
async def sku_economics_import_preview(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Empty file")
    return await preview_sku_economics_import(db, content)


@router.post("/sku-assumptions/import-apply")
async def sku_economics_import_apply(
    confirm: bool = Form(False),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm must be true to apply import changes")
    content = await file.read()
    if not content or not content.strip():
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        return await apply_sku_economics_import(db, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Apply conflicted with existing rows (e.g. duplicate product); refresh and retry.",
        ) from None


@router.get("/sku-assumptions")
async def list_sku_assumptions(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(default=None),
    product_id: int | None = Query(default=None, description="Exact DimProduct.id filter (non-breaking; optional)"),
):
    stmt = (
        select(CommercialSkuAssumption, DimProduct.sku, DimProduct.name)
        .join(DimProduct, DimProduct.id == CommercialSkuAssumption.product_id)
        .order_by(DimProduct.sku)
    )
    if product_id is not None:
        stmt = stmt.where(CommercialSkuAssumption.product_id == product_id)
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
        controlled_cost_amount=body.controlled_cost_amount,
        controlled_cost_currency_code=(body.controlled_cost_currency_code or "USD").strip(),
        vat_rate_pct=body.vat_rate_pct,
        fx_plan_currency_per_cost_currency=body.fx_plan_currency_per_cost_currency,
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

# Included verbatim in lineup-product-gaps responses.  DAP is NOT equivalent to SKU controlled cost.
# Never map dap_local directly to controlled_cost_amount without explicit cost-basis verification.
_COST_SEMANTICS_NOTE = (
    "DAP and similar columns (including Rand landed / local DAP style headers mapped to dap_local) are "
    "sell-in / distributor-acquisition evidence from historical lineup imports — not PM bottom or true "
    "landed cost (logistics is not modeled here). They are not equivalent to SKU controlled_cost_amount "
    "(internal cost basis) and must not be used as a controlled cost input without explicit cost-basis verification."
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
    makes explicit that DAP is NOT SKU controlled cost and must never be mapped directly as a cost
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
    "It is NOT equivalent to SKU controlled cost (PM bottom) and must not be used as a cost input "
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


class LineupCaseAttachPlanPatch(BaseModel):
    # None detaches the case from any plan. Plan linkage is optional enrichment for forward
    # buy-planning, never a precondition for viewing or working a lineup case.
    commercial_plan_id: int | None = None


class ConfirmWithPoBody(BaseModel):
    po_numbers: list[str] = Field(min_length=1, description="One or more PO numbers to link")
    notes: str | None = Field(default=None, max_length=1024)


class PoAutoLinkDismissBody(BaseModel):
    proposal_key: str = Field(min_length=1, max_length=128)
    case_id: int = Field(ge=1)
    purchase_order_id: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=256)


class PoAutoLinkApplyItem(BaseModel):
    case_id: int = Field(ge=1)
    purchase_order_id: int = Field(ge=1)
    notes: str | None = Field(default=None, max_length=1024)


class PoAutoLinkApplyBody(BaseModel):
    items: list[PoAutoLinkApplyItem] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=1024)


class CommercialLineupLinePatch(BaseModel):
    quantity_units: float | None = None
    msrp_local: float | None = None
    promo_price_evidence_local: float | None = None
    customer_feedback: str | None = Field(default=None, max_length=1024)
    internal_notes: str | None = Field(default=None, max_length=1024)


# Pricing/quantity edits are draft-only (pre-sync staging). Negotiation annotations
# (customer feedback / internal notes) stay editable through the review loop.
LINEUP_LINE_PRICING_EDIT_STATUSES = {"draft_imported"}
LINEUP_LINE_ANNOTATION_EDIT_STATUSES = {"draft_imported", "validated", "pending_review"}


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


class AssignDistributorBody(BaseModel):
    """Assign a distributor to a case's lines.

    Provide exactly one of: ``distributor_id`` (an existing dim, e.g. a shipment-evidence
    suggestion) OR ``new_code`` + ``new_name`` + ``confirm_create=true`` to create a new
    ``dim_distributor`` (steward-confirmed). ``only_unassigned`` (default true) writes only lines
    without a distributor.
    """

    distributor_id: int | None = Field(default=None, ge=1)
    new_code: str | None = Field(default=None, max_length=32)
    new_name: str | None = Field(default=None, max_length=256)
    confirm_create: bool = False
    only_unassigned: bool = True

    @model_validator(mode="after")
    def _validate(self) -> AssignDistributorBody:
        if self.distributor_id is not None:
            if self.new_code or self.new_name:
                raise ValueError("Provide either distributor_id or new_code+new_name, not both.")
            return self
        if not (self.new_code and self.new_name):
            raise ValueError("distributor_id, or new_code + new_name (to create), is required.")
        if not self.confirm_create:
            raise ValueError("confirm_create must be true to create a new distributor.")
        return self


def _case_payload(
    case: CommercialLineupCase, line_count: int, linked_pos: list[dict] | None = None
) -> dict:
    pos = linked_pos or []
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
        "iteration_number": case.iteration_number,
        "product_line": case.product_line,
        "inferred_period_start": case.inferred_period_start.isoformat()
        if case.inferred_period_start
        else None,
        "notes": case.notes,
        "accepted_at": case.accepted_at.isoformat() if case.accepted_at else None,
        "accepted_by": case.accepted_by,
        "line_count": line_count,
        "linked_pos": pos,
        "po_count": len(pos),
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "superseded_by_case_id": case.superseded_by_case_id,
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
    catalogue_dirty = False
    for case in cases:
        if await ensure_case_product_line_from_catalogue(db, case):
            catalogue_dirty = True
    if catalogue_dirty:
        await db.commit()
    pos_by_case = await list_case_pos_bulk(db, [int(c.id) for c in cases])
    out = []
    for case in cases:
        line_count = (
            await db.execute(
                select(func.count(CommercialLineupLine.id)).where(CommercialLineupLine.case_id == case.id)
            )
        ).scalar_one()
        out.append(_case_payload(case, int(line_count), pos_by_case.get(int(case.id), [])))
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
    linked_pos = await list_case_pos(db, case_id)
    return _case_payload(case, int(line_count), linked_pos)


@router.get("/lineup-cases/{case_id}/entity-resolution-candidates")
async def get_lineup_entity_resolution_candidates(case_id: int, db: AsyncSession = Depends(get_db)):
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status == "cancelled":
        raise HTTPException(status_code=409, detail="Case is cancelled")
    return await collect_entity_resolution_candidates(db, case_id)


def _workbench_calc_field_metadata() -> list[dict[str, str]]:
    """Derived pricing chain outputs stored on lineup lines (pricing_chain_json.outputs)."""
    specs = [
        ("dealer_price", "Dealer price (calc)", "calc_dealer_price_local"),
        ("net_price", "Net price (calc)", "calc_net_price_local"),
        ("disti_cost", "Disti cost (calc)", "calc_disti_cost_local"),
        ("dap", "DAP (calc)", "calc_dap_cost_currency"),
        ("profit", "Profit total (calc)", "calc_profit_total"),
    ]
    return [
        {"id": f"calc:{k}", "group": "calculated", "label": lab, "field": field} for k, lab, field in specs
    ]


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
        ("dealer_margin_pct_evidence", "Dealer margin % (evidence)"),
        ("distributor_margin_pct_evidence", "Disti margin % (evidence)"),
        ("import_tax_pct_evidence", "Import tax % (evidence)"),
        ("roe_evidence", "ROE / FX rate (evidence)"),
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
        "calc_fields": _workbench_calc_field_metadata(),
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
    # Negotiation round counter: the first send (validated -> pending_review) is round 1.
    # When the customer bounces it back for revision (pending_review -> validated), a new
    # round begins, so increment then.
    if case.commercial_status == "pending_review" and body.status == "validated":
        case.iteration_number = (case.iteration_number or 1) + 1
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


@router.patch("/lineup-cases/{case_id}/plan")
async def patch_lineup_case_plan(
    case_id: int, body: LineupCaseAttachPlanPatch, db: AsyncSession = Depends(get_db)
):
    """Attach (or detach) a lineup case to a commercial plan.

    Plan linkage is optional enrichment — a case is browsable and workable on its own. Pass
    ``commercial_plan_id`` to attach, or ``null`` to detach.
    """
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if body.commercial_plan_id is not None and not await db.get(CommercialPlan, body.commercial_plan_id):
        raise HTTPException(
            status_code=400, detail=f"Unknown commercial_plan_id={body.commercial_plan_id}"
        )
    case.commercial_plan_id = body.commercial_plan_id
    await db.commit()
    await db.refresh(case)
    line_count = (
        await db.execute(
            select(func.count(CommercialLineupLine.id)).where(CommercialLineupLine.case_id == case_id)
        )
    ).scalar_one()
    return _case_payload(case, int(line_count))


@router.get("/lineup-cases/{case_id}/suggested-pos")
async def get_lineup_case_suggested_pos(case_id: int, db: AsyncSession = Depends(get_db)):
    """Observed purchase orders ranked by product overlap with this case (read-only)."""
    try:
        return await suggest_pos_for_case(db, case_id)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Lineup case not found")


@router.post("/lineup-cases/{case_id}/confirm-with-po", status_code=200)
async def confirm_lineup_case_with_po(
    case_id: int, body: ConfirmWithPoBody, db: AsyncSession = Depends(get_db)
):
    """Confirm a lineup case with PO number(s); case -> po_issued. Idempotent and amendment-aware.

    Available from any case status except ``cancelled`` — no forward approval ladder required.
    Each PO is normalized then looked up / created on ``purchase_order`` (distributor inferred from
    the case lines) and linked via ``commercial_lineup_case_po``. Re-confirming the same PO is a
    no-op; confirming a new PO appends a link.
    """
    try:
        return await confirm_case_with_po(
            db, case_id, po_numbers=body.po_numbers, notes=body.notes
        )
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    except CaseStatusNotConfirmableError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": f"Cannot confirm a case in status '{exc.status}'.",
                "remediation": "Cancelled cases cannot be confirmed with a PO.",
            },
        )
    except UnresolvedCaseDistributorError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "remediation": (
                    "Assign a single distributor on lineup lines (or use distributor assign) "
                    "before confirming with a PO."
                ),
            },
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/lineup-cases/{case_id}/suggested-distributors")
async def get_lineup_case_suggested_distributors(case_id: int, db: AsyncSession = Depends(get_db)):
    """Distributors suggested from shipment-evidence product corroboration (read-only).

    Every suggestion is an existing ``dim_distributor``. ``converged`` is true only when exactly one
    distinct distributor is found across the corroborating evidence.
    """
    try:
        return await suggest_distributors_for_case(db, case_id)
    except CaseNotFoundError:
        raise HTTPException(status_code=404, detail="Lineup case not found")


@router.post("/lineup-cases/{case_id}/assign-distributor", status_code=200)
async def post_lineup_case_assign_distributor(
    case_id: int, body: AssignDistributorBody, db: AsyncSession = Depends(get_db)
):
    """Assign a distributor to a case's lines (existing dim or steward-confirmed create).

    Fills the gap left by token-keyed entity resolution for lines that carry no distributor token.
    Writes only ``distributor_id``; cost / DAP / SKU assumptions are untouched.
    """
    try:
        return await assign_case_distributor(
            db,
            case_id,
            distributor_id=body.distributor_id,
            new_code=body.new_code,
            new_name=body.new_name,
            only_unassigned=body.only_unassigned,
        )
    except AssignCaseNotFoundError:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    except AssignCaseStatusNotResolvableError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Distributor assignment is only allowed while the case is in draft/review "
                f"(statuses: {', '.join(sorted(RESOLUTION_ALLOWED_CASE_STATUSES))}). "
                f"Current: '{exc.status}'"
            ),
        )
    except DistributorNotFoundError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown distributor_id={exc}")
    except DistributorCodeExistsError as exc:
        raise HTTPException(status_code=400, detail=f"Distributor code already exists: {exc.code}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/lineup/po-reconciliation")
async def get_po_reconciliation(
    case_id: int = Query(..., description="Lineup case to reconcile against its confirmed POs"),
    db: AsyncSession = Depends(get_db),
):
    """Units-primary reconciliation per (case x product); FX-bridged value is secondary/display."""
    try:
        return await reconcile_case(db, case_id)
    except ReconCaseNotFoundError:
        raise HTTPException(status_code=404, detail="Lineup case not found")


class GapDismissBody(BaseModel):
    purchase_order_id: int = Field(ge=1)
    reason_code: str = Field(min_length=1, max_length=64)


@router.get("/lineup/po-gap-worklist")
async def get_po_gap_worklist(
    include_dismissed: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """POs with shipments but no covering confirmed lineup, grouped by quarter/year."""
    return await po_gap_worklist(db, include_dismissed=include_dismissed)


@router.post("/lineup/po-gap-worklist/dismiss", status_code=200)
async def dismiss_po_gap(body: GapDismissBody, db: AsyncSession = Depends(get_db)):
    try:
        return await dismiss_gap_po(db, body.purchase_order_id, body.reason_code)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=404, detail="Purchase order not found")


@router.post("/lineup/po-gap-worklist/restore", status_code=200)
async def restore_po_gap(
    purchase_order_id: int = Query(..., ge=1), db: AsyncSession = Depends(get_db)
):
    try:
        return await restore_gap_po(db, purchase_order_id)
    except PurchaseOrderNotFoundError:
        raise HTTPException(status_code=404, detail="Purchase order not found")


@router.get("/lineup/po-auto-link/proposals")
async def get_po_auto_link_proposals(
    period: str | None = Query(default=None, description="Filter by case period_label or quarter token (e.g. 26Q1)"),
    customer_id: int | None = Query(default=None, ge=1),
    confidence: Literal["high", "medium"] | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=5000),
    include_dismissed: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Derived PO↔lineup link proposals (CRAD-primary period match). Proposes only — never confirms."""
    return await po_auto_link_proposals(
        db,
        period=period,
        customer_id=customer_id,
        confidence=confidence,
        limit=limit,
        include_dismissed=include_dismissed,
    )


@router.post("/lineup/po-auto-link/dismiss", status_code=200)
async def post_po_auto_link_dismiss(body: PoAutoLinkDismissBody, db: AsyncSession = Depends(get_db)):
    """Dismiss a proposal so it no longer appears in the default review list."""
    try:
        return await dismiss_auto_link_proposal(
            db,
            proposal_key=body.proposal_key,
            case_id=body.case_id,
            purchase_order_id=body.purchase_order_id,
            reason_code=body.reason_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/lineup/po-auto-link/restore", status_code=200)
async def post_po_auto_link_restore(
    proposal_key: str = Query(..., min_length=1, max_length=128),
    db: AsyncSession = Depends(get_db),
):
    """Restore a previously dismissed auto-link proposal."""
    try:
        return await restore_auto_link_proposal(db, proposal_key=proposal_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ProposalNotFoundError:
        raise HTTPException(status_code=404, detail="Dismissed proposal not found")


@router.post("/lineup/po-auto-link/apply", status_code=200)
async def post_po_auto_link_apply(body: PoAutoLinkApplyBody, db: AsyncSession = Depends(get_db)):
    """Link selected proposals (writes ``commercial_lineup_case_po``; case -> po_issued)."""
    try:
        return await apply_auto_link_proposals(
            db,
            items=[item.model_dump() for item in body.items],
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
            "pricing_chain_json": ln.pricing_chain_json if isinstance(ln.pricing_chain_json, dict) else None,
            "calc_dap_cost_currency": float(ln.calc_dap_cost_currency)
            if ln.calc_dap_cost_currency is not None
            else None,
            "calc_profit_total": float(ln.calc_profit_total) if ln.calc_profit_total is not None else None,
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
        uploaded_for_evidence = (
            d.get("uploaded")
            if isinstance(d.get("uploaded"), dict)
            else (
                raw_payload.get("uploaded")
                if isinstance(raw_payload.get("uploaded"), dict)
                else {}
            )
        )
        for field, val in lineup_evidence_from_uploaded(uploaded_for_evidence).items():
            if d.get(field) is None:
                d[field] = val
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
    """Edit lineup row fields. Pricing/qty edits are draft-only (pre-sync staging);
    customer feedback / internal notes stay editable through the review loop."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")

    wants_pricing_edit = any(
        v is not None
        for v in (body.quantity_units, body.msrp_local, body.promo_price_evidence_local)
    )
    wants_annotation_edit = body.customer_feedback is not None or body.internal_notes is not None

    if wants_pricing_edit and case.commercial_status not in LINEUP_LINE_PRICING_EDIT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                "Can only edit pricing/quantity on cases with status 'draft_imported'. "
                f"Current: '{case.commercial_status}'"
            ),
        )
    if wants_annotation_edit and case.commercial_status not in LINEUP_LINE_ANNOTATION_EDIT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                "Can only edit customer feedback / internal notes while the case is in "
                f"{sorted(LINEUP_LINE_ANNOTATION_EDIT_STATUSES)}. Current: '{case.commercial_status}'"
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
    if body.customer_feedback is not None:
        ln.customer_feedback = body.customer_feedback.strip() or None
    if body.internal_notes is not None:
        ln.internal_notes = body.internal_notes.strip() or None

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
        "customer_feedback": ln2.customer_feedback,
        "internal_notes": ln2.internal_notes,
        "diagnostic_codes": ln2.diagnostic_codes or [],
        "row_status": ln2.row_status,
        "mapping_confidence": float(ln2.mapping_confidence) if ln2.mapping_confidence is not None else None,
        "dap_semantics_note": _LINEUP_DAP_SEMANTICS_NOTE,
    }


@router.get("/lineup-cases/{case_id}/export")
async def export_lineup_case_customer_slice(
    case_id: int,
    customer_id: int = Query(..., description="Resolved DimCustomer id to slice the lineup for"),
    db: AsyncSession = Depends(get_db),
):
    """Download a single customer's slice of a lineup case as XLSX (full pricing chain).

    Presents persisted calc_* / pricing_chain_json values — never recomputes. DAP shown is the
    calculated cost-currency DAP, not PM bottom.
    """
    from app.services.commercial_planner.lineup_customer_export import (
        LineupExportNotFoundError,
        build_customer_lineup_slice_xlsx,
    )

    try:
        data, filename, _row_count = await build_customer_lineup_slice_xlsx(db, case_id, customer_id)
    except LineupExportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/lineup-cases/{case_id}/delete-preview")
async def delete_lineup_case_preview(case_id: int, db: AsyncSession = Depends(get_db)):
    """Preview superseded children that will be restored if this case is deleted."""
    from app.services.commercial_planner.lineup_case_supersession import superseded_child_summaries

    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    if case.commercial_status != "draft_imported":
        raise HTTPException(
            status_code=409,
            detail=f"Can only delete lineup cases with status 'draft_imported'. Current status: '{case.commercial_status}'",
        )
    children = (
        await db.execute(
            select(CommercialLineupCase).where(CommercialLineupCase.superseded_by_case_id == case_id)
        )
    ).scalars().all()
    summaries = superseded_child_summaries(list(children))
    return {
        "case_id": case_id,
        "file_name": case.file_name,
        "superseded_child_count": len(summaries),
        "superseded_children": summaries,
        "message": (
            f"This case supersedes {len(summaries)} file(s); deleting will restore them as active."
            if summaries
            else None
        ),
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
    children = list(
        (
            await db.execute(
                select(CommercialLineupCase).where(CommercialLineupCase.superseded_by_case_id == case_id)
            )
        ).scalars().all()
    )
    for child in children:
        child.superseded_by_case_id = None
        child.commercial_status = "draft_imported"
    await db.delete(case)
    await db.commit()
    return Response(status_code=204)


@router.post("/lineup-cases/{case_id}/parse-preview", status_code=200)
async def parse_lineup_case_preview(
    case_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Parse upload in memory; does not write CommercialLineupLine rows."""
    case = await db.get(CommercialLineupCase, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Lineup case not found")
    filename = file.filename or "upload"
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    try:
        preview = await preview_current_lineup_file(db, filename, file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parse preview failed: {exc}") from exc
    return {
        "case_id": case_id,
        "total_rows": preview.total_rows,
        "resolved_products": preview.resolved_products,
        "unresolved_products": preview.unresolved_products,
        "unknown_customer_rows": preview.unknown_customer_rows,
        "unknown_distributor_rows": preview.unknown_distributor_rows,
        "warnings": preview.warnings,
        "can_apply": preview.can_apply,
        "rows": preview.rows,
        "rows_truncated": preview.total_rows > len(preview.rows),
    }


@router.post("/lineup-cases/{case_id}/parse-apply")
async def parse_lineup_case_apply(
    case_id: int,
    file: UploadFile = File(...),
    confirm: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
):
    """Apply parsed upload after preview. Requires confirm=true. May return 202 for large files."""
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required to apply parse")
    filename = file.filename or "upload"
    file_bytes = await file.read()
    from app.services.commercial_planner.lineup_parse_api import execute_lineup_parse_upload

    return await execute_lineup_parse_upload(db, case_id, filename, file_bytes)


@router.post("/lineup/unified-import", status_code=202)
async def unified_lineup_import(
    files: list[UploadFile] = File(..., description="One or more .csv/.xlsx/.xlsm lineup files"),
    commercial_plan_id: int | None = Form(default=None),
    period_label: str | None = Form(default=None),
    country_code: str | None = Form(default=None),
    currency_code: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Unified multi-file lineup import: one CommercialLineupCase + one async parse job per file.

    Each file runs the full pricing chain (backwards SRP->DAP) + period/product-line inference via
    the shared lineup parser, tagged template_slug='unified_lineup'. Per-file progress is visible in
    the activity feed; a single bad file does not abort the batch. DAP stays evidence-only.
    """
    from app.services.commercial_planner.unified_lineup_import import dispatch_unified_lineup_import

    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")

    payloads: list[tuple[str, bytes]] = []
    for f in files:
        payloads.append((f.filename or "upload", await f.read()))

    try:
        return await dispatch_unified_lineup_import(
            db,
            payloads,
            commercial_plan_id=commercial_plan_id,
            period_label=period_label,
            country_code=country_code,
            currency_code=currency_code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lineup/bulk-backfill/preview")
async def bulk_lineup_backfill_preview(
    files: list[UploadFile] = File(..., description="Historical lineup workbooks"),
    folder_paths: list[str] | None = Form(default=None),
    manual_overrides: str | None = Form(default=None, description="JSON map of proposal_key or file_key overrides"),
    persist_session: bool = Form(default=True, description="When false, in-memory preview only (no ImportJob row)"),
    db: AsyncSession = Depends(get_db),
):
    """File-grain preview for bulk historical lineup backfill (no lineup table writes)."""
    import json

    from app.services.commercial_planner.lineup_bulk_backfill_api import execute_bulk_lineup_preview

    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")
    paths = list(folder_paths or [])
    payloads: list[tuple[str, bytes, str | None]] = []
    for i, f in enumerate(files):
        raw_folder = paths[i] if i < len(paths) else None
        folder = raw_folder.strip() if raw_folder and str(raw_folder).strip() else None
        payloads.append((f.filename or "upload", await f.read(), folder))
    overrides: dict | None = None
    if manual_overrides and manual_overrides.strip():
        try:
            parsed = json.loads(manual_overrides)
            overrides = parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"manual_overrides must be JSON: {exc}") from exc
    try:
        return await execute_bulk_lineup_preview(
            db,
            payloads,
            manual_overrides=overrides,
            persist_session=persist_session,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/lineup/bulk-backfill/apply", status_code=202)
async def bulk_lineup_backfill_apply(
    session_import_job_id: int = Form(...),
    confirm: bool = Form(default=False),
    approved_proposal_keys: str | None = Form(default=None),
    excluded_proposal_keys: str | None = Form(default=None),
    supersession_confirmations: str | None = Form(default=None),
    commercial_plan_id: int | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Batch-apply steward-approved bulk lineup preview (async; good files only)."""
    import json

    from app.services.commercial_planner.lineup_bulk_backfill_api import execute_bulk_lineup_apply

    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required to apply bulk backfill.")

    def _parse_keys(raw: str | None) -> list[str] | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            return [k.strip() for k in raw.split(",") if k.strip()]
        return None

    def _parse_confirmations(raw: str | None) -> dict[str, str] | None:
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        except json.JSONDecodeError:
            return None
        return None

    try:
        return await execute_bulk_lineup_apply(
            db,
            session_import_job_id,
            approved_proposal_keys=_parse_keys(approved_proposal_keys),
            excluded_proposal_keys=_parse_keys(excluded_proposal_keys),
            supersession_confirmations=_parse_confirmations(supersession_confirmations),
            commercial_plan_id=commercial_plan_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/lineup/bulk-backfill/preview/{session_import_job_id}")
async def bulk_lineup_backfill_get_preview(
    session_import_job_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Reload a persisted bulk lineup preview session."""
    from app.services.commercial_planner.lineup_bulk_backfill_apply import load_preview_session

    try:
        preview = await load_preview_session(db, session_import_job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"session_import_job_id": session_import_job_id, "preview": preview}


@router.post("/lineup-cases/{case_id}/parse-upload")
async def parse_lineup_case_upload(
    case_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Parse an uploaded lineup file, write CommercialLineupLine rows, and link an ImportJob audit record.

    DAP fields are stored as evidence (dap_evidence_local) only.
    Never mapped to SKU controlled cost or override_controlled_cost_amount.
    Large files may return HTTP 202 and run via Celery (activity feed).
    """
    filename = file.filename or "upload"
    file_bytes = await file.read()
    from app.services.commercial_planner.lineup_parse_api import execute_lineup_parse_upload

    return await execute_lineup_parse_upload(db, case_id, filename, file_bytes)


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


from app.api.v1.endpoints.commercial_planner_intelligence_routes import (
    router as _cp_intelligence_extra_router,
)
from app.api.v1.endpoints.commercial_planner_lineup_routes import router as _cp_lineup_extra_router

router.include_router(_cp_lineup_extra_router)
router.include_router(_cp_intelligence_extra_router)
