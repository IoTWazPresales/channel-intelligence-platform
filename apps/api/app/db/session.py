from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()


def _asyncpg_connect_args(database_url: str) -> dict:
    """
    Supabase / PgBouncer transaction pooler (:6543) cannot reuse named prepared statements.

    Both caches must be disabled:
    - statement_cache_size (asyncpg)
    - prepared_statement_cache_size (SQLAlchemy asyncpg dialect)
    Unique prepared statement names avoid DuplicatePreparedStatementError when statements
    leak across pooled server connections.
    """
    args: dict = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "prepared_statement_name_func": lambda: f"__asyncpg_{uuid4()}__",
    }
    if "localhost" not in database_url and "127.0.0.1" not in database_url:
        args["ssl"] = "require"
    return args


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    poolclass=NullPool,
    connect_args=_asyncpg_connect_args(settings.database_url),
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
