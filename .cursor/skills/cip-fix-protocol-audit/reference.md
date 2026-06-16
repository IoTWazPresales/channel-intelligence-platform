# Fix-protocol — canonical file anchors

Use as starting grep targets; verify on disk — do not assume paths are current.

## DSI (`distributor_inventory`)

| Concern | Typical paths |
|---------|----------------|
| Validate sync | `apps/api/app/services/imports/distributor_sales_inventory.py` |
| Apply orchestrator | `apps/api/app/services/imports/dsi_resolution_plan_apply_sync.py` |
| Bulk writers | `dsi_bulk_*_sync.py` in same directory |
| Dispatch | `apps/api/app/api/v1/endpoints/imports.py` (`_dispatch_dsi_*`) |
| Celery | `apps/api/app/worker/tasks.py` |
| Web steward | `apps/web/src/features/import-steward/DsiImportJobResolutionSection.tsx` |
| Plan compute poll | `apps/web/src/features/import-steward/useDsiResolutionPlan.ts` |

## Shipment evidence (`inbound_shipments`)

| Concern | Typical paths |
|---------|----------------|
| Apply dispatch | `_dispatch_shipment_apply` in imports endpoints |
| Steward panel | `ShipmentEntityStewardPanel.tsx` / inbound evidence mapping |
| Bulk batching | Phase 2 shipment batch endpoints under `shipment-evidence` |

## Shared

| Concern | Path |
|---------|------|
| Import contract matrix | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` |
| Parity rule | `.cursor/rules/import-parity.mdc` |
| Transient retry | `apps/api/app/db/db_transient_retry.py` |
| Sync session | `apps/api/app/db/session_sync.py` |
| Background slots | `apps/api/app/services/imports/import_background_slots.py` |

## Commit model vocabulary

| Term | Meaning |
|------|---------|
| Per-row | Loop with commit or flush per entity — slow, avoid for bulk steward |
| Per-chunk | Fixed batch (e.g. 2k staging rows) then commit |
| Set-based | Single `INSERT … ON CONFLICT` per chunk — canonical for facts/aliases |
| Monolithic txn | One open transaction across cache + row loop — idle-in-tx risk on remote DB |
