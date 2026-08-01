"""P3-4 visibility helpers — personal vs published + role-aware share."""

from __future__ import annotations

from typing import Any, Sequence

from app.core.security import Role, normalize_role

ALL_ROLES = ("admin", "steward", "planner", "viewer")


def parse_user_id(user: dict | None) -> int | None:
    if not user:
        return None
    raw = user.get("id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def user_role_str(user: dict | None) -> str:
    if not user:
        return Role.VIEWER.value
    role = user.get("role")
    if isinstance(role, Role):
        return role.value
    return normalize_role(str(role) if role is not None else None).value


def normalize_shared_roles(raw: Sequence[str] | None) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for r in raw:
        n = normalize_role(str(r)).value
        if n not in out:
            out.append(n)
    return out


def role_may_view_shared(role: str, shared_roles: Sequence[str] | None) -> bool:
    """Empty shared_roles on a published item = visible to all tenant roles."""
    if role == Role.ADMIN.value:
        return True
    roles = list(shared_roles or [])
    if not roles:
        return True
    return role in roles


def can_view_owned_item(
    *,
    visibility: str,
    owner_user_id: int | None,
    shared_roles: Sequence[str] | None,
    user: dict | None,
) -> bool:
    role = user_role_str(user)
    if role == Role.ADMIN.value:
        return True
    uid = parse_user_id(user)
    if visibility == "personal":
        return uid is not None and owner_user_id is not None and uid == owner_user_id
    if visibility == "published":
        if uid is not None and owner_user_id is not None and uid == owner_user_id:
            return True
        return role_may_view_shared(role, shared_roles)
    return False


def can_edit_owned_item(
    *,
    owner_user_id: int | None,
    user: dict | None,
) -> bool:
    role = user_role_str(user)
    if role == Role.ADMIN.value:
        return True
    uid = parse_user_id(user)
    return uid is not None and owner_user_id is not None and uid == owner_user_id


def item_to_dict(row: Any, *, kind: str = "report") -> dict[str, Any]:
    base = {
        "id": int(row.id),
        "tenant_id": row.tenant_id,
        "owner_user_id": int(row.owner_user_id) if row.owner_user_id is not None else None,
        "name": row.name,
        "description": row.description,
        "visibility": row.visibility,
        "shared_roles": list(row.shared_roles or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if kind == "report":
        base.update(
            {
                "metric_key": row.metric_key,
                "grains": list(row.grains or []),
                "filters": dict(row.filters or {}),
                "visual": row.visual,
            }
        )
    return base
