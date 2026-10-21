"""N-0065 perf capture: drive real GET read paths in-process against cip under three
product-line settings and record per-statement SQL timings.

Safety: every connection is opened with default_transaction_read_only=on and
statement_timeout=60s, NullPool; the app's own async and sync session factories are
swapped for these read-only ones. No writes are possible. GET routes only.
Usage: python n0065_capture.py <out.json> [mode ...]   modes: unset star NB
"""
import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "apps" / "api"))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import event  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_settings  # noqa: E402

url = get_settings().database_url_sync
if url.startswith("postgresql://"):
    url = "postgresql+psycopg://" + url[len("postgresql://"):]
RO_ARGS = {"options": "-c default_transaction_read_only=on -c statement_timeout=60000", "prepare_threshold": None}

from app.main import app  # noqa: E402
import app.db.session as s_async  # noqa: E402
import app.db.session_sync as s_sync  # noqa: E402
from app.api.deps import get_db  # noqa: E402
from app.core import security  # noqa: E402

a_engine = create_async_engine(url, poolclass=NullPool, connect_args=RO_ARGS)
y_engine = sa.create_engine(url, poolclass=NullPool, connect_args=RO_ARGS)
ASess = async_sessionmaker(a_engine, expire_on_commit=False, class_=AsyncSession)
YSess = sessionmaker(bind=y_engine, class_=Session, autoflush=False, autocommit=False)

orig = {"AsyncSessionLocal": s_async.AsyncSessionLocal, "engine": s_async.engine,
        "SessionLocal": s_sync.SessionLocal, "sync_engine": s_sync.sync_engine}
repl = {"AsyncSessionLocal": ASess, "engine": a_engine, "SessionLocal": YSess, "sync_engine": y_engine}
patched = 0
for name, mod in list(sys.modules.items()):
    if not name.startswith("app") or mod is None:
        continue
    for attr, o in orig.items():
        if getattr(mod, attr, None) is o:
            setattr(mod, attr, repl[attr])
            patched += 1
print("patched session refs:", patched)

STATE = {"label": None, "stmts": [], "commits": 0}


def _before(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("t0", []).append(time.perf_counter())


def _after(conn, cursor, statement, parameters, context, executemany):
    t0 = conn.info["t0"].pop()
    STATE["stmts"].append({"label": STATE["label"], "ms": round((time.perf_counter() - t0) * 1000, 1),
                           "rows": getattr(cursor, "rowcount", None), "sql": statement,
                           "params": parameters if isinstance(parameters, (dict, list, tuple)) else None,
                           "engine": "sync" if conn.engine is y_engine else "async"})


def _err(ctx):
    STATE["stmts"].append({"label": STATE["label"], "ms": None, "error": str(ctx.original_exception)[:300],
                           "sql": ctx.statement, "params": None})


for eng in (a_engine.sync_engine, y_engine):
    event.listen(eng, "before_cursor_execute", _before)
    event.listen(eng, "after_cursor_execute", _after)
    event.listen(eng, "handle_error", _err)
    event.listen(eng, "commit", lambda conn: STATE.__setitem__("commits", STATE["commits"] + 1))

MODE = {"v": None}


async def ro_get_db():
    async with ASess() as session:
        if MODE["v"] is not None:
            await session.execute(sa.text("SELECT set_config('cip.product_lines', :v, true)"), {"v": MODE["v"]})
            await session.execute(sa.text("SELECT set_config('cip.editable_product_lines', :v, true)"),
                                  {"v": MODE["v"]})
        yield session


TENANT = {"v": "default"}


async def probe_user():
    return security._user_payload("perf-probe", security.Role.ADMIN, tenant_id=TENANT["v"],
                                  email=None, display_name=None)


app.dependency_overrides[get_db] = ro_get_db
app.dependency_overrides[security.get_current_user] = probe_user
app.dependency_overrides[security.get_optional_current_user] = probe_user

with y_engine.connect() as c:
    print("database:", c.execute(sa.text("select current_database()")).scalar())
    TENANT["v"] = c.execute(sa.text("select tenant_id from dim_product group by 1 order by count(*) desc limit 1")).scalar()
    case_id = c.execute(sa.text(
        "select case_id from commercial_lineup_line group by 1 order by count(*) desc limit 1")).scalar()
print("tenant:", TENANT["v"], "lineup case:", case_id)

PATHS = [
    "/api/v1/sellout/commercial-lines",
    "/api/v1/sellout/commercial-summary",
    "/api/v1/channel-ops/sell-out",
    "/api/v1/shipping/lines",
    "/api/v1/shipping/summary",
    "/api/v1/shipping/commercial-summary",
    "/api/v1/supply/overview",
    "/api/v1/channel-ops/cover-distribution",
    "/api/v1/channel-ops/summary",
    "/api/v1/plan-vs-executed",
    "/api/v1/lineup/net-requirement",
    f"/api/v1/commercial-planner/lineup-cases/{case_id}/lines",
    f"/api/v1/commercial-planner/lineup/po-reconciliation?case_id={case_id}",
    "/api/v1/cpor/settlement/book",
    "/api/v1/dashboard/summary",
    "/api/v1/brief/signals",
]
if len(sys.argv) > 3 and sys.argv[3].startswith("/"):
    PATHS = sys.argv[3].split(",")

from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
modes = {"unset": None, "star": "*", "NB": "NB"}
want = (sys.argv[2].split(",") if len(sys.argv) > 2 else list(modes))
results = []
for m in want:
    MODE["v"] = modes[m]
    for p in PATHS:
        STATE["label"] = f"{m} {p}"
        n0 = len(STATE["stmts"])
        c0 = STATE["commits"]
        t0 = time.perf_counter()
        r = client.get(p)
        wall = round((time.perf_counter() - t0) * 1000)
        mine = STATE["stmts"][n0:]
        body = r.text[:200] if r.status_code != 200 else ""
        rows = None
        try:
            js = r.json()
            if isinstance(js, dict):
                for k in ("total", "total_count", "count", "row_count"):
                    if isinstance(js.get(k), int):
                        rows = js[k]
                        break
                if rows is None:
                    for k in ("items", "rows", "lines", "data"):
                        if isinstance(js.get(k), list):
                            rows = len(js[k])
                            break
            elif isinstance(js, list):
                rows = len(js)
        except Exception:
            pass
        top = sorted([s for s in mine if s.get("ms") is not None], key=lambda s: -s["ms"])[:1]
        errs = [s["error"] for s in mine if s.get("error")]
        print(f"{m:5} {r.status_code} {wall:>7}ms stmts={len(mine):3} rows={rows} commits={STATE['commits'] - c0}"
              f" top={top[0]['ms'] if top else None}ms {p} {body} {errs[:1]}", flush=True)
        results.append({"mode": m, "path": p, "status": r.status_code, "wall_ms": wall, "rows": rows,
                        "n_stmts": len(mine), "errors": errs, "body": body})

out = pathlib.Path(sys.argv[1])
out.write_text(json.dumps({"results": results, "stmts": STATE["stmts"]}, default=str, indent=1), encoding="utf-8")
print("wrote", out)
