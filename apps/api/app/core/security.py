"""Auth stub: extend with JWT / SSO."""

from enum import Enum

from fastapi import Depends, Header, HTTPException, status


class Role(str, Enum):
    ADMIN = "admin"
    DATA_STEWARD = "data_steward"
    COMMERCIAL_MANAGER = "commercial_manager"
    PLANNER = "planner"
    PRODUCT_MANAGER = "product_manager"
    FINANCE_REVIEWER = "finance_reviewer"
    EXECUTIVE_VIEWER = "executive_viewer"


def get_current_user_stub(
    x_user_role: str | None = Header(default=Role.ADMIN.value, alias="X-User-Role"),
    x_user_id: str | None = Header(default="demo-user", alias="X-User-Id"),
) -> dict:
    try:
        role = Role(x_user_role)
    except ValueError:
        role = Role.ADMIN
    return {"id": x_user_id, "role": role}


def require_roles(*allowed: Role):
    def _dep(user: dict = Depends(get_current_user_stub)) -> dict:
        if user["role"] not in allowed and user["role"] != Role.ADMIN:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user

    return _dep
