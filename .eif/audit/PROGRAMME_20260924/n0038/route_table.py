"""N-0038: print every mounted CPOR and shipment-evidence route with method and the role now required.

Read-only: imports the FastAPI app and introspects routes; no database access.
"""

from fastapi.routing import APIRoute

from app.core.security import get_current_user
from app.main import app

_Q = "require_roles.<locals>._dep"
_ORDER = ["admin", "steward", "planner", "viewer"]


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
    for c in _calls(route.dependant):
        if getattr(c, "__qualname__", "") == _Q:
            for cell in c.__closure__ or ():
                if isinstance(cell.cell_contents, set):
                    return sorted((r.value for r in cell.cell_contents), key=_ORDER.index)
    return None


for prefix in ("/api/v1/cpor/", "/api/v1/shipment-evidence"):
    print(f"\n{prefix}\n")
    print("| # | Method | Path | Handler | Role required |")
    print("|---|--------|------|---------|---------------|")
    n = 0
    for r in app.routes:
        if not isinstance(r, APIRoute) or not r.path.startswith(prefix):
            continue
        n += 1
        method = ",".join(sorted(m for m in r.methods if m not in {"HEAD", "OPTIONS"}))
        roles = _roles(r)
        if roles is not None:
            need = " + ".join(roles)
        elif get_current_user in _calls(r.dependant):
            need = "any signed-in user (read)"
        else:
            need = "NONE"
        print(f"| {n} | {method} | `{r.path}` | `{r.endpoint.__module__.rsplit('.', 1)[-1]}.{r.endpoint.__name__}` | {need} |")
