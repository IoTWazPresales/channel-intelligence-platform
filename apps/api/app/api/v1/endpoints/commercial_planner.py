from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_db
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


def _line_payload(
    line: CommercialPlanLine,
    *,
    customer_code: str | None = None,
    customer_name: str | None = None,
    distributor_code: str | None = None,
    distributor_name: str | None = None,
    product_sku: str | None = None,
    product_name: str | None = None,
) -> dict:
    return {
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
            )
            .select_from(CommercialPlanLine)
            .join(DimCustomer, DimCustomer.id == CommercialPlanLine.customer_id)
            .join(DimDistributor, DimDistributor.id == CommercialPlanLine.distributor_id)
            .join(DimProduct, DimProduct.id == CommercialPlanLine.product_id)
            .where(CommercialPlanLine.id == line.id)
        )
    ).one_or_none()
    if r is None:
        return _line_payload(line)
    cc, cn, dc, dn, ps, pn = r
    return _line_payload(
        line,
        customer_code=cc,
        customer_name=cn,
        distributor_code=dc,
        distributor_name=dn,
        product_sku=ps,
        product_name=pn,
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
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    lines = (await db.execute(select(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id))).scalars().all()
    for line in lines:
        await db.delete(line)
    plan = await db.get(CommercialPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
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
            )
            .join(DimCustomer, DimCustomer.id == CommercialPlanLine.customer_id)
            .join(DimDistributor, DimDistributor.id == CommercialPlanLine.distributor_id)
            .join(DimProduct, DimProduct.id == CommercialPlanLine.product_id)
            .where(CommercialPlanLine.commercial_plan_id == plan_id)
            .order_by(CommercialPlanLine.id)
        )
    ).all()
    out = []
    for line, cc, cn, dc, dn, ps, pn in rows:
        out.append(
            _line_payload(
                line,
                customer_code=cc,
                customer_name=cn,
                distributor_code=dc,
                distributor_name=dn,
                product_sku=ps,
                product_name=pn,
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
    rows = (
        await db.execute(select(CommercialPlanLine).where(CommercialPlanLine.commercial_plan_id == plan_id).order_by(CommercialPlanLine.id))
    ).scalars().all()
    out: list[dict] = []
    for row in rows:
        avg_sellout = (
            await db.execute(
                select(func.coalesce(func.avg(FactSalesSellout.units), 0)).where(
                    FactSalesSellout.product_id == row.product_id, FactSalesSellout.customer_id == row.customer_id
                )
            )
        ).scalar_one()
        prior_planned = (
            await db.execute(
                select(func.avg(CommercialPlanLine.target_units)).where(
                    CommercialPlanLine.product_id == row.product_id,
                    CommercialPlanLine.customer_id == row.customer_id,
                    CommercialPlanLine.id != row.id,
                )
            )
        ).scalar_one()
        latest_forecast = (
            await db.execute(
                select(FactForecast.forecast_units)
                .where(FactForecast.product_id == row.product_id)
                .order_by(FactForecast.period_start.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        latest_net = (
            await db.execute(
                select(FactPricing.net_price)
                .where(FactPricing.product_id == row.product_id)
                .order_by(FactPricing.effective_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        inp = SuggestionInputs(
            avg_sellout_units=float(avg_sellout or 0.0),
            prior_planned_units=float(prior_planned) if prior_planned is not None else None,
            forecast_units=float(latest_forecast) if latest_forecast is not None else None,
            latest_net_price=float(latest_net) if latest_net is not None else None,
            target_srp_local=float(row.target_srp_local),
            promo_mix_pct=float(row.promo_mix_pct),
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
                        },
                    },
                    {
                        "type": "pricing_band",
                        "value": {"target_srp_local": srp, "promo_srp_local": promo_srp},
                        "reason": price_reason,
                        "confidence": price_conf,
                        "factors": {"latest_net_price": inp.latest_net_price, "target_srp_local": inp.target_srp_local},
                    },
                    {
                        "type": "promo_mix_pct",
                        "value": mix,
                        "reason": mix_reason,
                        "confidence": mix_conf,
                        "factors": {"avg_sellout_units": inp.avg_sellout_units, "forecast_units": inp.forecast_units},
                    },
                ],
            }
        )
    return out


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
):
    stmt = (
        select(CommercialCustomerTerm, DimCustomer.code, DimCustomer.name)
        .join(DimCustomer, DimCustomer.id == CommercialCustomerTerm.customer_id)
        .order_by(DimCustomer.code)
    )
    if q and q.strip():
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
):
    stmt = (
        select(CommercialDistributorTerm, DimDistributor.code, DimDistributor.name)
        .join(DimDistributor, DimDistributor.id == CommercialDistributorTerm.distributor_id)
        .order_by(DimDistributor.code)
    )
    if q and q.strip():
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
        )
        .join(
            HistoricalLineupImportHeader,
            HistoricalLineupImportHeader.id == HistoricalLineupImportLine.header_id,
        )
        .outerjoin(DimProduct, DimProduct.id == HistoricalLineupImportLine.product_id)
        .outerjoin(header_customer, header_customer.id == HistoricalLineupImportHeader.customer_id)
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
                "actual_dap_local": float(ln.actual_dap_local) if ln.actual_dap_local is not None else None,
                "disti_cost_local": float(ln.disti_cost_local) if ln.disti_cost_local is not None else None,
                "rebate_pct": float(ln.rebate_pct) if ln.rebate_pct is not None else None,
                "dealer_margin_pct": float(ln.dealer_margin_pct) if ln.dealer_margin_pct is not None else None,
                "vat_pct": float(ln.vat_pct) if ln.vat_pct is not None else None,
                "header_customer_id": header_customer_id,
                "header_customer_code": header_customer_code,
                "header_customer_name": header_customer_name,
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
