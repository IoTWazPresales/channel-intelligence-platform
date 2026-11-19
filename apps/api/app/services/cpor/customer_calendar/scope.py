"""Transaction-local tenant context for the calendar tables' forced RLS policies."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session


def bind_calendar_tenant(db: Session, tenant_id: str) -> None:
    if not tenant_id or not tenant_id.strip():
        raise ValueError("A calendar tenant is required")
    db.execute(select(func.set_config("cip.customer_calendar_tenant_id", tenant_id, True)))
