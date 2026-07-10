# Shipment evidence: evidence vs fact operator guide

## Two layers (Plan C operator docs)

| Layer | Table | Scope | Meaning |
|-------|-------|-------|---------|
| **Evidence** | `shipment_evidence_line` | Per `import_job_id` | Immutable snapshot of what this upload file contained. History is preserved per job. |
| **Fact** | `fact_inbound_shipment` | Global `source_key` | Current operational truth for inbound shipments. **Latest apply wins** across jobs. |

Upload and validate alone **do not** change `fact_inbound_shipment`. You must **steward entities** (map/provisional) and **Apply** the job.

## `import_purpose` (staged_metadata)

Set on shipment import jobs via `staged_metadata.import_purpose`:

| Value | When to use |
|-------|-------------|
| `current` | Rolling operational report (default when unset) |
| `backfill` | Historical landed-only or archival file (e.g. 2023 ACZA) |

Backfill jobs still write evidence per job; after steward + apply, re-apply the **current** job if needed so fact rows reflect the latest operational snapshot.

## Recommended backfill workflow

1. Upload historical file → validate → steward products + distributors/customers on **evidence**.
2. **Apply** historical job → upserts `fact_inbound_shipment` for keys in that file.
3. Upload/validate **current** job → steward deltas → **Apply** current job (latest-job-wins for overlapping `source_key`).
4. Revalidate DSI so corroboration reads refreshed evidence (corroboration uses **evidence**, not fact).

## Steward parity (Plan C)

- Steward surface: `ShipmentImportJobResolutionSection` + shared `ImportStewardCandidateWorkspace`.
- Resolution plan: `POST /api/v1/shipment-evidence/import-jobs/{id}/resolution-plan/*` (compute, effective, apply-async).
- Bulk steward remains on `/api/v1/shipment-evidence/…` (not `/mappings/`).
