from fastapi import APIRouter, HTTPException

router = APIRouter()

# Spec §7 / U6: the scaffold is not a second planner. Cases own the plan.
# The old plan tables were dropped in 20261011_0032. These routes do not read them.
_PARKED = {
    "parked": True,
    "message": "Promotion plans are promotion cases.",
    "href": "/commercial-planner/cpor-cases",
    "cpor_cases_href": "/commercial-planner/cpor-cases",
}


def _parked() -> None:
    raise HTTPException(status_code=409, detail=_PARKED)


@router.get("/plans")
async def list_promo_plans():
    """Parked (spec §7). Does not read fact_promotion_plan."""
    _parked()


@router.get("/readiness")
async def list_promo_readiness():
    """Parked (spec §7 / §11). Does not read promo readiness rows."""
    _parked()


@router.get("/meta")
async def promotions_meta():
    return _PARKED


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_promo_plan(plan_id: int):
    _ = plan_id
    _parked()


@router.post("/plans/clear-all", status_code=200)
async def clear_promo_plans():
    _parked()


@router.delete("/readiness/{row_id}", status_code=204)
async def delete_promo_readiness(row_id: int):
    _ = row_id
    _parked()


@router.post("/readiness/clear-all", status_code=200)
async def clear_promo_readiness():
    _parked()
