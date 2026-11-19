"""One heavy read shared by the widget calls that need it.

A dashboard with six widgets sends six ``POST /query/execute`` calls at once. The query result
cache is keyed per metric, so six metrics over the same filters each re-ran the same heavy read
(the plan-vs-executed read model for every A1 metric, the portfolio roll-up for every A2 metric)
and each waited behind the others. Here the read is shared: concurrent callers wait for one load,
and a finished load is reused for the query cache's own TTL, so a result is never older than the
cached query results it feeds.

The key carries the tenant, the read's arguments and the request scope (product lines, role,
My accounts) that row security applies, so a read made under one scope never serves another.
A load that fails for one caller (its session went away) is retried once on the caller's own
session instead of failing the callers that were waiting on it.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.query.cache import DEFAULT_TTL_SECONDS
from app.services.brief_swr_cache import StaleWhileRevalidate

# No stale serving: the same freshness the query result cache already promises.
_SHARED = StaleWhileRevalidate(fresh_seconds=DEFAULT_TTL_SECONDS, stale_seconds=DEFAULT_TTL_SECONDS)


def _scope() -> dict[str, Any]:
    from app.core.my_accounts import request_my_account_ids
    from app.core.product_line_scope import request_product_lines, request_role, scope_csv

    ids = request_my_account_ids.get()
    return {
        "product_lines": scope_csv(request_product_lines.get()),
        "role": request_role.get(),
        "my_account_ids": sorted(ids) if ids else None,
    }


def _key(namespace: str, args: dict[str, Any], tenant_id: str) -> str:
    raw = json.dumps(
        {"ns": namespace, "tenant_id": tenant_id, "args": args, "scope": _scope()},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def shared_read(
    namespace: str,
    args: dict[str, Any],
    tenant_id: str,
    compute: Callable[[], Awaitable[Any]],
) -> Any:
    """Return ``compute()``, sharing one load between callers with the same tenant, scope and args.

    The result is handed to every caller as is: callers must treat it as read-only.
    """
    key = _key(namespace, args, tenant_id)
    try:
        return await _SHARED.get(key, compute)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 - the shared load ran on another caller's session
        return await compute()


def clear_shared_reads() -> None:
    """Test helper."""
    _SHARED.clear()
