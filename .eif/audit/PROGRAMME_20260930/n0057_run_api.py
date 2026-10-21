"""API on 127.0.0.1:8002 bound to cip_test.

Uses the same local default DSN as app settings, with the database name
rewritten. Does not edit .env and does not open cip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
os.chdir(API_ROOT)
sys.path.insert(0, str(API_ROOT))

os.environ["DATABASE_URL"] = "postgresql+asyncpg://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC"] = "postgresql://cip:cip@localhost:5432/cip_test"
os.environ["DATABASE_URL_SYNC_MIGRATE"] = os.environ["DATABASE_URL_SYNC"]

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8002, reload=False)
