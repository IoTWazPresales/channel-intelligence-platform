from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # The product-line scope (N-0065 / D-0056) is bound by the Session ``after_begin``
    # listener (app.core.product_line_scope) at the start of every transaction, so
    # nothing is applied here.
    async with AsyncSessionLocal() as session:
        yield session


__all__ = ["get_db"]
