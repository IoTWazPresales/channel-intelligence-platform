"""Single registry for import-job background-task slots in ``staged_metadata``.

Phase 2 of the Import Flow capability contract (see
``docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md`` §3b). Every importer used to hand-write
its own ``staged_metadata`` task slot, with a parallel reader in ``background_tasks.py``
and inconsistent clearers in three places (one of which forgot most slots, leaving
orphan slots on cancel/retry). This module is the **one** place that defines:

* which slot keys exist (``TASK_SLOTS``),
* how to write one (:func:`set_task_slot_on_job` / :func:`set_task_slot_by_job_id`),
* how to read the active ones for the activity feed (:func:`iter_active_slots`),
* how to clear one or all of them (:func:`clear_task_slot` / :func:`clear_all_task_slots`).

The on-disk JSON shape is preserved byte-for-byte with the previous hand-written
writers, so in-flight jobs and the frontend (which already understands every ``kind``)
are unaffected.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import and_, or_

from app.models.ingestion import ImportJob
from app.utils.json_safe import to_jsonable

# --- Tracking kinds (runtime truth; mirrors the contract doc §3b) --------------

KIND_PRODUCT_MASTER_VALIDATE = "product_master_validate"
KIND_PRODUCT_MASTER_COMMIT = "product_master_commit"
KIND_DSI_PIPELINE = "dsi_pipeline"
KIND_DSI_BULK_PROVISIONAL = "dsi_bulk_provisional"
KIND_DSI_BULK_IGNORE = "dsi_bulk_ignore"
KIND_DSI_RESOLUTION_PLAN_APPLY = "dsi_resolution_plan_apply"
KIND_DSI_RESOLUTION_PLAN_COMPUTE = "dsi_resolution_plan_compute"
KIND_DSI_SOH_RECONCILIATION = "dsi_soh_reconciliation"
KIND_DSI_VELOCITY_COMPUTE = "dsi_velocity_compute"
KIND_DSI_FORECASTING = "dsi_forecasting"
KIND_SHIPMENT_IMPORT = "shipment_import"
KIND_SHIPMENT_BULK = "shipment_bulk"
KIND_COMMERCIAL_PLANNER_LINEUP_PARSE = "commercial_planner_lineup_parse"
KIND_CPOR_HISTORICAL_IMPORT = "cpor_historical_import"

# Allowed resolved kinds for the shared ``dsi_bulk_task`` slot. Anything else (e.g. the
# legacy ``dsi_bulk_provisional_customers`` string still written by the endpoint) is
# normalized to ``dsi_bulk_provisional`` — preserving the prior discovery behavior.
_DSI_BULK_ALLOWED_KINDS = (
    KIND_DSI_BULK_PROVISIONAL,
    KIND_DSI_BULK_IGNORE,
    KIND_DSI_RESOLUTION_PLAN_APPLY,
    KIND_DSI_RESOLUTION_PLAN_COMPUTE,
)


# --- Slot descriptors ----------------------------------------------------------

# kind_resolution values:
FIXED = "fixed"  # one slot key ↔ one kind
FROM_TEMPLATE_SLUG = "from_template_slug"  # kind derived from job.template_slug
FROM_PAYLOAD = "from_payload"  # kind stored inside the slot payload dict

# payload_shape values:
SHAPE_STRING = "string"  # meta[key] is the bare task-id string (the "main" slot)
SHAPE_DICT = "dict"  # meta[key] is a dict carrying task_id + extras

# label_source values:
LABEL_PAYLOAD = "payload"  # use stored label (fallback to default_label)
LABEL_COMPUTED = "computed"  # compute via task_label(job, kind)


@dataclass(frozen=True)
class SlotDescriptor:
    slot_key: str  # logical name used by callers
    meta_key: str  # actual key inside staged_metadata
    kind_resolution: str
    payload_shape: str
    label_source: str
    fixed_kind: str | None = None
    default_label: str | None = None


# Logical slot key "main" maps to the historical ``celery_task_id`` meta key.
SLOT_MAIN = "main"
SLOT_DSI_BULK = "dsi_bulk_task"
SLOT_DSI_SOH = "dsi_soh_reconcile_task"
SLOT_DSI_VELOCITY = "dsi_velocity_compute_task"
SLOT_DSI_FORECASTING = "dsi_forecasting_task"
SLOT_PM_VALIDATE = "pm_validate_task"
SLOT_PM_COMMIT = "pm_commit_task"
SLOT_LINEUP_PARSE = "lineup_parse_task"
SLOT_SHIPMENT_BULK = "shipment_bulk_task"


TASK_SLOTS: tuple[SlotDescriptor, ...] = (
    SlotDescriptor(
        slot_key=SLOT_MAIN,
        meta_key="celery_task_id",
        kind_resolution=FROM_TEMPLATE_SLUG,
        payload_shape=SHAPE_STRING,
        label_source=LABEL_COMPUTED,
    ),
    SlotDescriptor(
        slot_key=SLOT_DSI_BULK,
        meta_key="dsi_bulk_task",
        kind_resolution=FROM_PAYLOAD,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_COMPUTED,
    ),
    SlotDescriptor(
        slot_key=SLOT_DSI_SOH,
        meta_key="dsi_soh_reconcile_task",
        kind_resolution=FIXED,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_PAYLOAD,
        fixed_kind=KIND_DSI_SOH_RECONCILIATION,
        default_label="Reconciling inventory…",
    ),
    SlotDescriptor(
        slot_key=SLOT_DSI_VELOCITY,
        meta_key="dsi_velocity_compute_task",
        kind_resolution=FIXED,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_PAYLOAD,
        fixed_kind=KIND_DSI_VELOCITY_COMPUTE,
        default_label="Computing sell-out velocity…",
    ),
    SlotDescriptor(
        slot_key=SLOT_DSI_FORECASTING,
        meta_key="dsi_forecasting_task",
        kind_resolution=FIXED,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_PAYLOAD,
        fixed_kind=KIND_DSI_FORECASTING,
        default_label="Generating forecasts…",
    ),
    SlotDescriptor(
        slot_key=SLOT_PM_VALIDATE,
        meta_key="pm_validate_task",
        kind_resolution=FIXED,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_PAYLOAD,
        fixed_kind=KIND_PRODUCT_MASTER_VALIDATE,
        default_label="Validating product master…",
    ),
    SlotDescriptor(
        slot_key=SLOT_PM_COMMIT,
        meta_key="pm_commit_task",
        kind_resolution=FIXED,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_PAYLOAD,
        fixed_kind=KIND_PRODUCT_MASTER_COMMIT,
        default_label="Committing product master…",
    ),
    SlotDescriptor(
        slot_key=SLOT_LINEUP_PARSE,
        meta_key="lineup_parse_task",
        kind_resolution=FIXED,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_PAYLOAD,
        fixed_kind=KIND_COMMERCIAL_PLANNER_LINEUP_PARSE,
        default_label="Parsing current lineup…",
    ),
    SlotDescriptor(
        slot_key=SLOT_SHIPMENT_BULK,
        meta_key="shipment_bulk_task",
        kind_resolution=FIXED,
        payload_shape=SHAPE_DICT,
        label_source=LABEL_PAYLOAD,
        fixed_kind=KIND_SHIPMENT_BULK,
        default_label="Applying shipment steward bulk action…",
    ),
)

_SLOTS_BY_KEY: dict[str, SlotDescriptor] = {s.slot_key: s for s in TASK_SLOTS}
_TASK_META_KEYS: tuple[str, ...] = tuple(s.meta_key for s in TASK_SLOTS)

# Non-slot background-timing keys cleared alongside slots on cancel/retry.
_PIPELINE_TIMING_KEYS = ("pipeline_queued_at", "pipeline_started_at", "pipeline_dispatch_claim")


def slot_meta_keys() -> tuple[str, ...]:
    """All staged_metadata keys that hold a background-task slot."""
    return _TASK_META_KEYS


# --- Label / kind resolution ---------------------------------------------------


def task_label(job: ImportJob, *, kind: str) -> str:
    """Human label for an active background task (moved here from background_tasks)."""
    jid = int(job.id)
    slug = (job.template_slug or "").strip()
    mode = (job.import_mode or "").strip().lower()
    if kind == KIND_DSI_BULK_PROVISIONAL:
        return f"Creating provisional customers (DSI job {jid})"
    if kind == KIND_DSI_BULK_IGNORE:
        return f"Ignoring steward candidates (DSI job {jid})"
    if kind == KIND_DSI_RESOLUTION_PLAN_APPLY:
        return f"Applying resolution plan (DSI job {jid})"
    if kind == KIND_DSI_RESOLUTION_PLAN_COMPUTE:
        return f"Computing resolution plan (DSI job {jid})"
    if kind == KIND_DSI_SOH_RECONCILIATION:
        return f"Reconciling inventory (DSI job {jid})"
    if kind == KIND_DSI_VELOCITY_COMPUTE:
        return f"Computing sell-out velocity (DSI job {jid})"
    if kind == KIND_DSI_FORECASTING:
        return f"Generating forecasts (DSI job {jid})"
    if kind == KIND_PRODUCT_MASTER_VALIDATE:
        return f"Validating product master (job {jid})"
    if kind == KIND_COMMERCIAL_PLANNER_LINEUP_PARSE:
        return f"Parsing current lineup (job {jid})"
    if kind == KIND_SHIPMENT_BULK:
        return f"Applying shipment steward bulk action (job {jid})"
    if kind == KIND_CPOR_HISTORICAL_IMPORT:
        return f"Applying historical CPOR import {jid}"
    if slug == "distributor_inventory":
        if mode == "validate":
            return f"Validating DSI import {jid}"
        return f"Processing DSI import {jid}"
    if slug == "inbound_shipments":
        return f"Processing shipment import {jid}"
    if slug == "product_master":
        return f"Applying product master (job {jid})"
    if slug == "cpor_historical_cases":
        if mode == "apply":
            return f"Applying historical CPOR import {jid}"
        return f"Validating historical CPOR import {jid}"
    return f"Import job {jid}"


def _kind_from_template_slug(job: ImportJob) -> str:
    slug = (job.template_slug or "").strip()
    if slug == "inbound_shipments":
        return KIND_SHIPMENT_IMPORT
    if slug == "product_master":
        return KIND_PRODUCT_MASTER_COMMIT
    if slug == "cpor_historical_cases":
        return KIND_CPOR_HISTORICAL_IMPORT
    return KIND_DSI_PIPELINE


def _normalize_dsi_bulk_kind(raw_kind: Any) -> str:
    if isinstance(raw_kind, str) and raw_kind.strip() in _DSI_BULK_ALLOWED_KINDS:
        return raw_kind.strip()
    return KIND_DSI_BULK_PROVISIONAL


# --- Resolved slot read model --------------------------------------------------


@dataclass(frozen=True)
class ResolvedSlot:
    slot_key: str
    task_id: str
    kind: str
    label: str
    async_poll: bool


def _extract_task_id(descriptor: SlotDescriptor, value: Any) -> str | None:
    if descriptor.payload_shape == SHAPE_STRING:
        return value.strip() if isinstance(value, str) and value.strip() else None
    if isinstance(value, dict):
        tid = value.get("task_id")
        return tid.strip() if isinstance(tid, str) and tid.strip() else None
    return None


def _resolve_kind(descriptor: SlotDescriptor, job: ImportJob, value: Any) -> str:
    if descriptor.kind_resolution == FROM_TEMPLATE_SLUG:
        return _kind_from_template_slug(job)
    if descriptor.kind_resolution == FROM_PAYLOAD:
        raw = value.get("kind") if isinstance(value, dict) else None
        return _normalize_dsi_bulk_kind(raw)
    return descriptor.fixed_kind or ""


def _resolve_label(descriptor: SlotDescriptor, job: ImportJob, value: Any, kind: str) -> str:
    if descriptor.label_source == LABEL_PAYLOAD and isinstance(value, dict):
        stored = value.get("label")
        if isinstance(stored, str) and stored.strip():
            return stored.strip()
        if descriptor.default_label:
            return descriptor.default_label
    return task_label(job, kind=kind)


def iter_active_slots(job: ImportJob) -> Iterator[ResolvedSlot]:
    """Yield a :class:`ResolvedSlot` for every registered slot present on the job."""
    meta = job.staged_metadata if isinstance(job.staged_metadata, dict) else {}
    for descriptor in TASK_SLOTS:
        value = meta.get(descriptor.meta_key)
        if value is None:
            continue
        task_id = _extract_task_id(descriptor, value)
        if not task_id:
            continue
        kind = _resolve_kind(descriptor, job, value)
        label = _resolve_label(descriptor, job, value, kind)
        async_poll = bool(value.get("async_poll", True)) if isinstance(value, dict) else True
        yield ResolvedSlot(
            slot_key=descriptor.slot_key,
            task_id=task_id,
            kind=kind,
            label=label,
            async_poll=async_poll,
        )


# --- Writers -------------------------------------------------------------------


def _build_slot_payload(
    descriptor: SlotDescriptor,
    *,
    task_id: str,
    async_poll: bool,
    extra: dict[str, Any],
) -> Any:
    if descriptor.payload_shape == SHAPE_STRING:
        return task_id
    payload: dict[str, Any] = {"task_id": task_id, "async_poll": async_poll}
    if descriptor.fixed_kind is not None:
        payload["kind"] = descriptor.fixed_kind
    if descriptor.label_source == LABEL_PAYLOAD and descriptor.default_label:
        payload["label"] = descriptor.default_label
    payload["queued_at"] = datetime.now(timezone.utc).isoformat()
    # Caller-supplied extras (kind for dsi_bulk, case_id/filename/candidate_count, an
    # overriding label, …) win over the defaults above.
    payload.update(extra)
    return payload


def set_task_slot_on_job(
    job: ImportJob,
    slot_key: str,
    *,
    task_id: str,
    async_poll: bool = True,
    **extra: Any,
) -> None:
    """Write a background-task slot onto ``job.staged_metadata`` (no commit).

    Caller owns the session/commit. Byte-compatible with the previous per-importer
    writers (same meta key, same payload fields).
    """
    descriptor = _SLOTS_BY_KEY.get(slot_key)
    if descriptor is None:
        raise KeyError(f"Unknown background task slot: {slot_key!r}")
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    meta[descriptor.meta_key] = _build_slot_payload(
        descriptor, task_id=task_id, async_poll=async_poll, extra=extra
    )
    job.staged_metadata = to_jsonable(meta)


def set_task_slot_by_job_id(
    job_id: int,
    slot_key: str,
    *,
    task_id: str,
    async_poll: bool = True,
    **extra: Any,
) -> None:
    """Open a sync session, write the slot, and commit. For enqueue helpers that run
    detached from any caller session."""
    from app.db.session_sync import SessionLocal

    with SessionLocal() as db:
        job = db.get(ImportJob, int(job_id))
        if job is None:
            return
        set_task_slot_on_job(job, slot_key, task_id=task_id, async_poll=async_poll, **extra)
        db.add(job)
        db.commit()


# --- Clearers ------------------------------------------------------------------


def clear_task_slot(meta: dict[str, Any], slot_key: str) -> None:
    """Remove a single slot from a staged_metadata dict (in place)."""
    descriptor = _SLOTS_BY_KEY.get(slot_key)
    if descriptor is None:
        raise KeyError(f"Unknown background task slot: {slot_key!r}")
    meta.pop(descriptor.meta_key, None)


def clear_task_slot_on_job(job: ImportJob, slot_key: str) -> None:
    meta = dict(job.staged_metadata or {}) if isinstance(job.staged_metadata, dict) else {}
    descriptor = _SLOTS_BY_KEY.get(slot_key)
    if descriptor is None:
        raise KeyError(f"Unknown background task slot: {slot_key!r}")
    if meta.pop(descriptor.meta_key, None) is not None:
        job.staged_metadata = to_jsonable(meta) if meta else None


def clear_all_task_slots(meta: dict[str, Any] | None, *, include_timing: bool = True) -> dict[str, Any] | None:
    """Return ``meta`` without ANY background-task slot (or None if empty).

    Used by cancel/retry so no orphan slot survives. With ``include_timing`` also
    strips the pipeline timing keys (matches the legacy cancel/retry behavior).
    """
    if not isinstance(meta, dict):
        return None
    m = dict(meta)
    for key in _TASK_META_KEYS:
        m.pop(key, None)
    if include_timing:
        for key in _PIPELINE_TIMING_KEYS:
            m.pop(key, None)
    return to_jsonable(m) if m else None


def has_any_task_slot(meta: dict[str, Any] | None) -> bool:
    if not isinstance(meta, dict):
        return False
    return any(key in meta for key in _TASK_META_KEYS)


def iter_slot_task_ids(meta: dict[str, Any] | None) -> Iterator[str]:
    """Yield the Celery task id of every registered slot present in ``meta``.

    Registry order (main → dsi_bulk → soh → velocity → forecasting → pm_validate →
    pm_commit → lineup). Used by cancel to revoke ALL in-flight sub-tasks, not just the
    main/dsi_bulk pair.
    """
    if not isinstance(meta, dict):
        return
    for descriptor in TASK_SLOTS:
        value = meta.get(descriptor.meta_key)
        if value is None:
            continue
        task_id = _extract_task_id(descriptor, value)
        if task_id:
            yield task_id


# --- Query fragment ------------------------------------------------------------


def jobs_with_possible_background_tasks():
    """SQLAlchemy condition: jobs that are running or still reference a task slot.

    Mirrors the historical narrow scan but is generated from the registry so a new slot
    automatically widens the scan.
    """
    has_meta = ImportJob.staged_metadata.isnot(None)
    conditions = [ImportJob.status == "running"]
    for meta_key in _TASK_META_KEYS:
        conditions.append(and_(has_meta, ImportJob.staged_metadata.has_key(meta_key)))
    return or_(*conditions)
