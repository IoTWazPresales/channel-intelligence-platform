"""Demo / dev catalog seed: **wipes the database** then reloads import templates + dimension rows.

For production-like environments, controlled Commercial Planner reference rows (**OPEN_CHANNEL**,
**UNASSIGNED**) are ensured by **Alembic migration** ``20260429_0022`` and/or
``python scripts/seed.py --commercial-system-reference-only`` (no wipe).

This module is not the sole portability path for those two rows — see ``reference_bootstrap``."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.derived import (
    BudgetHealth,
    BuyRecommendation,
    ExceptionInboxItem,
    PricingRecommendation,
    PromoReadiness,
    StockHealth,
    StockRisk,
    WeeksOfStock,
)
from app.models.dimensions import (
    DimBudgetOwner,
    DimChannel,
    DimCompetitorBrand,
    DimCompetitorProduct,
    DimCustomer,
    DimDistributor,
    DimProduct,
    DimPromotion,
    DimRegion,
    DimSource,
)
from app.models.lineup import FactLineupPlanItem
from app.models.promo_export import PromoPlanExport, PromoPlanExportEvent
from app.models.facts import (
    FactBudgetAllocation,
    FactBudgetActual,
    FactBudgetCommitment,
    FactBudgetRequest,
    FactBuyPlan,
    FactCompetitorMapping,
    FactCompetitorPrice,
    FactForecast,
    FactInboundShipment,
    FactInventoryCustomer,
    FactPricing,
    FactProductRoadmap,
    FactPromotionPlan,
    FactSalesSellout,
)
from app.models.ingestion import ImportJob, ImportRowResult, ImportTemplate, RawFileMetadata, SourceDefinition
from app.models.product_catalog import BusinessUnit, ProductCatalog
from app.models.mapping import EntityMappingQueue, ProductAlias
from app.services.planning.buy import BuyInputs, build_buy_plan
from app.services.planning.pricing import PricingInputs, pricing_state
from app.services.planning.wos import WosInputs, classify_stock_risk
from app.services.promo_export.cpor_xlsx import TEMPLATE_CODE, build_promo_plan_workbook_bytes
from app.services.imports.template_definitions import DEFAULT_SOURCES, IMPORT_TEMPLATE_ROWS
from app.storage.local import LocalStorageBackend

from app.services.commercial_planner.reference_bootstrap import ensure_commercial_planner_system_reference_data_sync


def _seed_import_core(session: Session) -> None:
    """Templates + provider rows (idempotent after Alembic or full wipe)."""
    for row in IMPORT_TEMPLATE_ROWS:
        exists = session.execute(select(ImportTemplate).where(ImportTemplate.slug == row["slug"])).scalar_one_or_none()
        if exists:
            continue
        session.add(
            ImportTemplate(
                slug=row["slug"],
                display_name=row["display_name"],
                description=row["description"],
                enabled=row["enabled"],
                hidden=row["hidden"],
                admin_only=row["admin_only"],
                requires_provider=row["requires_provider"],
                pipeline_handler=row["pipeline_handler"],
                destructive_apply_requires_confirm=row["destructive_apply_requires_confirm"],
                accepted_file_types=row["accepted_file_types"],
                expected_columns=row["expected_columns"],
            )
        )
    session.flush()
    for row in IMPORT_TEMPLATE_ROWS:
        tpl = session.scalar(select(ImportTemplate).where(ImportTemplate.slug == row["slug"]))
        if not tpl:
            continue
        tpl.display_name = row["display_name"]
        tpl.description = row["description"]
        tpl.enabled = row["enabled"]
        tpl.hidden = row["hidden"]
        tpl.admin_only = row["admin_only"]
        tpl.requires_provider = row["requires_provider"]
        tpl.pipeline_handler = row["pipeline_handler"]
        tpl.destructive_apply_requires_confirm = row["destructive_apply_requires_confirm"]
        tpl.accepted_file_types = row["accepted_file_types"]
        tpl.expected_columns = row["expected_columns"]
    session.flush()
    by_slug = {t.slug: t.id for t in session.scalars(select(ImportTemplate)).all()}
    for code, name, slug, kind in DEFAULT_SOURCES:
        if session.execute(select(SourceDefinition).where(SourceDefinition.code == code)).scalar_one_or_none():
            continue
        session.add(
            SourceDefinition(
                import_template_id=by_slug[slug],
                code=code,
                name=name,
                source_kind=kind,
                expected_template=None,
                parser_module=None,
                is_active=True,
            )
        )
    if not session.execute(select(SourceDefinition).where(SourceDefinition.code == "distributor_inventory")).scalar_one_or_none():
        session.add(
            SourceDefinition(
                import_template_id=by_slug["distributor_inventory"],
                code="distributor_inventory",
                name="Distributor Inventory Snapshot",
                source_kind="distributor_reports",
                expected_template=None,
                parser_module="app.ingestion.parsers.distributor_inventory",
                is_active=True,
            )
        )
    session.flush()
    disti_src = session.scalar(select(SourceDefinition).where(SourceDefinition.code == "distributor_inventory"))
    if disti_src and disti_src.expected_template:
        disti_src.expected_template = None
    session.flush()

    pc = session.scalar(
        select(ProductCatalog).join(BusinessUnit).where(
            BusinessUnit.code == "platform",
            ProductCatalog.code == "default_master",
        )
    )
    if pc:
        for code in ("product_catalog_default",):
            s = session.scalar(select(SourceDefinition).where(SourceDefinition.code == code))
            if s and s.product_catalog_id is None:
                s.product_catalog_id = pc.id
    session.flush()


def _wipe_all(session: Session) -> None:
    conn = session.connection()
    try:
        existing = set(inspect(conn).get_table_names())
    except Exception:  # noqa: BLE001
        existing = {t.name for t in Base.metadata.sorted_tables}
    for table in reversed(Base.metadata.sorted_tables):
        if table.name in existing:
            session.execute(table.delete())
    session.flush()


def run(session: Session, *, full_demo: bool = False) -> None:
    _wipe_all(session)
    _seed_import_core(session)

    regions = [
        DimRegion(code="NA-W", name="North America West"),
        DimRegion(code="NA-E", name="North America East"),
    ]
    channels = [
        DimChannel(code="RET", name="Retail"),
        DimChannel(code="ECOM", name="eCommerce"),
    ]
    distributors = [
        DimDistributor(code="DIST-01", name="Summit Supply Co."),
        DimDistributor(code="DIST-02", name="Harbor Wholesale"),
    ]
    session.add_all(regions + channels + distributors)
    session.flush()

    # System reference dimensions (OPEN_CHANNEL, UNASSIGNED) — same path as Alembic migration / seed flag.
    ensure_commercial_planner_system_reference_data_sync(session.connection())

    if not full_demo:
        session.commit()
        return

    customers = [
        DimCustomer(code="CUST-1001", name="Metro Market Group", region_id=regions[0].id, channel_id=channels[0].id),
        DimCustomer(code="CUST-1002", name="Lakeside Retailers", region_id=regions[1].id, channel_id=channels[0].id),
    ]
    products = [
        DimProduct(
            sku="SKU-ALPHA-01",
            name="Alpha Pro 200",
            category="Audio",
            form_factor="Soundbar",
            specs_json={"watts": "200", "channels": "3.1"},
            price_band="premium",
            channel_id=channels[0].id,
        ),
        DimProduct(
            sku="SKU-BRAVO-02",
            name="Bravo Mini",
            category="Audio",
            form_factor="Compact Speaker",
            specs_json={"watts": "40"},
            price_band="mid",
        ),
        DimProduct(
            sku="SKU-CHARLIE-03",
            name="Charlie Soundbar",
            category="Audio",
            form_factor="Soundbar",
            specs_json={"watts": "120", "channels": "2.1"},
            price_band="mid",
        ),
    ]
    session.add_all(customers + products)
    session.flush()

    owners = [DimBudgetOwner(name="Alex Rivera", email="alex@example.com")]
    session.add_all(owners)
    session.flush()

    promos = [
        DimPromotion(code="PROMO-Q2", name="Spring Audio Event", start_date=date.today(), end_date=date.today() + timedelta(days=45)),
    ]
    session.add_all(promos)
    session.flush()

    comp_brand = DimCompetitorBrand(name="Northwave Audio")
    session.add(comp_brand)
    session.flush()
    comp_products = [
        DimCompetitorProduct(
            brand_id=comp_brand.id,
            sku="NW-SB-300",
            name="Northwave Pulse 300",
            category="Audio",
            specs_json={"watts": "300", "channels": "3.1"},
        ),
        DimCompetitorProduct(
            brand_id=comp_brand.id,
            sku="NW-MINI",
            name="Northwave Mini Drop",
            category="Audio",
            specs_json={"watts": "45"},
        ),
    ]
    session.add_all(comp_products)
    session.flush()

    session.add_all(
        [
            ProductAlias(product_id=products[0].id, alias_value="APL-200-GL", alias_kind="distributor_code", confidence="high"),
            FactSalesSellout(
                product_id=products[0].id,
                customer_id=customers[0].id,
                channel_id=channels[0].id,
                distributor_id=distributors[0].id,
                period_start=date.today() - timedelta(days=7),
                units=420,
                revenue=63000,
            ),
            FactInventoryCustomer(
                product_id=products[0].id,
                customer_id=customers[0].id,
                as_of_date=date.today(),
                on_hand_units=180,
                on_order_units=60,
            ),
            FactInboundShipment(
                product_id=products[0].id,
                distributor_id=distributors[0].id,
                eta_date=date.today() + timedelta(days=10),
                quantity=120,
                reference="PO-77821",
                status="scheduled",
            ),
            FactForecast(
                product_id=products[0].id,
                customer_id=customers[0].id,
                period_start=date.today(),
                forecast_units=95,
                confidence_placeholder="medium",
            ),
            FactPricing(
                product_id=products[0].id,
                customer_id=customers[0].id,
                channel_id=channels[0].id,
                effective_date=date.today(),
                list_price=199.99,
                net_price=169.99,
                currency="USD",
            ),
            FactPromotionPlan(
                promotion_id=promos[0].id,
                product_id=products[0].id,
                expected_uplift_pct=18.0,
                support_needed="Incremental display allowance",
                stock_readiness="at_risk",
            ),
        ]
    )

    wos_inputs = WosInputs(on_hand=180, avg_weekly_demand=95, target_wos=6.0)
    risk = classify_stock_risk(wos_inputs)
    session.add(
        WeeksOfStock(
            product_id=products[0].id,
            customer_id=customers[0].id,
            as_of_date=date.today(),
            wos=wos_inputs.on_hand / wos_inputs.avg_weekly_demand,
            target_wos=wos_inputs.target_wos,
        )
    )
    session.add(
        StockHealth(
            product_id=products[0].id,
            customer_id=customers[0].id,
            as_of_date=date.today(),
            health_state=risk.kind,
            explanation=risk.explanation_summary,
        )
    )
    session.add(
        StockRisk(
            product_id=products[0].id,
            customer_id=customers[0].id,
            risk_kind=risk.kind,
            recommendation_type="stock_risk",
            status="active",
            confidence="high",
            explanation_summary=risk.explanation_summary,
            explanation_factors=risk.factors,
            impact_estimate="Potential lost sales if demand holds through promo window.",
            action_owner="planner_queue",
        )
    )

    buy = build_buy_plan(
        BuyInputs(
            forecast_weekly_demand=95,
            on_hand=180,
            inbound=180,
            target_wos=6.0,
            lead_time_weeks=4.0,
        ),
        today=date.today(),
    )
    buy_fact = FactBuyPlan(
        product_id=products[0].id,
        distributor_id=distributors[0].id,
        recommended_qty=buy.recommended_qty,
        recommended_window_start=buy.window_start,
        recommended_window_end=buy.window_end,
        rationale=buy.rationale,
        risk_if_not_ordered=buy.risk_if_not_ordered,
    )
    session.add(buy_fact)
    session.flush()
    session.add(
        BuyRecommendation(
            product_id=products[0].id,
            buy_plan_id=buy_fact.id,
            recommendation_type="buy",
            status="active",
            confidence="medium",
            explanation_summary=buy.rationale,
            explanation_factors={"recommended_qty": buy.recommended_qty, "window_start": str(buy.window_start)},
            impact_estimate="Closes coverage gap vs target WOS and lead time.",
            action_owner="procurement",
        )
    )

    price_rec = pricing_state(
        PricingInputs(
            current_net_price=169.99,
            reference_price=179.99,
            stock_risk_kind=risk.kind,
            days_to_promo=14,
            competitor_net=154.5,
        )
    )
    session.add(
        PricingRecommendation(
            product_id=products[0].id,
            suggested_state=price_rec.suggested_state,
            recommendation_type="pricing",
            status="active",
            confidence="medium",
            explanation_summary=price_rec.explanation_summary,
            explanation_factors=price_rec.factors,
            impact_estimate="Margin vs share trade-off in promo window.",
            action_owner="commercial_manager",
        )
    )

    session.add(
        PromoReadiness(
            promotion_id=promos[0].id,
            product_id=products[0].id,
            recommendation_type="promo_readiness",
            status="active",
            confidence="medium",
            explanation_summary="Inbound arrives after promo start; risk of stock-out during uplift.",
            explanation_factors={"eta_days": 10, "promo_start": str(date.today())},
            impact_estimate="Promo performance at risk without pull-forward or air freight.",
            action_owner="planner_queue",
        )
    )

    roadmap = FactProductRoadmap(
        product_id=products[2].id,
        lifecycle_phase="growth",
        replacement_candidate_id=None,
        launch_target=date.today() + timedelta(days=120),
        retire_target=None,
        whitespace_flag=True,
        overlap_flag=False,
    )
    session.add(roadmap)
    session.flush()

    session.add(
        FactCompetitorMapping(
            product_id=products[0].id,
            competitor_product_id=comp_products[0].id,
            score=0.82,
            explanation="Category, form factor, and spec overlap with premium soundbar band.",
            approval_status="pending",
        )
    )
    session.add(
        FactCompetitorPrice(
            competitor_product_id=comp_products[0].id,
            observed_at=datetime.now(timezone.utc),
            price=154.5,
            channel="Retail",
        )
    )

    session.add_all(
        [
            FactBudgetAllocation(
                owner_id=owners[0].id,
                category="Trade Marketing",
                period_start=date.today().replace(day=1),
                envelope_type="discretionary",
                allocated_amount=250000,
            ),
            FactBudgetCommitment(
                owner_id=owners[0].id,
                period_start=date.today().replace(day=1),
                committed_amount=180000,
                description="Committed displays and co-op",
            ),
            FactBudgetActual(
                owner_id=owners[0].id,
                period_start=date.today().replace(day=1),
                actual_amount=95000,
            ),
            FactBudgetRequest(
                owner_id=owners[0].id,
                amount=35000,
                initiative_type="promo_support",
                linked_product_id=products[0].id,
                linked_promotion_id=promos[0].id,
                justification_summary="Fund incremental promo support for Alpha Pro 200 in West region.",
                expected_impact="Protect share during competitor surge; estimated +6 pts lift.",
                risk_of_not_funding="Promo execution weakens; stock risk compounds with late inbound.",
                status="submitted",
            ),
        ]
    )
    session.flush()

    session.add(
        BudgetHealth(
            owner_id=owners[0].id,
            period_start=date.today().replace(day=1),
            remaining_amount=75000,
            pressure_state="elevated",
        )
    )

    session.add(
        ExceptionInboxItem(
            exception_type="delayed_inbound",
            severity="high",
            title="Inbound PO-77821 may miss promo readiness",
            detail="ETA 10d vs promo start this week for Alpha Pro 200.",
            explanation_summary="Late inbound vs planned uplift window.",
            explanation_factors={"po": "PO-77821", "eta_days": 10},
            status="open",
            owner="planner_queue",
            product_id=products[0].id,
        )
    )

    dist_src = session.execute(
        select(SourceDefinition).where(SourceDefinition.code == "distributor_inventory")
    ).scalar_one()

    job = ImportJob(
        source_id=dist_src.id,
        template_slug="distributor_inventory",
        import_mode="apply",
        status="completed",
        stage="validated",
        file_name="demo_inventory.csv",
        content_type="text/csv",
        inferred_schema={"row_count": 2, "columns": [{"name": "sku"}, {"name": "qty"}]},
        field_mapping={"sku": "sku", "qty": "quantity"},
        error_summary=None,
    )
    session.add(job)
    session.flush()
    session.add(RawFileMetadata(job_id=job.id, storage_key=f"demo/{job.id}.csv", byte_size=120, checksum="demo"))
    session.add(
        ImportRowResult(
            job_id=job.id,
            row_number=1,
            severity="info",
            code="parsed",
            message="Row parsed successfully (demo).",
        )
    )

    period_anchor = date.today().replace(day=1)
    pricing_row = session.execute(select(FactPricing).limit(1)).scalar_one()
    budget_row = session.execute(select(FactBudgetRequest).limit(1)).scalar_one()

    session.add_all(
        [
            FactLineupPlanItem(
                customer_id=customers[0].id,
                channel_id=channels[0].id,
                period_start=period_anchor,
                period_label="2026-Q2",
                product_id=products[0].id,
                predecessor_product_id=products[1].id,
                successor_product_id=products[2].id,
                current_range_summary="Alpha family current shelf set",
                planned_range_summary="Alpha Pro refresh + Bravo upsell",
                planned_launch_date=date.today() + timedelta(days=45),
                planned_eol_date=date.today() + timedelta(days=540),
                current_volume_units=420,
                planned_volume_units=610,
                overlap_cannibalization_flag=False,
                whitespace_gap_flag=False,
                approval_status="submitted",
                link_buy_plan_id=buy_fact.id,
                link_pricing_id=pricing_row.id,
                link_promotion_id=promos[0].id,
                link_budget_request_id=budget_row.id,
                link_roadmap_id=None,
                notes="Cross-links: buy plan, pricing row, promo, and budget request.",
            ),
            FactLineupPlanItem(
                customer_id=customers[0].id,
                channel_id=channels[0].id,
                period_start=period_anchor,
                period_label="2026-Q2",
                product_id=products[2].id,
                predecessor_product_id=None,
                successor_product_id=None,
                current_range_summary="Mid-tier soundbar",
                planned_range_summary="Hero gap in architect-led projects",
                planned_launch_date=date.today() + timedelta(days=120),
                planned_eol_date=None,
                current_volume_units=15,
                planned_volume_units=180,
                overlap_cannibalization_flag=False,
                whitespace_gap_flag=True,
                approval_status="draft",
                link_buy_plan_id=None,
                link_pricing_id=None,
                link_promotion_id=None,
                link_budget_request_id=None,
                link_roadmap_id=roadmap.id,
                notes="Whitespace candidate aligned to roadmap gap signal.",
            ),
        ]
    )

    data, digest = build_promo_plan_workbook_bytes(session, promos[0].id, default_customer_id=customers[0].id)
    demo_export = PromoPlanExport(
        promotion_id=promos[0].id,
        template_code=TEMPLATE_CODE,
        export_version=1,
        storage_key="pending",
        file_name=f"CPOR_PromoPlan_{promos[0].code}_v1.xlsx",
        checksum_sha256=digest,
        validation_status="passed",
        workflow_status="approved",
        created_by="seed",
        submitted_at=datetime.now(timezone.utc),
        decided_at=datetime.now(timezone.utc),
        decided_by="seed",
    )
    session.add(demo_export)
    session.flush()
    storage = LocalStorageBackend()
    demo_key = f"exports/promo/{demo_export.id}/cpor_v1.xlsx"
    storage.save(demo_key, data)
    demo_export.storage_key = demo_key
    session.add(
        PromoPlanExportEvent(
            export_id=demo_export.id,
            event_type="created",
            actor="seed",
            payload={"seed": True},
        )
    )
    session.add(
        PromoPlanExportEvent(
            export_id=demo_export.id,
            event_type="approved",
            actor="seed",
        )
    )

    session.commit()
