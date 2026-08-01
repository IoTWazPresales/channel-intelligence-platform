"""B1 analogue demand forecast for products with no sell-out history.

Matching axes (domain §2.3 / SEMANTICS B1-05): product_line (required), series_name,
form_factor, price_band, specs_json.gpu, plus roadmap predecessor when present.
Confidence always ``low``; bands widened vs velocity method.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.commercial_lineup import CommercialLineupLine
from app.models.dimensions import DimProduct
from app.models.fact_customer_velocity import FactCustomerVelocity
from app.models.fact_demand_forecast import FactDemandForecast
from app.models.facts import FactProductRoadmap
from app.services.demand_forecast.velocity_compute import (
    _bands,
    demand_forecast_velocity_source_key,
)

logger = logging.getLogger(__name__)

_ANALOGUE_BAND_WIDEN = Decimal("1.5")


def demand_forecast_analogue_source_key(
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int,
    period_start: date,
) -> str:
    return (
        f"demand-forecast:analogue:{int(distributor_id)}:{int(product_id)}:"
        f"{int(customer_id)}:{period_start.isoformat()}"
    )


def _gpu_token(specs: dict | None) -> str | None:
    if not isinstance(specs, dict):
        return None
    for key in ("gpu", "GPU", "graphics", "Graphics"):
        val = specs.get(key)
        if val is None:
            continue
        if isinstance(val, dict):
            name = val.get("name") or val.get("model")
            return str(name).strip().lower() if name else None
        return str(val).strip().lower() or None
    return None


def _score_analogue(target: DimProduct, candidate: DimProduct) -> tuple[int, dict[str, Any]]:
    """Higher score = better match. product_line mismatch → score 0."""
    basis: dict[str, Any] = {"matched": [], "scale": 1.0}
    if not target.product_line or not candidate.product_line:
        return 0, basis
    if str(target.product_line).strip().upper() != str(candidate.product_line).strip().upper():
        return 0, basis
    score = 10
    basis["matched"].append("product_line")

    if target.series_name and candidate.series_name:
        if str(target.series_name).strip().upper() == str(candidate.series_name).strip().upper():
            score += 5
            basis["matched"].append("series_name")
    if target.form_factor and candidate.form_factor:
        if str(target.form_factor).strip().lower() == str(candidate.form_factor).strip().lower():
            score += 3
            basis["matched"].append("form_factor")
    if target.price_band and candidate.price_band:
        if str(target.price_band).strip().lower() == str(candidate.price_band).strip().lower():
            score += 2
            basis["matched"].append("price_band")
    tg = _gpu_token(target.specs_json)
    cg = _gpu_token(candidate.specs_json)
    if tg and cg and tg == cg:
        score += 2
        basis["matched"].append("gpu")
    return score, basis


def _has_positive_velocity(db: Session, product_id: int) -> bool:
    n = db.scalar(
        select(func.count())
        .select_from(FactCustomerVelocity)
        .where(
            FactCustomerVelocity.product_id == int(product_id),
            FactCustomerVelocity.velocity_52wk.is_not(None),
            FactCustomerVelocity.velocity_52wk > 0,
        )
    )
    return bool(n and int(n) > 0)


def find_analogue_product(db: Session, product_id: int) -> tuple[DimProduct, dict[str, Any]] | None:
    target = db.get(DimProduct, int(product_id))
    if target is None:
        return None

    # Predecessor from roadmap (product → replacement candidate is reverse; also check
    # rows where this product is the replacement of an older SKU with velocity).
    roadmap = db.execute(
        select(FactProductRoadmap).where(
            (FactProductRoadmap.product_id == int(product_id))
            | (FactProductRoadmap.replacement_candidate_id == int(product_id))
        )
    ).scalars().all()
    for rm in roadmap:
        pred_id = None
        if rm.replacement_candidate_id == int(product_id):
            pred_id = int(rm.product_id)
        elif rm.product_id == int(product_id) and rm.replacement_candidate_id:
            # target listed as retiring into candidate — prefer candidate if it has velocity
            pred_id = int(rm.replacement_candidate_id)
        if pred_id and pred_id != int(product_id) and _has_positive_velocity(db, pred_id):
            pred = db.get(DimProduct, pred_id)
            if pred is not None:
                basis = {
                    "matched": ["predecessor"],
                    "scale": 1.0,
                    "source": "fact_product_roadmap",
                }
                return pred, basis

    if not target.product_line:
        return None

    candidates = list(
        db.scalars(
            select(DimProduct).where(
                DimProduct.product_line == target.product_line,
                DimProduct.id != int(product_id),
                DimProduct.is_active.is_(True),
            )
        ).all()
    )
    scored: list[tuple[int, float, DimProduct, dict[str, Any]]] = []
    for cand in candidates:
        if not _has_positive_velocity(db, int(cand.id)):
            continue
        score, basis = _score_analogue(target, cand)
        if score <= 0:
            continue
        # Prefer stronger velocity as tie-break
        v = db.scalar(
            select(func.max(FactCustomerVelocity.velocity_52wk)).where(
                FactCustomerVelocity.product_id == int(cand.id)
            )
        )
        scored.append((score, float(v or 0), cand, basis))

    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    _score, _v, best, basis = scored[0]
    return best, basis


def generate_analogue_demand_forecasts(
    db: Session,
    *,
    product_ids: list[int] | None = None,
    weeks_ahead: int = 13,
    skip_overrides: bool = True,
    max_products: int = 200,
) -> dict[str, Any]:
    """Create analogue-method rows for no-history products.

    Default product set: active lineup products lacking positive velocity (capped).
    """
    if product_ids:
        targets = [int(x) for x in product_ids]
    else:
        targets = list(
            db.scalars(
                select(DimProduct.id)
                .where(
                    DimProduct.is_active.is_(True),
                    DimProduct.id.in_(
                        select(CommercialLineupLine.product_id).where(
                            CommercialLineupLine.product_id.is_not(None)
                        )
                    ),
                    ~DimProduct.id.in_(
                        select(FactCustomerVelocity.product_id).where(
                            FactCustomerVelocity.velocity_52wk.is_not(None),
                            FactCustomerVelocity.velocity_52wk > 0,
                        )
                    ),
                )
                .limit(int(max_products))
            ).all()
        )

    considered = 0
    upserted = 0
    skipped_has_velocity = 0
    skipped_no_analogue = 0
    skipped_override = 0
    proven: list[dict[str, Any]] = []

    override_keys: set[tuple[int, int, int, date]] = set()
    if skip_overrides:
        for d, p, c, per in db.execute(
            select(
                FactDemandForecast.distributor_id,
                FactDemandForecast.product_id,
                FactDemandForecast.customer_id,
                FactDemandForecast.period_start,
            ).where(FactDemandForecast.is_override.is_(True))
        ).all():
            override_keys.add((int(d), int(p), int(c), per))

    tbl = FactDemandForecast.__table__

    for pid in targets:
        considered += 1
        if _has_positive_velocity(db, int(pid)):
            skipped_has_velocity += 1
            continue
        found = find_analogue_product(db, int(pid))
        if found is None:
            skipped_no_analogue += 1
            continue
        analogue, basis = found
        scale = Decimal(str(basis.get("scale") or 1))

        # Borrow grain from analogue velocity rows (keeps dist×cust partition).
        vel_rows = list(
            db.scalars(
                select(FactCustomerVelocity).where(
                    FactCustomerVelocity.product_id == int(analogue.id),
                    FactCustomerVelocity.velocity_52wk.is_not(None),
                    FactCustomerVelocity.velocity_52wk > 0,
                )
            ).all()
        )
        if not vel_rows:
            skipped_no_analogue += 1
            continue

        product_upserts = 0
        for row in vel_rows:
            velocity_52 = Decimal(str(row.velocity_52wk))
            seasonal = Decimal(str(row.seasonal_index or 1))
            base = velocity_52 * seasonal * scale
            units, lower, upper = _bands(
                forecast_units=base,
                velocity_52=velocity_52,
                velocity_4wk=Decimal(str(row.velocity_4wk)) if row.velocity_4wk is not None else None,
            )
            # Widen bands; confidence capped low
            lower = max(Decimal("0"), lower / _ANALOGUE_BAND_WIDEN)
            upper = upper * _ANALOGUE_BAND_WIDEN
            anchor = row.computed_through_date
            dist_id = int(row.distributor_id)
            cust_id = int(row.customer_id)

            for week in range(1, weeks_ahead + 1):
                period_start = anchor + timedelta(days=week * 7)
                grain = (dist_id, int(pid), cust_id, period_start)
                if grain in override_keys:
                    skipped_override += 1
                    continue
                source_key = demand_forecast_analogue_source_key(
                    distributor_id=dist_id,
                    product_id=int(pid),
                    customer_id=cust_id,
                    period_start=period_start,
                )
                values = {
                    "tenant_id": None,
                    "distributor_id": dist_id,
                    "product_id": int(pid),
                    "customer_id": cust_id,
                    "period_start": period_start,
                    "forecast_units": float(units),
                    "lower_band": float(lower),
                    "upper_band": float(upper),
                    "method": "analogue",
                    "confidence_level": "low",
                    "velocity_basis": None,
                    "seasonal_index": float(seasonal),
                    "analogue_product_id": int(analogue.id),
                    "analogue_basis": basis,
                    "is_override": False,
                    "source_key": source_key,
                }
                stmt = pg_insert(tbl).values(**values)
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_fact_demand_forecast_grain",
                    set_={
                        "forecast_units": stmt.excluded.forecast_units,
                        "lower_band": stmt.excluded.lower_band,
                        "upper_band": stmt.excluded.upper_band,
                        "method": stmt.excluded.method,
                        "confidence_level": stmt.excluded.confidence_level,
                        "seasonal_index": stmt.excluded.seasonal_index,
                        "analogue_product_id": stmt.excluded.analogue_product_id,
                        "analogue_basis": stmt.excluded.analogue_basis,
                        "source_key": stmt.excluded.source_key,
                        "is_override": False,
                    },
                    where=(tbl.c.is_override.is_(False)),
                )
                result = db.execute(stmt)
                if result.rowcount:
                    upserted += 1
                    product_upserts += 1

        if product_upserts:
            proven.append(
                {
                    "product_id": int(pid),
                    "analogue_product_id": int(analogue.id),
                    "analogue_sku": analogue.sku,
                    "basis": basis,
                    "rows": product_upserts,
                }
            )

    out = {
        "considered": considered,
        "upserted": upserted,
        "skipped_has_velocity": skipped_has_velocity,
        "skipped_no_analogue": skipped_no_analogue,
        "skipped_override": skipped_override,
        "proven": proven[:20],
    }
    logger.info("analogue demand forecasts %s", out)
    return out


def apply_manual_override(
    db: Session,
    *,
    distributor_id: int,
    product_id: int,
    customer_id: int,
    period_start: date,
    forecast_units: float,
) -> FactDemandForecast:
    """Force override precedence over velocity/analogue for one grain."""
    units = float(forecast_units)
    existing = db.scalar(
        select(FactDemandForecast).where(
            FactDemandForecast.distributor_id == int(distributor_id),
            FactDemandForecast.product_id == int(product_id),
            FactDemandForecast.customer_id == int(customer_id),
            FactDemandForecast.period_start == period_start,
        )
    )
    if existing is None:
        row = FactDemandForecast(
            distributor_id=int(distributor_id),
            product_id=int(product_id),
            customer_id=int(customer_id),
            period_start=period_start,
            forecast_units=units,
            lower_band=units,
            upper_band=units,
            method="manual",
            confidence_level="override",
            is_override=True,
            source_key=demand_forecast_velocity_source_key(
                distributor_id=int(distributor_id),
                product_id=int(product_id),
                customer_id=int(customer_id),
                period_start=period_start,
            ).replace(":velocity:", ":manual:"),
        )
        db.add(row)
        return row
    existing.forecast_units = units
    existing.lower_band = units
    existing.upper_band = units
    existing.method = "manual"
    existing.confidence_level = "override"
    existing.is_override = True
    return existing
