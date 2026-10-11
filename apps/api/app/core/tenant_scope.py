"""Tenant scoping helpers for P2-3 isolation."""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any

from sqlalchemy.sql import ColumnElement


logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"

# Set for the life of an authenticated API request. Unset means "do not add a
# predicate" so workers, scripts, and login itself keep their current reads.
request_tenant_id: ContextVar[str | None] = ContextVar("cip_request_tenant_id", default=None)

# Filled by install_tenant_select_scope(). Read at execution time.
TENANT_CLASSES: list[type] = []

_INSTALLED = False


def tenant_id_from_user(user: dict | None) -> str:
    if not user:
        return DEFAULT_TENANT_ID
    raw = user.get("tenant_id")
    tid = str(raw).strip() if raw is not None else ""
    return tid or DEFAULT_TENANT_ID


def where_tenant(column: Any, user: dict | None) -> ColumnElement[bool]:
    """SQLAlchemy boolean expression: column == caller's tenant."""
    return column == tenant_id_from_user(user)


def install_tenant_select_scope() -> None:
    """ORM selects of tenant-owned classes gain tenant_id == request tenant.

    Login runs before the context var is set, so the user row load is not
    filtered by a tenant that is not known yet. Bulk writes are unchanged.
    """
    global _INSTALLED
    if _INSTALLED:
        return

    from sqlalchemy import event
    from sqlalchemy.orm import Session, with_loader_criteria

    from app.models.cpor import CporCase
    from app.models.cpor_payment import CporPaymentEvidence
    from app.models.customer_code_mint_setting import CustomerCodeMintSetting
    from app.models.derived import WeeksOfCoverObservation
    from app.models.dimensions import DimCustomer, DimDistributor, DimProduct
    from app.models.distributor_code_mint_setting import DistributorCodeMintSetting
    from app.models.fact_customer_sellthrough import FactCustomerSellthrough
    from app.models.fact_demand_forecast import FactDemandForecast
    from app.models.facts import (
        FactInboundShipment,
        FactInventoryCustomer,
        FactInventoryDistributor,
        FactSalesSellout,
    )
    from app.models.iam import AppUser
    from app.models.ingestion import ImportJob
    from app.models.report_delivery import ReportDelivery, ReportSchedule
    from app.models.saved_reports import Dashboard, DashboardWidget, SavedReport
    from app.models.shipping_mailer_recipient import ShippingMailerRecipient
    from app.models.sql_viewer_audit import SqlViewerAudit
    from app.models.steward_audit import StewardAuditEvent

    TENANT_CLASSES.clear()
    TENANT_CLASSES.extend(
        [
            AppUser,
            CporCase,
            CporPaymentEvidence,
            CustomerCodeMintSetting,
            Dashboard,
            DashboardWidget,
            DimCustomer,
            DimDistributor,
            DimProduct,
            DistributorCodeMintSetting,
            FactCustomerSellthrough,
            FactDemandForecast,
            FactInboundShipment,
            FactInventoryCustomer,
            FactInventoryDistributor,
            FactSalesSellout,
            ImportJob,
            ReportDelivery,
            ReportSchedule,
            SavedReport,
            ShippingMailerRecipient,
            SqlViewerAudit,
            StewardAuditEvent,
            WeeksOfCoverObservation,
        ]
    )

    @event.listens_for(Session, "do_orm_execute")
    def _scope_tenant_select(execute_state: Any) -> None:
        if not execute_state.is_select:
            return
        if execute_state.is_column_load or execute_state.is_relationship_load:
            return
        tid = request_tenant_id.get()
        if not tid or not TENANT_CLASSES:
            return

        def _match(model: Any) -> Any:
            # Closure variable, not a default arg: the lambda cache keys on its value.
            return model.tenant_id == tid

        execute_state.statement = execute_state.statement.options(
            *[
                with_loader_criteria(cls, _match, include_aliases=True)
                for cls in TENANT_CLASSES
            ]
        )
        logger.debug("tenant_scope select tenant=%s", tid)

    _INSTALLED = True
