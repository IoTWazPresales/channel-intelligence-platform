"""Query/response models for paginated shipment evidence mapping candidate listing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ShipmentCandidateEntityFilter = Literal["all", "customer", "distributor"]
ShipmentCandidatePartyFilter = Literal["all", "bill_to", "ship_to"]
ShipmentCandidateStatusFilter = Literal["all", "open", "needs_review", "terminal"]


class ShipmentMappingCandidatesListParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    entity: ShipmentCandidateEntityFilter = "all"
    party: ShipmentCandidatePartyFilter = "all"
    verify_name_only: bool = False
    special_category_only: bool = False
    possible_duplicates_only: bool = False
    duplicate_unresolved_only: bool = False
    status: ShipmentCandidateStatusFilter = "open"


class ShipmentMappingCandidateItem(BaseModel):
    id: int
    import_job_id: int
    source_definition_id: int | None
    entity_type: str
    normalized_key: str
    dealer_group_token: str | None
    row_count: int
    total_units: float | None
    total_reported_value: float | None
    sample_raw_values: list[str] | None
    suggested_entity_id: int | None
    suggested_distributor_code: str | None = None
    suggested_distributor_name: str | None = None
    suggested_customer_code: str | None = None
    suggested_customer_name: str | None = None
    suggested_action: str | None = None
    match_reason: str | None
    confidence_score: float | None
    status: str
    context: dict[str, Any] | None
    created_at: str | None
    updated_at: str | None


class ShipmentMappingCandidatesPageResponse(BaseModel):
    items: list[ShipmentMappingCandidateItem]
    total: int
    skip: int
    limit: int


class ShipmentEntityTabCountPair(BaseModel):
    open: int = 0
    needs_work: int = 0
    needs_review: int = 0


class ShipmentMappingCandidatesTabCountsResponse(BaseModel):
    import_job_id: int
    counts: dict[str, ShipmentEntityTabCountPair]
