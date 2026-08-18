from fastapi import APIRouter

from app.core.feature_flags import commercial_planner_enabled
from app.api.v1.endpoints import (
    auth,
    budgets,
    buy_plans,
    channel_intelligence,
    channel_ops,
    commercial_planner,
    cpor_cases,
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
    imports,
    imports_product_master,
    inbound_shipments,
    inventory,
    lineup,
    listing_capture,
    mappings,
    market,
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
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
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
api_router.include_router(
    channel_intelligence.router, prefix="/channel-intelligence", tags=["channel-intelligence"]
)
api_router.include_router(listing_capture.router, prefix="/listing-capture", tags=["listing-capture"])
api_router.include_router(inbound_shipments.router, prefix="/inbound-shipments", tags=["inbound-shipments"])
api_router.include_router(shipment_evidence.router, prefix="/shipment-evidence", tags=["shipment-evidence"])
api_router.include_router(shipping.router, prefix="/shipping", tags=["shipping"])
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
    api_router.include_router(cpor_exports.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cpor_historical_import.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cpor_payment_evidence.router, prefix="/cpor", tags=["cpor"])
    api_router.include_router(cst_steward.router, prefix="/cst-steward", tags=["cst-steward"])
api_router.include_router(pricing.router, prefix="/pricing", tags=["pricing"])
api_router.include_router(promotions.router, prefix="/promotions", tags=["promotions"])
api_router.include_router(promo_exports.router, prefix="/promotions", tags=["promotions"])
api_router.include_router(lineup.router, prefix="/lineup", tags=["lineup"])
api_router.include_router(competition.router, prefix="/competition", tags=["competition"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
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
api_router.include_router(sql_viewer.router, prefix="/admin", tags=["admin"])
api_router.include_router(ops.router, prefix="/admin", tags=["admin"])
api_router.include_router(product_master_gaps.router, prefix="/product-master-gaps", tags=["product-master-gaps"])
api_router.include_router(exceptions.router, prefix="/exceptions", tags=["exceptions"])
api_router.include_router(dev_wipe.router, prefix="/dev", tags=["dev"])
