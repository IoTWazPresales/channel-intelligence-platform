"""SQL execute counter for bulk-delete routes (one round trip per cursor execute)."""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from fastapi import Response

from app.db.session import engine
from app.services.db_sql_counter import SqlExecuteCounter, sql_counter_scope

logger = logging.getLogger(__name__)


@contextmanager
def bulk_delete_sql_probe() -> Iterator[SqlExecuteCounter]:
    """Always instrument bulk-delete handlers; log count + elapsed for ops debugging."""
    t0 = time.perf_counter()
    with sql_counter_scope(engine) as counter:
        yield counter
    elapsed_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "bulk_delete_sql_probe statements=%s elapsed_ms=%.0f",
        counter.count,
        elapsed_ms,
    )


def apply_sql_probe_headers(response: Response, counter: SqlExecuteCounter) -> None:
    response.headers["X-CIP-SQL-Count"] = str(counter.count)
    if counter.statements:
        response.headers["X-CIP-SQL-First"] = counter.statements[0][:512]
