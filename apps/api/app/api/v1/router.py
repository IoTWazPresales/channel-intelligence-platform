import logging

from fastapi import APIRouter, Depends

from app.core.feature_flags import commercial_planner_enabled
from app.core.security import Role, get_current_user, normalize_role
from app.api.deps import get_db
from app.core.product_line_scope import (
    apply_product_line_guc,
    product_line_scope_for,
    request_editable_product_lines,
    request_product_lines,
    request_role,
)
from app.core.tenant_scope import request_tenant_id, tenant_id_from_user
from app.models.product_line_access import UserProductLineAccess

logger = logging.getLogger(__name__)


async def _bind_request_tenant(
    user: dict = Depends(get_current_user),
    db=Depends(get_db),
):
    """Scope ORM reads to the signed-in tenant and product lines (admin: all lines)."""
    from sqlalchemy import select

    tid = tenant_id_from_user(user)
    token = request_tenant_id.set(tid)
    read_token = None
    edit_token = None
    role_token = None
    uid = str(user.get("id") or "")
    scope_kind = "unset"
    if uid.isdigit():
        # D-0056: an admin sees and edits every product line without an assignment.
        is_admin = user.get("role") == Role.ADMIN
        rows = []
        if not is_admin:
            rows = (
                await db.execute(
                    select(UserProductLineAccess).where(UserProductLineAccess.user_id == int(uid))
                )
            ).scalars().all()
        read, edit = product_line_scope_for(
            is_admin=is_admin,
            assignments=((row.product_line, bool(row.can_edit)) for row in rows),
        )
        read_token = request_product_lines.set(read)
        edit_token = request_editable_product_lines.set(edit)
        # Server-side role (the same source require_roles trusts), bound as cip.request_role:
        # shipment evidence with no product and no resolved identity is steward/admin only.
        raw_role = user.get("role")
        role_token = request_role.set(normalize_role(getattr(raw_role, "value", raw_role)).value)
        # The sign-in and access-row lookups normally began this transaction before the
        # scope was known, so the after_begin listener bound nothing; bind it now. Every
        # later transaction, on this session or any SessionLocal(), is bound by the listener.
        await apply_product_line_guc(db)
        scope_kind = "all" if is_admin else f"assigned:{len(read)}"
    logger.info("tenant_scope bound tenant=%s product_lines=%s", tid, scope_kind)
    try:
        yield
    finally:
        request_tenant_id.reset(token)
        if read_token is not None:
            request_product_lines.reset(read_token)
        if edit_token is not None:
            request_editable_product_lines.reset(edit_token)
        if role_token is not None:
            request_role.reset(role_token)
from app.api.v1.endpoints import (
    administration,
    auth,
    brief,
    budgets,
    buy_plans,
    channel_intelligence,
    channel_ops,
    commercial_planner,
    case_approval,
    cpor_cases,
    cpor_fx,
    cpor_exports,
    cpor_historical_import,
    cpor_payment_evidence,
    cst_steward,
    dashboards,
    dev_wipe,
    catalog,
    competition,
    customers,
    dashboard,
    distributors,
    exceptions,
    forecasts,
    grid_fields,
    imports,
    imports_product_master,
    inbound_shipments,
    inventory,
    lineup,
    listing_capture,
    planning,
    platform_audit,
    mappings,
    ops,
    plan_vs_executed,
    po_management,
    product_master_gaps,
    pricing,
    products,
    promo_exports,
    promotions,
    query,
    reference,
    report_exports,
    roadmap,
    saved_reports,
    sellout,
    semantics,
    shipment_evidence,
    shipping,
    shipping_mailer,
    sql_viewer,
    steward_audit,
    stock_leaves,
    supply,
)

# Router-level authentication. In stub mode get_current_user resolves admin@local and never
# raises, so local dev and the pytest suite are unchanged. In session mode (CIP_AUTH_MODE=session)
# every route below requires a bearer; before this, auth was per-endpoint and a route
# enumeration on 2026-09-21 found 127 of 229 GET routes serving data with no token.
# Endpoint-level get_current_user / require_roles dependencies still apply on top (FastAPI
# caches the resolved user per request, so the lookup runs once).
api_router = APIRouter(dependencies=[Depends(get_current_user), Depends(_bind_request_tenant)])

# The one route that must answer without a bearer so a session can be created at all.
public_router = APIRouter()
public_router.include_router(auth.public_router, prefix="/auth", tags=["auth"])
if commercial_planner_enabled():
    public_router.include_router(case_approval.public_router, prefix="/case-approval", tags=["case-approval"])

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(brief.router, prefix="/brief", tags=["brief"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(catalog.router, prefix="/catalog", tags=["catalog"])
api_router.include_router(reference.router, prefix="/reference", tags=["reference"])
api_router.include_router(products.router, prefix="/products", tags=["products"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(distributors.router, prefix="/distributors", tags=["distributors"])
api_router.include_router(sellout.router, prefix="/sellout", tags=["sellout"])
api_router.include_router(semantics.router, prefix="/semantics", tags=["semantics"])
api_router.include_router(query.router, prefix="/query", tags=["query"])
api_router.include_router(saved_reports.router, prefix="/saved-reports", tags=["saved-reports"])
api_router.include_router(dashboards.router, prefix="/dashboards", tags=["dashboards"])
api_router.include_router(report_exports.router, prefix="/reports", tags=["reports"])
api_router.include_router(channel_ops.router, prefix="/channel-ops", tags=["channel-ops"])
api_router.include_router(grid_fields.router, prefix="/grid-fields", tags=["grid-fields"])
api_router.include_router(
    channel_intelligence.router, prefix="/channel-intelligence", tags=["channel-intelligence"]
)
api_router.include_router(listing_capture.router, prefix="/listing-capture", tags=["listing-capture"])
api_router.include_router(inbound_shipments.router, prefix="/inbound-shipments", tags=["inbound-shipments"])
api_router.include_router(shipment_evidence.router, prefix="/shipment-evidence", tags=["shipment-evidence"])
api_router.include_router(shipping.router, prefix="/shipping", tags=["shipping"])
api_router.include_router(supply.router, prefix="/supply", tags=["supply"])
api_router.include_router(stock_leaves.router, prefix="/stock", tags=["stock"])
api_router.include_router(planning.router, prefix="/planning", tags=["planning"])
api_router.include_router(administration.router, prefix="/administration", tags=["administration"])
api_router.include_router(
    shipping_mailer.router, prefix="/shipping-mailer", tags=["shipping-mailer"]
)
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(forecasts.router, prefix="/forecasts", tags=["forecasts"])
api_router.include_router(buy_plans.router, prefix="/buy-plans", tags=["buy-plans"])
if commercial_planner_enabled():
    api_router.include_router(commercial_planner.router, prefix="/commercial-planner", tags=["commercial-planner"])
    api_router.include_router(po_management.router, prefix="/po-management", tags=["po-management"])
    api_router.include_router(plan_vs_executed.router, prefix="/plan-vs-executed", tags=["plan-vs-executed"])
    api_router.include_router(cpor_cases.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(case_approval.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cpor_fx.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cpor_exports.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cpor_historical_import.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cpor_payment_evidence.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cst_steward.router, prefix="/cst-steward", tags=["cst-steward"])
api_router.include_router(pricing.router, prefix="/pricing", tags=["pricing"])
api_router.include_router(promotions.router, prefix="/promotions", tags=["promotions"])
api_router.include_router(promo_exports.router, prefix="/promotions", tags=["promotions"])
api_router.include_router(lineup.router, prefix="/lineup", tags=["lineup"])
api_router.include_router(competition.router, prefix="/competition", tags=["competition"])
api_router.include_router(roadmap.router, prefix="/roadmap", tags=["roadmap"])
api_router.include_router(budgets.router, prefix="/budgets", tags=["budgets"])
api_router.include_router(imports.router, prefix="/imports", tags=["imports"])
api_router.include_router(
    imports_product_master.router,
    prefix="/imports/product-master",
    tags=["imports-product-master"],
)
api_router.include_router(mappings.router, prefix="/mappings", tags=["mappings"])
api_router.include_router(steward_audit.router, prefix="/admin", tags=["admin"])
api_router.include_router(platform_audit.router, prefix="/admin", tags=["admin"])
api_router.include_router(sql_viewer.router, prefix="/admin", tags=["admin"])
api_router.include_router(ops.router, prefix="/admin", tags=["admin"])
api_router.include_router(product_master_gaps.router, prefix="/product-master-gaps", tags=["product-master-gaps"])
api_router.include_router(exceptions.router, prefix="/exceptions", tags=["exceptions"])
api_router.include_router(dev_wipe.router, prefix="/dev", tags=["dev"])
