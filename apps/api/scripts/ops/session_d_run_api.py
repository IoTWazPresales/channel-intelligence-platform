"""Start uvicorn on :8001 with DATABASE_* from .env, optionally rewritten to cip_test.

Does not edit .env. Env overrides live only in this process.

  python scripts/ops/session_d_run_api.py cip_test
  python scripts/ops/session_d_run_api.py env

cip_test: rewrite DATABASE_URL, DATABASE_URL_SYNC, and DATABASE_URL_SYNC_MIGRATE
to database name cip_test. DATABASE_URL (async) is also rewritten because
GET /health/ready uses AsyncSessionLocal, not the sync URLs. If only the sync
vars were set, /health/ready would still report cip — that is a STOP, not a proof.

env: force DATABASE_* from the .env file (ignore inherited shell values) so
restore cannot accidentally keep a cip_test override from a parent process.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

API_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = API_ROOT / ".env"
DB_KEYS = (
    "DATABASE_URL",
    "DATABASE_URL_SYNC",
    "DATABASE_URL_SYNC_MIGRATE",
    "DATABASE_URL_SYNC_WRITABLE",
    "DATABASE_URL_LOCAL",
    "DATABASE_URL_LOCAL_SYNC",
)


def _parse_env_file() -> dict[str, str]:
    out: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return out
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k:
            out[k] = v
    return out


def _rewrite_dbname(url: str, dbname: str) -> str:
    p = urlparse(url)
    return urlunparse(p._replace(path=f"/{dbname}"))


def _url_dbname(url: str) -> str:
    path = urlparse(url).path or ""
    return path.lstrip("/") or "(empty)"


def apply_mode(mode: str) -> None:
    file_vals = _parse_env_file()
    for k, v in file_vals.items():
        if k in DB_KEYS or k not in os.environ:
            os.environ[k] = v
    # Always overlay DATABASE_* from .env so a parent shell cannot leak cip_test
    # into "env" restore, and so cip_test rewrite starts from file truth.
    for k in DB_KEYS:
        if k in file_vals:
            os.environ[k] = file_vals[k]
        elif mode == "env" and k in os.environ:
            del os.environ[k]
    if mode == "cip_test":
        sync = os.environ.get("DATABASE_URL_SYNC") or ""
        if not sync:
            raise SystemExit("DATABASE_URL_SYNC missing after reading .env")
        for k in DB_KEYS:
            if os.environ.get(k):
                os.environ[k] = _rewrite_dbname(os.environ[k], "cip_test")
        if not os.environ.get("DATABASE_URL_SYNC_MIGRATE"):
            os.environ["DATABASE_URL_SYNC_MIGRATE"] = os.environ["DATABASE_URL_SYNC"]
    print("session_d_run_api mode", mode)
    for k in (
        "DATABASE_URL",
        "DATABASE_URL_SYNC",
        "DATABASE_URL_SYNC_MIGRATE",
    ):
        val = os.environ.get(k)
        if not val:
            print(k, "(unset)")
        else:
            print(k, "dbname", _url_dbname(val))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("cip_test", "env"))
    args = parser.parse_args()
    os.chdir(API_ROOT)
    sys.path.insert(0, str(API_ROOT))
    apply_mode(args.mode)
    import uvicorn  # noqa: E402 — after env rewrite

    uvicorn.run("app.main:app", host="127.0.0.1", port=8001, reload=False)


if __name__ == "__main__":
    main()
