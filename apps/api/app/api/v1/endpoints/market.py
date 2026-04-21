from fastapi import APIRouter

router = APIRouter()


@router.get("/placeholders")
async def market_placeholders():
    return {
        "category_trends": [],
        "share_panel": [],
        "competitive_benchmark_hooks": [
            {"name": "competitor_price_import", "status": "ready", "source": "imports"},
        ],
        "note": "Foundation only: wire syndicated data when contracts exist.",
    }
