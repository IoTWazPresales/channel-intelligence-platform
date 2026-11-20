from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.dimensions import DimProduct
from app.models.facts import FactPricing
from app.services.grid_fields import customer_labels, fact_row_dict, reference_fields

router = APIRouter()

RETIRED_PRICING_MESSAGE = (
    "Recorded prices was retired. Prices now come from the line-up retail price "
    "and the latest shelf price seen on customer listings"
)

_RETIRED_PRICING_DETAIL = {
    "message": RETIRED_PRICING_MESSAGE,
    "lineup_href": "/lineup",
    "listings_href": "/listing-capture?tab=registry",
}


@router.get("/facts")
async def list_pricing_facts(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(FactPricing).order_by(FactPricing.effective_date.desc()))
    rows = res.scalars().all()
    customers = await customer_labels(db, (p.customer_id for p in rows))
    out = []
    for p in rows:
        prod = await db.get(DimProduct, p.product_id)
        out.append(pricing_fact_row_dict(p, prod, customers))
    return out


def pricing_fact_row_dict(
    p: FactPricing, prod: DimProduct | None, customers: dict[int, tuple[str, str]]
) -> dict:
    return {
        **fact_row_dict(p, "pricing.facts"),
        **reference_fields(customer_id=p.customer_id, customers=customers),
        "id": p.id,
        "sku": prod.sku if prod else None,
        "sales_model_name": prod.sales_model_name if prod else None,
        "effective_date": p.effective_date.isoformat(),
        "list_price": float(p.list_price),
        "net_price": float(p.net_price),
        "currency": p.currency,
    }


@router.get("/recommendations")
async def list_pricing_recommendations():
    return _RETIRED_PRICING_DETAIL


@router.api_route("", methods=["POST", "PUT", "PATCH", "DELETE"])
@router.api_route("/{retired_path:path}", methods=["POST", "PUT", "PATCH", "DELETE"])
async def retired_pricing_write():
    # No body parsing, database dependency, entity resolution or queue writes.
    raise HTTPException(status_code=410, detail=_RETIRED_PRICING_DETAIL)
