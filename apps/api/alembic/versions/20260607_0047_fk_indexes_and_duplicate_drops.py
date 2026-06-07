"""Add covering indexes for unindexed foreign keys; drop proven duplicate indexes.

Phase A (additive): CREATE INDEX CONCURRENTLY for single-column FK columns lacking a
covering index (Supabase advisor / pg_catalog discovery 2026-06-07).

Phase B (dedup): Drop non-canonical duplicates where migration chain already created
the canonical ix_<table>_<col> index:
  KEEP ix_cst_staging_job (20260518_0045); DROP ix_import_customer_sellthrough_staging_line_import_job_id
  KEEP ix_shipment_evidence_line_import_job (20260507_0030); DROP ix_shipment_evidence_line_import_job_id

CONCURRENTLY ops run inside autocommit_block (not in Alembic transaction).

Revision ID: 20260607_0047
Revises: 20260601_0046
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260607_0047"
down_revision: Union[str, Sequence[str], None] = "20260601_0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, index_name) — discovered unindexed single-column FKs
FK_INDEX_SPECS: tuple[tuple[str, str, str], ...] = (
    ('import_distributor_si_staging_line', 'resolved_customer_id', 'ix_import_distributor_si_staging_line_resolved_customer_id'),
    ('import_distributor_si_staging_line', 'resolved_product_id', 'ix_import_distributor_si_staging_line_resolved_product_id'),
    ('import_distributor_si_staging_line', 'resolved_distributor_id', 'ix_import_distributor_si_staging_line_resolved_distributor_id'),
    ('shipment_evidence_line', 'distributor_id', 'ix_shipment_evidence_line_distributor_id'),
    ('shipment_evidence_line', 'product_id', 'ix_shipment_evidence_line_product_id'),
    ('shipment_evidence_line', 'customer_id', 'ix_shipment_evidence_line_customer_id'),
    ('fact_inbound_shipment', 'product_id', 'ix_fact_inbound_shipment_product_id'),
    ('fact_inbound_shipment', 'distributor_id', 'ix_fact_inbound_shipment_distributor_id'),
    ('fact_inbound_shipment', 'customer_id', 'ix_fact_inbound_shipment_customer_id'),
    ('fact_inbound_shipment', 'shipment_evidence_line_id', 'ix_fact_inbound_shipment_shipment_evidence_line_id'),
    ('import_entity_mapping_candidate', 'source_definition_id', 'ix_import_entity_mapping_candidate_source_definition_id'),
    ('catalog_product', 'canonical_product_id', 'ix_catalog_product_canonical_product_id'),
    ('catalog_product', 'catalog_id', 'ix_catalog_product_catalog_id'),
    ('catalog_product', 'last_import_job_id', 'ix_catalog_product_last_import_job_id'),
    ('import_job', 'source_id', 'ix_import_job_source_id'),
    ('customer_source_token_alias', 'customer_id', 'ix_customer_source_token_alias_customer_id'),
    ('customer_source_token_alias', 'source_definition_id', 'ix_customer_source_token_alias_source_definition_id'),
    ('customer_source_token_alias', 'distributor_id', 'ix_customer_source_token_alias_distributor_id'),
    ('customer_source_token_alias', 'created_from_import_job_id', 'ix_customer_source_token_alias_created_from_import_job_id'),
    ('customer_source_token_alias', 'import_entity_mapping_candidate_id', 'ix_csta_import_entity_mapping_candidate_id'),
    ('dim_customer', 'region_id', 'ix_dim_customer_region_id'),
    ('dim_customer', 'preferred_distributor_id', 'ix_dim_customer_preferred_distributor_id'),
    ('dim_customer', 'channel_id', 'ix_dim_customer_channel_id'),
    ('import_row_result', 'job_id', 'ix_import_row_result_job_id'),
    ('attribute_definition', 'catalog_id', 'ix_attribute_definition_catalog_id'),
    ('distributor_source_token_alias', 'source_definition_id', 'ix_distributor_source_token_alias_source_definition_id'),
    ('distributor_source_token_alias', 'created_from_import_job_id', 'ix_distributor_source_token_alias_created_from_import_job_id'),
    ('distributor_source_token_alias', 'distributor_id', 'ix_distributor_source_token_alias_distributor_id'),
    ('source_definition', 'product_catalog_id', 'ix_source_definition_product_catalog_id'),
    ('source_definition', 'import_template_id', 'ix_source_definition_import_template_id'),
    ('channel_source_token_alias', 'source_definition_id', 'ix_channel_source_token_alias_source_definition_id'),
    ('channel_source_token_alias', 'created_from_import_job_id', 'ix_channel_source_token_alias_created_from_import_job_id'),
    ('channel_source_token_alias', 'channel_id', 'ix_channel_source_token_alias_channel_id'),
    ('raw_file_metadata', 'job_id', 'ix_raw_file_metadata_job_id'),
    ('region_source_token_alias', 'source_definition_id', 'ix_region_source_token_alias_source_definition_id'),
    ('region_source_token_alias', 'created_from_import_job_id', 'ix_region_source_token_alias_created_from_import_job_id'),
    ('region_source_token_alias', 'region_id', 'ix_region_source_token_alias_region_id'),
    ('fact_forecast', 'customer_id', 'ix_fact_forecast_customer_id'),
    ('fact_buy_plan', 'product_id', 'ix_fact_buy_plan_product_id'),
    ('fact_buy_plan', 'distributor_id', 'ix_fact_buy_plan_distributor_id'),
    ('fact_competitor_mapping', 'product_id', 'ix_fact_competitor_mapping_product_id'),
    ('fact_competitor_mapping', 'competitor_product_id', 'ix_fact_competitor_mapping_competitor_product_id'),
    ('fact_product_roadmap', 'product_id', 'ix_fact_product_roadmap_product_id'),
    ('fact_product_roadmap', 'replacement_candidate_id', 'ix_fact_product_roadmap_replacement_candidate_id'),
    ('product_alias', 'product_id', 'ix_product_alias_product_id'),
    ('commercial_plan_line', 'commercial_plan_id', 'ix_commercial_plan_line_commercial_plan_id'),
    ('commercial_plan_line', 'customer_id', 'ix_commercial_plan_line_customer_id'),
    ('commercial_plan_line', 'distributor_id', 'ix_commercial_plan_line_distributor_id'),
    ('commercial_plan_line', 'product_id', 'ix_commercial_plan_line_product_id'),
    ('buy_recommendation', 'product_id', 'ix_buy_recommendation_product_id'),
    ('buy_recommendation', 'buy_plan_id', 'ix_buy_recommendation_buy_plan_id'),
    ('lineup_gap_analysis', 'roadmap_id', 'ix_lineup_gap_analysis_roadmap_id'),
    ('roadmap_recommendation', 'roadmap_id', 'ix_roadmap_recommendation_roadmap_id'),
    ('fact_budget_request', 'owner_id', 'ix_fact_budget_request_owner_id'),
    ('fact_budget_request', 'linked_product_id', 'ix_fact_budget_request_linked_product_id'),
    ('fact_budget_request', 'linked_customer_id', 'ix_fact_budget_request_linked_customer_id'),
    ('fact_budget_request', 'linked_promotion_id', 'ix_fact_budget_request_linked_promotion_id'),
    ('fact_budget_request', 'linked_roadmap_id', 'ix_fact_budget_request_linked_roadmap_id'),
    ('budget_justification_summary', 'budget_request_id', 'ix_budget_justification_summary_budget_request_id'),
    ('fact_lineup_plan_item', 'customer_id', 'ix_fact_lineup_plan_item_customer_id'),
    ('fact_lineup_plan_item', 'channel_id', 'ix_fact_lineup_plan_item_channel_id'),
    ('fact_lineup_plan_item', 'product_id', 'ix_fact_lineup_plan_item_product_id'),
    ('fact_lineup_plan_item', 'predecessor_product_id', 'ix_fact_lineup_plan_item_predecessor_product_id'),
    ('fact_lineup_plan_item', 'successor_product_id', 'ix_fact_lineup_plan_item_successor_product_id'),
    ('fact_lineup_plan_item', 'link_buy_plan_id', 'ix_fact_lineup_plan_item_link_buy_plan_id'),
    ('fact_lineup_plan_item', 'link_pricing_id', 'ix_fact_lineup_plan_item_link_pricing_id'),
    ('fact_lineup_plan_item', 'link_promotion_id', 'ix_fact_lineup_plan_item_link_promotion_id'),
    ('fact_lineup_plan_item', 'link_budget_request_id', 'ix_fact_lineup_plan_item_link_budget_request_id'),
    ('fact_lineup_plan_item', 'link_roadmap_id', 'ix_fact_lineup_plan_item_link_roadmap_id'),
    ('fact_customer_velocity', 'product_id', 'ix_fact_customer_velocity_product_id'),
    ('fact_customer_velocity', 'customer_id', 'ix_fact_customer_velocity_customer_id'),
    ('fact_customer_velocity', 'import_job_id', 'ix_fact_customer_velocity_import_job_id'),
    ('fact_dsi_forecast', 'product_id', 'ix_fact_dsi_forecast_product_id'),
    ('fact_dsi_forecast', 'distributor_id', 'ix_fact_dsi_forecast_distributor_id'),
    ('fact_dsi_forecast', 'import_job_id', 'ix_fact_dsi_forecast_import_job_id'),
    ('fact_inventory_distributor', 'product_id', 'ix_fact_inventory_distributor_product_id'),
    ('fact_inventory_distributor', 'distributor_id', 'ix_fact_inventory_distributor_distributor_id'),
    ('fact_inventory_distributor', 'source_import_job_id', 'ix_fact_inventory_distributor_source_import_job_id'),
    ('fact_inventory_reconciliation', 'product_id', 'ix_fact_inventory_reconciliation_product_id'),
    ('fact_inventory_reconciliation', 'customer_id', 'ix_fact_inventory_reconciliation_customer_id'),
    ('fact_inventory_reconciliation', 'distributor_id', 'ix_fact_inventory_reconciliation_distributor_id'),
    ('fact_inventory_reconciliation', 'import_job_id', 'ix_fact_inventory_reconciliation_import_job_id'),
    ('fact_competitor_price', 'competitor_product_id', 'ix_fact_competitor_price_competitor_product_id'),
    ('fact_competitor_price', 'source_job_id', 'ix_fact_competitor_price_source_job_id'),
    ('entity_mapping_queue', 'job_id', 'ix_entity_mapping_queue_job_id'),
    ('lineup_plan_item_event', 'lineup_item_id', 'ix_lineup_plan_item_event_lineup_item_id'),
    ('import_customer_sellthrough_staging_line', 'resolved_customer_id', 'ix_import_cst_staging_line_resolved_customer_id'),
    ('import_customer_sellthrough_staging_line', 'resolved_location_id', 'ix_import_cst_staging_line_resolved_location_id'),
    ('import_customer_sellthrough_staging_line', 'resolved_product_id', 'ix_import_customer_sellthrough_staging_line_resolved_product_id'),
    ('import_customer_sellthrough_staging_line', 'fact_sellthrough_row_id', 'ix_import_cst_staging_line_fact_sellthrough_row_id'),
    ('fact_sales_sellout', 'staging_line_id', 'ix_fact_sales_sellout_staging_line_id'),
    ('fact_sales_sellout', 'product_id', 'ix_fact_sales_sellout_product_id'),
    ('fact_sales_sellout', 'customer_id', 'ix_fact_sales_sellout_customer_id'),
    ('fact_sales_sellout', 'channel_id', 'ix_fact_sales_sellout_channel_id'),
    ('fact_sales_sellout', 'distributor_id', 'ix_fact_sales_sellout_distributor_id'),
    ('fact_sales_sellout', 'source_import_job_id', 'ix_fact_sales_sellout_source_import_job_id'),
    ('fact_returns', 'staging_line_id', 'ix_fact_returns_staging_line_id'),
    ('fact_returns', 'distributor_id', 'ix_fact_returns_distributor_id'),
    ('fact_returns', 'product_id', 'ix_fact_returns_product_id'),
    ('fact_returns', 'customer_id', 'ix_fact_returns_customer_id'),
    ('budget_health', 'owner_id', 'ix_budget_health_owner_id'),
    ('product_attribute_value', 'attribute_definition_id', 'ix_product_attribute_value_attribute_definition_id'),
    ('product_attribute_value', 'catalog_product_id', 'ix_product_attribute_value_catalog_product_id'),
    ('product_catalog', 'business_unit_id', 'ix_product_catalog_business_unit_id'),
    ('fact_customer_sellthrough', 'customer_id', 'ix_fact_customer_sellthrough_customer_id'),
    ('fact_customer_sellthrough', 'customer_location_id', 'ix_fact_customer_sellthrough_customer_location_id'),
    ('fact_customer_sellthrough', 'product_id', 'ix_fact_customer_sellthrough_product_id'),
    ('historical_lineup_import_header', 'channel_id', 'ix_historical_lineup_import_header_channel_id'),
    ('historical_lineup_import_header', 'customer_id', 'ix_historical_lineup_import_header_customer_id'),
    ('historical_lineup_import_header', 'distributor_id', 'ix_historical_lineup_import_header_distributor_id'),
    ('historical_lineup_import_line', 'product_id', 'ix_historical_lineup_import_line_product_id'),
    ('dim_competitor_product', 'brand_id', 'ix_dim_competitor_product_brand_id'),
    ('promo_plan_export', 'promotion_id', 'ix_promo_plan_export_promotion_id'),
    ('fact_budget_allocation', 'owner_id', 'ix_fact_budget_allocation_owner_id'),
    ('fact_budget_commitment', 'owner_id', 'ix_fact_budget_commitment_owner_id'),
    ('fact_budget_actual', 'owner_id', 'ix_fact_budget_actual_owner_id'),
    ('stock_health', 'product_id', 'ix_stock_health_product_id'),
    ('stock_health', 'customer_id', 'ix_stock_health_customer_id'),
    ('weeks_of_stock', 'product_id', 'ix_weeks_of_stock_product_id'),
    ('weeks_of_stock', 'customer_id', 'ix_weeks_of_stock_customer_id'),
    ('stock_risk', 'product_id', 'ix_stock_risk_product_id'),
    ('stock_risk', 'customer_id', 'ix_stock_risk_customer_id'),
    ('forecast_summary', 'product_id', 'ix_forecast_summary_product_id'),
    ('pricing_recommendation', 'product_id', 'ix_pricing_recommendation_product_id'),
    ('promo_readiness', 'promotion_id', 'ix_promo_readiness_promotion_id'),
    ('promo_readiness', 'product_id', 'ix_promo_readiness_product_id'),
    ('competitive_positioning', 'product_id', 'ix_competitive_positioning_product_id'),
    ('competitive_positioning', 'competitor_product_id', 'ix_competitive_positioning_competitor_product_id'),
    ('exception_inbox_item', 'product_id', 'ix_exception_inbox_item_product_id'),
    ('customer_location', 'region_id', 'ix_customer_location_region_id'),
    ('promo_plan_export_event', 'export_id', 'ix_promo_plan_export_event_export_id'),
    ('fact_sales_sellin', 'product_id', 'ix_fact_sales_sellin_product_id'),
    ('fact_sales_sellin', 'distributor_id', 'ix_fact_sales_sellin_distributor_id'),
    ('fact_inventory_customer', 'product_id', 'ix_fact_inventory_customer_product_id'),
    ('fact_inventory_customer', 'customer_id', 'ix_fact_inventory_customer_customer_id'),
    ('fact_pricing', 'product_id', 'ix_fact_pricing_product_id'),
    ('fact_pricing', 'customer_id', 'ix_fact_pricing_customer_id'),
    ('fact_pricing', 'channel_id', 'ix_fact_pricing_channel_id'),
    ('fact_support', 'product_id', 'ix_fact_support_product_id'),
    ('fact_promotion_plan', 'promotion_id', 'ix_fact_promotion_plan_promotion_id'),
    ('fact_promotion_plan', 'product_id', 'ix_fact_promotion_plan_product_id'),
    ('fact_promotion_performance', 'promotion_id', 'ix_fact_promotion_performance_promotion_id'),
    ('fact_promotion_performance', 'product_id', 'ix_fact_promotion_performance_product_id'),
    ('fact_activation', 'product_id', 'ix_fact_activation_product_id'),
    ('fact_activation', 'channel_id', 'ix_fact_activation_channel_id'),
    ('fact_forecast', 'product_id', 'ix_fact_forecast_product_id'),
)

# Non-canonical duplicate indexes (not created by Alembic chain)
DUPLICATE_DROP_INDEXES: tuple[str, ...] = (
    'ix_import_customer_sellthrough_staging_line_import_job_id',
    'ix_shipment_evidence_line_import_job_id',
)

# (index_name, table, column) — restore on downgrade
DUPLICATE_RESTORE_SPECS: tuple[tuple[str, str, str], ...] = (
    ('ix_import_customer_sellthrough_staging_line_import_job_id', 'import_customer_sellthrough_staging_line', 'import_job_id'),
    ('ix_shipment_evidence_line_import_job_id', 'shipment_evidence_line', 'import_job_id'),
)


def _create_fk_indexes() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        for table, column, index_name in FK_INDEX_SPECS:
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}" '
                f'ON "{table}" ("{column}")'
            )


def _drop_fk_indexes() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        for _table, _column, index_name in FK_INDEX_SPECS:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"')


def _drop_duplicate_indexes() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        for index_name in DUPLICATE_DROP_INDEXES:
            op.execute(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"')


def _restore_duplicate_indexes() -> None:
    ctx = op.get_context()
    with ctx.autocommit_block():
        for index_name, table, column in DUPLICATE_RESTORE_SPECS:
            op.execute(
                f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}" '
                f'ON "{table}" ("{column}")'
            )


def upgrade() -> None:
    _create_fk_indexes()
    _drop_duplicate_indexes()


def downgrade() -> None:
    _restore_duplicate_indexes()
    _drop_fk_indexes()
