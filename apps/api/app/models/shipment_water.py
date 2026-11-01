"""On the water: the voyage columns shared by the three shipment tables, and manual port conditions.

``ShipmentWaterColumns`` is mixed into ``ShipmentEvidenceLine``, ``ShipmentEvidenceObservation`` and
``FactInboundShipment``. Every column is nullable. ``port_eta_date`` is the vessel's estimated port arrival
and is not ``eta_date`` (a coalesced delivery date on the fact), so the two are never confused.
``container_no`` stays empty until a forwarder supplies an ISO 6346 number: the 5-digit ``Container Number``
in the ACZA reports is an internal number and is not mapped to it.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Column names in one place for the migration, the mapping layer, the writers and the backfill.
WATER_DATE_FIELDS: tuple[str, ...] = ("on_board_date", "port_eta_date", "port_ata_date")
WATER_TEXT_FIELDS: tuple[str, ...] = (
    "shipping_method",
    "forwarder_code",
    "origin_hub",
    "ship_way",
    "deliver_port",
    "vessel_name",
    "voyage_no",
    "bill_of_lading_no",
    "container_no",
)
WATER_FIELDS: tuple[str, ...] = WATER_DATE_FIELDS + WATER_TEXT_FIELDS
# Width of each text column (the migration reads these too, so the two cannot drift).
WATER_TEXT_WIDTH: dict[str, int] = {
    "shipping_method": 256,
    "forwarder_code": 64,
    "origin_hub": 64,
    "ship_way": 64,
    "deliver_port": 32,
    "vessel_name": 128,
    "voyage_no": 64,
    "bill_of_lading_no": 64,
    "container_no": 64,
}


class ShipmentWaterColumns:
    on_board_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    port_eta_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    port_ata_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    shipping_method: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["shipping_method"]), nullable=True)
    forwarder_code: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["forwarder_code"]), nullable=True)
    origin_hub: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["origin_hub"]), nullable=True)
    ship_way: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["ship_way"]), nullable=True)
    deliver_port: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["deliver_port"]), nullable=True)

    vessel_name: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["vessel_name"]), nullable=True)
    voyage_no: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["voyage_no"]), nullable=True)
    bill_of_lading_no: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["bill_of_lading_no"]), nullable=True)
    container_no: Mapped[str | None] = mapped_column(String(WATER_TEXT_WIDTH["container_no"]), nullable=True)


class PortCondition(Base):
    """A manually entered port delay. Append-only: the newest row per tenant and port is current.

    There is no UPDATE or DELETE policy (see migration 20261101_0049), so a correction is a new row.
    No licensed port-delay feed is wired (D4); ``entered_by`` and ``entered_at`` say who said so and when.
    """

    __tablename__ = "port_condition"
    __table_args__ = (Index("ix_port_condition_current", "tenant_id", "port_code", "entered_at", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="default", server_default="default")
    port_code: Mapped[str] = mapped_column(String(16), nullable=False)
    delay_days: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by: Mapped[str] = mapped_column(String(256), nullable=False)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
