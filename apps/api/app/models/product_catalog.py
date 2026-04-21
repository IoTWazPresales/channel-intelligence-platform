"""Multi-catalog product model: business units, catalogs, catalog products, and EAV attributes.

`DimProduct` (dim_product) remains the **canonical** platform product record. `CatalogProduct` holds
per-catalog / per-source views that link to a canonical row when matched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class BusinessUnit(Base, TimestampMixin):
    """Organizational owner (division, region P&L, etc.); not a full org chart yet."""

    __tablename__ = "business_unit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)

    catalogs: Mapped[list["ProductCatalog"]] = relationship(back_populates="business_unit")


class ProductCatalog(Base, TimestampMixin):
    """A named product dataset (e.g. “US retail master”, “Distributor A feed”, “BU X assortment”)."""

    __tablename__ = "product_catalog"
    __table_args__ = (UniqueConstraint("business_unit_id", "code", name="uq_product_catalog_bu_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_unit_id: Mapped[int] = mapped_column(ForeignKey("business_unit.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business_unit: Mapped["BusinessUnit"] = relationship(back_populates="catalogs")
    catalog_products: Mapped[list["CatalogProduct"]] = relationship(back_populates="catalog")
    sources: Mapped[list["SourceDefinition"]] = relationship("SourceDefinition", back_populates="product_catalog")


class CatalogProduct(Base, TimestampMixin):
    """Per-catalog product row: source identifiers + link to canonical `dim_product` when resolved."""

    __tablename__ = "catalog_product"
    __table_args__ = (UniqueConstraint("catalog_id", "source_sku", name="uq_catalog_product_catalog_sku"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_id: Mapped[int] = mapped_column(ForeignKey("product_catalog.id"), nullable=False)
    source_sku: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    canonical_product_id: Mapped[int | None] = mapped_column(ForeignKey("dim_product.id"), nullable=True)
    source_metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    last_import_job_id: Mapped[int | None] = mapped_column(ForeignKey("import_job.id"), nullable=True)

    catalog: Mapped["ProductCatalog"] = relationship(back_populates="catalog_products")
    canonical_product: Mapped["DimProduct | None"] = relationship("DimProduct", foreign_keys="CatalogProduct.canonical_product_id")
    last_import_job: Mapped["ImportJob | None"] = relationship("ImportJob", foreign_keys="CatalogProduct.last_import_job_id")
    attribute_values: Mapped[list["ProductAttributeValue"]] = relationship(back_populates="catalog_product")


class AttributeDefinition(Base, TimestampMixin):
    """Defines an attribute: unique `namespace` encodes scope (global vs catalog vs category bucket).

    Examples: `global:wattage`, `catalog:{id}:voltage`, `catalog:{id}:cat:gpu:memory_gb`.
    Optional `catalog_id` denormalized for filtering; source of truth is `namespace`.
    """

    __tablename__ = "attribute_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    namespace: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    catalog_id: Mapped[int | None] = mapped_column(ForeignKey("product_catalog.id"), nullable=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # data_type: string | number | boolean | date | json

    catalog: Mapped["ProductCatalog | None"] = relationship()
    values: Mapped[list["ProductAttributeValue"]] = relationship(back_populates="attribute_definition")


class ProductAttributeValue(Base, TimestampMixin):
    """Typed attribute storage for a catalog-scoped product row (EAV)."""

    __tablename__ = "product_attribute_value"
    __table_args__ = (
        UniqueConstraint("catalog_product_id", "attribute_definition_id", name="uq_pav_catalog_product_attr"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_product_id: Mapped[int] = mapped_column(ForeignKey("catalog_product.id"), nullable=False)
    attribute_definition_id: Mapped[int] = mapped_column(ForeignKey("attribute_definition.id"), nullable=False)
    value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONB, nullable=False)

    catalog_product: Mapped["CatalogProduct"] = relationship(back_populates="attribute_values")
    attribute_definition: Mapped["AttributeDefinition"] = relationship(back_populates="values")


if TYPE_CHECKING:
    from app.models.dimensions import DimProduct
    from app.models.ingestion import ImportJob, SourceDefinition
