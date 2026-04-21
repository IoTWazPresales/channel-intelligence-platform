from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.product_catalog import ProductCatalog


class ImportTemplate(Base, TimestampMixin):
    """First-class import type (product master, distributor inventory, …).

    `SourceDefinition` rows are provider/feed instances bound to one template.
    """

    __tablename__ = "import_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    admin_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requires_provider: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pipeline_handler: Mapped[str] = mapped_column(String(64), nullable=False)
    destructive_apply_requires_confirm: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepted_file_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    expected_columns: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    sources: Mapped[list["SourceDefinition"]] = relationship(back_populates="import_template")


class SourceDefinition(Base, TimestampMixin):
    __tablename__ = "source_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    import_template_id: Mapped[int] = mapped_column(ForeignKey("import_template.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_template: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Product Master: learned header_norm → target/disposition from prior confirmed saves (source-scoped).
    column_mapping_memory: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    parser_module: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # When set, product imports for this source are materialized into this catalog (see `product_catalog`).
    product_catalog_id: Mapped[int | None] = mapped_column(ForeignKey("product_catalog.id"), nullable=True)

    import_template: Mapped["ImportTemplate"] = relationship(back_populates="sources")
    product_catalog: Mapped["ProductCatalog | None"] = relationship("ProductCatalog", back_populates="sources")


class ImportJob(Base, TimestampMixin):
    __tablename__ = "import_job"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_definition.id"), nullable=False)
    template_slug: Mapped[str | None] = mapped_column(String(64), nullable=True)
    import_mode: Mapped[str] = mapped_column(String(32), default="apply", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    stage: Mapped[str] = mapped_column(String(64), default="uploaded", nullable=False)
    file_name: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    inferred_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    field_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    file_headers: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    mapping_decisions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    staged_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Product Master async commit: { "phase", "queued_at", "started_at", "celery_task_id", ... }
    pm_commit_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped["SourceDefinition"] = relationship()
    raw_files: Mapped[list["RawFileMetadata"]] = relationship(back_populates="job")
    row_results: Mapped[list["ImportRowResult"]] = relationship(back_populates="job")


class RawFileMetadata(Base, TimestampMixin):
    __tablename__ = "raw_file_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_job.id"), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)

    job: Mapped["ImportJob"] = relationship(back_populates="raw_files")


class ImportRowResult(Base, TimestampMixin):
    __tablename__ = "import_row_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("import_job.id"), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    job: Mapped["ImportJob"] = relationship(back_populates="row_results")
