"""N-0086: print every mounted import / steward route with method and the role it requires.

Read-only: imports the FastAPI app and introspects routes; no database access.
Run from apps/api with its virtualenv:  python <this file> [prefix ...]
"""

import sys

from fastapi.routing import APIRoute

from app.core.security import get_current_user
from app.main import app

_Q = "require_roles.<locals>._dep"
_ORDER = ["admin", "steward", "planner", "viewer"]

DEFAULT_PREFIXES = (
    "/api/v1/imports",
    "/api/v1/cst-steward",
    "/api/v1/mappings",
    "/api/v1/product-master-gaps",
    "/api/v1/exceptions",
    "/api/v1/shipment-evidence",
    "/api/v1/listing-capture",
    "/api/v1/customers",
    "/api/v1/distributors",
    "/api/v1/admin",
)


def _calls(d):
    out = []
    if d is None:
        return out
    if getattr(d, "call", None) is not None:
        out.append(d.call)
    for x in getattr(d, "dependencies", None) or []:
        out.extend(_calls(x))
    return out


def _roles(route):
    found = []
    for c in _calls(route.dependant):
        if getattr(c, "__qualname__", "") == _Q:
            for cell in c.__closure__ or ():
                if isinstance(cell.cell_contents, set):
                    found.append(sorted((r.value for r in cell.cell_contents), key=_ORDER.index))
    if not found:
        return None
    # admin always passes; the strictest set wins when several gates stack.
    best = min(found, key=len)
    return sorted(set(best) | {"admin"}, key=_ORDER.index)


def main(prefixes):
    for prefix in prefixes:
        print(f"\n{prefix}\n")
        print("| # | Method | Path | Handler | Role required |")
        print("|---|--------|------|---------|---------------|")
        n = 0
        for r in app.routes:
            if not isinstance(r, APIRoute):
                continue
            if not (r.path == prefix or r.path.startswith(prefix + "/")):
                continue
            n += 1
            method = ",".join(sorted(m for m in r.methods if m not in {"HEAD", "OPTIONS"}))
            roles = _roles(r)
            if roles is not None:
                need = " + ".join(roles)
            elif get_current_user in _calls(r.dependant):
                need = "any signed-in user"
            else:
                need = "NONE"
            mod = r.endpoint.__module__.rsplit(".", 1)[-1]
            print(f"| {n} | {method} | `{r.path}` | `{mod}.{r.endpoint.__name__}` | {need} |")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT_PREFIXES)
