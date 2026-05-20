"""Staging, mapping candidates, and customer token aliases for distributor sales & inventory imports."""

from __future__ import annotations

from datetime import date

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ImportDistributorSiStagingLine(Base, TimestampMixin):
    """One source row of a distributor sales & inventory import before / after fact apply."""

    __tablename__ = "import_distributor_si_staging_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False, index=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_row_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    mapped_canonical: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    raw_distributor_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_customer_dealer_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_dealer_group_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    raw_product_token: Mapped[str | None] = mapped_column(String(512), nullable=True)

    resolved_distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True)
    resolved_customer_id: Mapped[int | None] = mapped_column(ForeignKey("dim_customer.id"), nullable=True)
    resolved_product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)

    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    snapshot_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    quantity_sold: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    stock_on_hand: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    unit_sellout_price_ex_tax_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    reported_revenue_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    computed_revenue_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)

    resolution_status: Mapped[str] = mapped_column(String(64), default="pending", nullable=False)
    diagnostic_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="info", nullable=False)
    apply_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)

    fact_sellout_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fact_inventory_row_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ImportEntityMappingCandidate(Base, TimestampMixin):
    """Aggregated unresolved entity tokens for an import job (not one queue row per source row)."""

    __tablename__ = "import_entity_mapping_candidate"
    __table_args__ = (
        UniqueConstraint(
            "import_job_id",
            "entity_type",
            "normalized_key",
            name="uq_import_entity_mapping_candidate_job_entity_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_job.id", ondelete="CASCADE"), nullable=False, index=True)
    source_definition_id: Mapped[int | None] = mapped_column(ForeignKey("source_definition.id"), nullable=True)

    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_key: Mapped[str] = mapped_column(String(512), nullable=False)
    dealer_group_token: Mapped[str | None] = mapped_column(String(512), nullable=True)

    row_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_units: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    total_reported_value: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    sample_raw_values: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    suggested_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="needs_review", nullable=False)
    context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CustomerSourceTokenAlias(Base, TimestampMixin):
    """Approved mapping from a raw distributor-reported customer/dealer token to dim_customer."""

    __tablename__ = "customer_source_token_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("dim_customer.id", ondelete="CASCADE"), nullable=False)
    source_definition_id: Mapped[int | None] = mapped_column(ForeignKey("source_definition.id"), nullable=True)
    distributor_id: Mapped[int | None] = mapped_column(ForeignKey("dim_distributor.id"), nullable=True)

    raw_token: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_token: Mapped[str] = mapped_column(String(512), nullable=False)
    dealer_group_token: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
    import_entity_mapping_candidate_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_entity_mapping_candidate.id", ondelete="SET NULL"), nullable=True
    )


class DistributorSourceTokenAlias(Base, TimestampMixin):
    """Steward-approved mapping from a raw distributor-reported token to dim_distributor."""

    __tablename__ = "distributor_source_token_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    distributor_id: Mapped[int] = mapped_column(ForeignKey("dim_distributor.id", ondelete="CASCADE"), nullable=False)
    source_definition_id: Mapped[int | None] = mapped_column(ForeignKey("source_definition.id"), nullable=True)
    raw_token: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_token: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )


class ChannelSourceTokenAlias(Base, TimestampMixin):
    """Steward-approved mapping from a normalized DSI route-to-market / channel token to dim_channel."""

    __tablename__ = "channel_source_token_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("dim_channel.id", ondelete="CASCADE"), nullable=False)
    source_definition_id: Mapped[int | None] = mapped_column(ForeignKey("source_definition.id"), nullable=True)
    raw_token: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_token: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )


class RegionSourceTokenAlias(Base, TimestampMixin):
    """Steward-approved mapping from a normalized DSI region / province token to dim_region."""

    __tablename__ = "region_source_token_alias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    region_id: Mapped[int] = mapped_column(ForeignKey("dim_region.id", ondelete="CASCADE"), nullable=False)
    source_definition_id: Mapped[int | None] = mapped_column(ForeignKey("source_definition.id"), nullable=True)
    raw_token: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_token: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_import_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_job.id", ondelete="SET NULL"), nullable=True
    )
