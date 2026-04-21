from fastapi import APIRouter

from app.core.security import Role

router = APIRouter()


@router.get("/me")
async def me():
    """Stub auth: supply `X-User-Id` and `X-User-Role` headers from the UI."""
    return {
        "id": "demo-user",
        "role": Role.ADMIN.value,
        "roles_supported": [r.value for r in Role],
    }
