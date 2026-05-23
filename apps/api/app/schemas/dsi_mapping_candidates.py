"""Query/response models for paginated DSI mapping candidate listing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DsiCandidateEntityFilter = Literal["all", "customer", "distributor", "product"]
DsiCandidatePartyFilter = Literal["all", "bill_to", "ship_to"]
DsiCandidateStatusFilter = Literal["all", "open", "needs_review", "terminal"]


class DsiMappingCandidatesListParams(BaseModel):
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
    entity: DsiCandidateEntityFilter = "all"
    party: DsiCandidatePartyFilter = "all"
    verify_name_only: bool = False
    special_category_only: bool = False
    possible_duplicates_only: bool = False
    duplicate_unresolved_only: bool = False
    status: DsiCandidateStatusFilter = "open"


class DsiMappingCandidateItem(BaseModel):
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
    match_reason: str | None
    confidence_score: float | None
    status: str
    context: dict[str, Any] | None
    created_at: str | None
    updated_at: str | None


class DsiMappingCandidatesPageResponse(BaseModel):
    items: list[DsiMappingCandidateItem]
    total: int
    skip: int
    limit: int
