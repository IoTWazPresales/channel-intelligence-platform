"""Bulk steward mutations for DSI unresolved region/channel file tokens."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.services.imports.dsi_steward_candidate_ops import StewardOpError
from app.services.imports.dsi_steward_geo_catalog import (
    create_dim_channel_with_source_alias_sync,
    create_dim_region_with_source_alias_sync,
    register_region_from_geographic_hint_sync,
    suggest_geo_create_prefill_sync,
)

GeoStewardBulkAction = Literal["register_region_from_hint", "register_from_file"]


def apply_dsi_geo_steward_bulk_sync(
    sess: Session,
    *,
    import_job_id: int,
    action: GeoStewardBulkAction,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply geo steward ops to many file tokens in one transaction (per-item errors collected)."""
    if not items:
        raise StewardOpError("items must not be empty", status_code=400)
    if len(items) > 500:
        raise StewardOpError("items exceeds maximum of 500 per bulk request", status_code=400)

    results: list[dict[str, Any]] = []
    applied = 0
    failed = 0

    for item in items:
        kind = str(item.get("kind") or "").strip().lower()
        raw_token = str(item.get("raw_token") or "").strip()
        normalized_token = item.get("normalized_token")
        row_key = f"{kind}:{raw_token}"

        try:
            if not raw_token:
                raise StewardOpError("raw_token is required", status_code=400)

            if action == "register_region_from_hint":
                if kind != "channel":
                    raise StewardOpError(
                        "register_region_from_hint applies to channel file tokens only",
                        status_code=400,
                    )
                out = register_region_from_geographic_hint_sync(
                    sess,
                    import_job_id=int(import_job_id),
                    raw_token=raw_token,
                    iso_alpha2=item.get("iso_alpha2"),
                    notes=item.get("notes"),
                )
            elif action == "register_from_file":
                if kind not in ("channel", "region"):
                    raise StewardOpError("kind must be channel or region", status_code=400)
                pre = suggest_geo_create_prefill_sync(
                    raw_token=raw_token,
                    dimension=kind,
                    normalized_token=str(normalized_token) if normalized_token else None,
                )
                code = str(item.get("code") or pre["code"]).strip()
                name = str(item.get("name") or pre["name"]).strip()
                if kind == "channel":
                    out = create_dim_channel_with_source_alias_sync(
                        sess,
                        import_job_id=int(import_job_id),
                        channel_code=code,
                        channel_name=name,
                        raw_token=raw_token,
                        notes=item.get("notes"),
                    )
                else:
                    out = create_dim_region_with_source_alias_sync(
                        sess,
                        import_job_id=int(import_job_id),
                        region_code=code,
                        region_name=name,
                        raw_token=raw_token,
                        notes=item.get("notes"),
                    )
            else:
                raise StewardOpError(f"unknown action: {action}", status_code=400)

            applied += 1
            results.append(
                {
                    "ok": True,
                    "kind": kind,
                    "raw_token": raw_token,
                    "row_key": row_key,
                    **{k: v for k, v in out.items() if k != "ok"},
                }
            )
        except StewardOpError as exc:
            failed += 1
            results.append(
                {
                    "ok": False,
                    "kind": kind or None,
                    "raw_token": raw_token or None,
                    "row_key": row_key,
                    "error": exc.detail,
                    "status_code": exc.status_code,
                }
            )

    return {
        "import_job_id": int(import_job_id),
        "action": action,
        "applied": applied,
        "failed": failed,
        "results": results,
    }
