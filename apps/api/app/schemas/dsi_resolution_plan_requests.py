"""Pydantic request bodies for DSI resolution plan endpoints (kept separate from FastAPI routes to avoid heavy DB driver imports in lightweight tests)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DsiResolutionPlanGenerateBody(BaseModel):
    candidate_ids: list[int] | None = Field(default=None, max_length=500)
    default_region_id: int | None = Field(default=None, ge=1)
    default_channel_id: int | None = Field(default=None, ge=1)


DsiResolutionPlanOverrideAction = Literal[
    "ignore",
    "map_distributor",
    "create_provisional_distributor",
    "map_customer",
    "create_provisional_customer",
    "resolve_product",
]


class DsiResolutionPlanRowOverrideBody(BaseModel):
    candidate_id: int = Field(..., ge=1)
    action: DsiResolutionPlanOverrideAction | None = None
    target_id: int | None = Field(default=None, ge=1)
    region_id: int | None = Field(default=None, ge=1)
    channel_id: int | None = Field(default=None, ge=1)
    hold_for_manual_review: bool = False
    ack_strategic_channel_hint: bool = False
    confirm_for_suspicious_distributor_token: bool = False
    confirm_ineligible_product: bool = False
    audit_note: str | None = Field(default=None, max_length=2000)


class DsiResolutionPlanApplyBody(BaseModel):
    candidate_ids: list[int] = Field(..., min_length=1, max_length=500)
    default_region_id: int | None = Field(default=None, ge=1)
    default_channel_id: int | None = Field(default=None, ge=1)
    partner_tier: str | None = Field(default="unmanaged", max_length=32)
    provisional_notes_summary: str | None = Field(default=None, max_length=512)
    confirm_for_suspicious_distributor_token: bool = False
    overrides: list[DsiResolutionPlanRowOverrideBody] | None = Field(default=None, max_length=500)


class DsiResolutionPlanEffectiveBody(BaseModel):
    candidate_ids: list[int] | None = Field(default=None, max_length=500)
    default_region_id: int | None = Field(default=None, ge=1)
    default_channel_id: int | None = Field(default=None, ge=1)
    confirm_for_suspicious_distributor_token: bool = False
    overrides: list[DsiResolutionPlanRowOverrideBody] = Field(default_factory=list, max_length=500)
