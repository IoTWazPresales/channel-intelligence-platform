from fastapi import APIRouter

router = APIRouter()


@router.get("/placeholders")
async def market_placeholders():
    return {
        "category_trends": [],
        "share_panel": [],
        "competitive_benchmark_hooks": [
            {
                # Honesty (BACKLOG-160): `fact_competitor_price` and its list endpoint exist, but there is
                # no import template and no writer. "ready" is earned only when both exist.
                "name": "competitor_price_import",
                "status": "substrate",
                "source": "imports",
                "note": "Table and list endpoint exist; no import template or writer yet.",
            },
        ],
        "note": "Foundation only: wire syndicated data when contracts exist.",
    }
