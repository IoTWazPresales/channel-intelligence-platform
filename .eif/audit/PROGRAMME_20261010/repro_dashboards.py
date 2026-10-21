"""Reproduce GET /api/v1/dashboards and print the exception class only."""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
os.chdir(ROOT / "apps" / "api")

from sqlalchemy import select

from app.api.v1.endpoints.dashboards import list_dashboards
from app.core.password import hash_session_token
from app.db.session import AsyncSessionLocal
from app.models.iam import AppUser, AuthSession


async def main() -> None:
    token = Path(os.environ["TEMP"], "cip-smoke-token.txt").read_text(encoding="utf-8").strip()
    async with AsyncSessionLocal() as db:
        session = (
            await db.execute(select(AuthSession).where(AuthSession.token_hash == hash_session_token(token)))
        ).scalar_one()
        user_row = await db.get(AppUser, session.user_id)
        user = {
            "id": user_row.id,
            "role": user_row.role,
            "tenant_id": user_row.tenant_id,
        }
        try:
            result = await list_dashboards(db=db, user=user)
            print(f"ok count={result.get('count')}")
        except Exception as exc:
            print(type(exc).__name__)
            line = str(exc).splitlines()[0][:240]
            print(line)


if __name__ == "__main__":
    asyncio.run(main())
