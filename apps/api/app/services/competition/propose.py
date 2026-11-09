"""Propose competitor mappings using the deterministic scorer."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dimensions import DimCompetitorProduct, DimProduct
from app.models.facts import FactCompetitorMapping
from app.services.competition.matching import (
    CompetitorCandidate,
    InternalProductProfile,
    score_competitor_candidate,
)


def _spec_tokens(specs: dict | None) -> list[str]:
    if not specs:
        return []
    out: list[str] = []
    for key, val in specs.items():
        out.append(str(key))
        if isinstance(val, (list, tuple)):
            out.extend(str(v) for v in val)
        elif val is not None:
            out.append(str(val))
    return out


def _internal_profile(product: DimProduct) -> InternalProductProfile:
    return InternalProductProfile(
        title=product.name or product.sku,
        category=product.category,
        form_factor=product.form_factor,
        spec_tokens=_spec_tokens(product.specs_json),
        internal_price=None,
    )


def _candidate_profile(comp: DimCompetitorProduct) -> CompetitorCandidate:
    form = None
    if isinstance(comp.specs_json, dict):
        form = comp.specs_json.get("form_factor") or comp.specs_json.get("form")
        if form is not None:
            form = str(form)
    return CompetitorCandidate(
        title=comp.name or comp.sku,
        category=comp.category,
        form_factor=form,
        spec_tokens=_spec_tokens(comp.specs_json),
        competitor_price=None,
    )


async def propose_competitor_mappings(
    db: AsyncSession,
    *,
    min_score: float = 0.55,
    max_per_product: int = 3,
) -> dict:
    """Score every active internal product against competitor products.

    Creates `fact_competitor_mapping` rows with approval_status=pending for the
    top matches above min_score that do not already exist. Never invents a second
    scorer — always calls score_competitor_candidate.
    """
    products = (await db.execute(select(DimProduct))).scalars().all()
    competitors = (await db.execute(select(DimCompetitorProduct))).scalars().all()
    existing = (await db.execute(select(FactCompetitorMapping))).scalars().all()
    existing_pairs = {(m.product_id, m.competitor_product_id) for m in existing}

    if not products or not competitors:
        return {
            "created": 0,
            "considered_products": len(products),
            "considered_competitors": len(competitors),
            "skipped_existing": 0,
            "min_score": min_score,
        }

    created = 0
    skipped_existing = 0
    for product in products:
        scored: list[tuple[float, DimCompetitorProduct, object]] = []
        internal = _internal_profile(product)
        for comp in competitors:
            result = score_competitor_candidate(internal, _candidate_profile(comp))
            if result.score >= min_score:
                scored.append((result.score, comp, result))
        scored.sort(key=lambda t: t[0], reverse=True)
        for score, comp, result in scored[:max_per_product]:
            pair = (product.id, comp.id)
            if pair in existing_pairs:
                skipped_existing += 1
                continue
            db.add(
                FactCompetitorMapping(
                    product_id=product.id,
                    competitor_product_id=comp.id,
                    score=result.score,
                    explanation=result.explanation,
                    approval_status="pending",
                )
            )
            existing_pairs.add(pair)
            created += 1

    if created:
        await db.commit()
    return {
        "created": created,
        "considered_products": len(products),
        "considered_competitors": len(competitors),
        "skipped_existing": skipped_existing,
        "min_score": min_score,
    }
