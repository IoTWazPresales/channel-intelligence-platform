# SWEEP B — docs/BACKLOG.md lines 1091-2063 — COMPLETE

Lenses: business-analyst (PB-003), product-manager (PB-002). Read-only sweep, 2026-10-07. Status is decided from CODE evidence (apps/api, apps/web, scripts, alembic), not the doc's own status line. A negative grep describes that search only, not proof of absence. The earlier draft had no rows, so all 62 entries are new in this version.

Status key: DONE / OPEN / PARTIAL / OBSOLETE / UNCLEAR. Commits were confirmed with `git log --oneline -1`. "covered_by" is a ledger node from `.eif/ROADMAP.md`.

## 1. Entry table (62 entries, headings at lines 1091-2048)

| id | short title | status | evidence | covered_by | needs_warren |
|----|-------------|--------|----------|------------|--------------|
| 082 | DSI header vocabulary → template config | DONE | `apps/api/app/services/imports/template_definitions.py:250` `_policy` block | none | no |
| 081 | Customer merge alias seal | OPEN | `alias_seal\|loser.*alias` in apps/: 0 files | none (N-0030 Stage 4.8 has no ledger node) | no |
| 080 | CST article-alias batch Confirm/Reject | OPEN | `endpoints/cst_steward.py:661,678` per-alias confirm/reject only; no batch route | N-0069 | no |
| 079 | Ops-list MasterDataGridShell parity | OBSOLETE | Shell is now used only by masters (`admin/products`, `customers`, `distributors` page.tsx). CPOR cases were redesigned as the settlement desk (N-0008/N-0044), and Warren 2026-08-15 said not to wrap PvE or PM-gaps | none | no |
| 075 | Unit F remainder (DSI relocate, inboundEvidence) | DONE | `apps/web/src/app/(app)/admin/imports/dsi/*`, `admin/shipment-evidence/*` exist at the new paths | none | no |
| 074 | CST import steward E2 resolution plan | DONE | `import_background_slots.py:105` `SLOT_CST_RESOLUTION_PLAN`, `:215` registered | none | no |
| 078 | DSI layout-coalesce follow-ons | PARTIAL | `admin/imports/page.tsx:1002,1018` reads `dsi_excluded_mapping_keys`, but there is no Exclude-sheet control (grep `exclude sheet\|exclusions` in web: 0); no layout templates | N-0069 | no |
| 077 | DSI weekly email-attachment auto-ingest | PARTIAL | `services/mailbox_ingest/shipment_intake.py`, `main.py:25` poller does shipping only; no DSI batch-propose in mailbox_ingest | N-0069 | no |
| 073 | Import-job fact rollback / purge | DONE | `services/imports/import_job_bulk_delete.py:44` `preview_import_job_bulk_delete` | none | no |
| 070 | Frontend ESLint flat-config gap | DONE | `.github/workflows/ci.yml:34` `ESLINT_USE_FLAT_CONFIG: "false"` legacy shim; full flat config is still out of scope | none | no |
| 071 | Clone-gate pg_dump PATH tooling | DONE | `scripts/ops/clone_cip_db.py:5,25,35` `PG_BIN` resolution | none | no |
| 068 | Landed-quarter attribution (pod_date) | DONE | `services/commercial_planner/inbound_lineup_quarter.py:443,455` landed / shipped-not-landed units | none | no |
| 067 | Backfill file-provenance gap | OPEN | `RawFileMetadata\|storage_key\|.save(` in `lineup_bulk_backfill*` / `unified_lineup*`: 0 hits | N-0069 | no |
| 066 | #39/#40 duplicate-ingestion repair | DONE | `services/commercial_planner/lineup_duplicate_partition_repair.py`; N-0030 measured cases 39/40 gone on cip | none | no |
| 054 | Smoke-migrate URL fall-through guard | DONE | `apps/api/app/db/migrate_url_guard.py:41,44,84` `resolve_alembic_migrate_url` + `CIP_SMOKE_MIGRATE` | none | no |
| 055 | Lineup BU resolver thresholds provisional | OPEN | `lineup_business_unit_resolution.py:85,88` still 0.05 / 0.25, with no evidence of a retune | N-0058 (closed; retune not evidenced) | no |
| 059 | Catalogue column semantic mapping + cross-check | OPEN | Only alias-level division hints in `pm_suggest_mapping.py` / `pm_deterministic_aliases.py`; no post-map product_line-vs-division cross-check found | N-0069 | no |
| 060 | Bulk backfill completion UX | DONE | `admin/imports/BulkLineupBackfillDialog.tsx:474` Link POs CTA; test `BulkLineupBackfillDialog.test.tsx:104` keeps the dialog open with a summary | N-0059 | no |
| 057 | Bulk preview persists ImportJob | DONE (closed as documented) | `lineup_bulk_backfill_apply.py:48` `persist_preview_session` kept on purpose | none | no |
| 058 | Bulk apply dedicated slot | DONE | `import_background_slots.py:100,188` `SLOT_BULK_LINEUP_APPLY` | none | no |
| 053 | Per-line ROE override | OPEN | `roe_override` in apps/api: 0 (`read_model.py:245` `line_override` is generic provenance, not ROE) | N-0083 (adjacent: rate table + case ROE) | yes — is per-deal locked FX allowed at all? |
| 052 | Lineup margin-amount evidence capture | OPEN (data-gated) | `*_amount_evidence` columns: 0 hits; no real file needs it | none | no |
| 051 | Post-apply import reconciliation report | OPEN | `reconciliation` in `endpoints/imports.py`: 0 | N-0069 | no |
| 049 | Unresolved module (ignore → worklist) | PARTIAL | `services/imports/product_master_gap_worklist.py:258` reads `ignore_no_catalogue`; N-0027 groups the steward queue by failure type; no reason-grouped excluded-volume worklist | N-0069 | no |
| 048 | Import Celery / background-task parity audit | OPEN | BACKLOG-048 is cited only in `.eif/audit` notes; no as-built matrix | none | no |
| 047 | Wizard stale mapping after Back + re-upload | DONE | `admin/imports/page.tsx:3653` "New file — previous mapping cleared" banner | none | no |
| 046 | ACZA non-operational sheets (BOM Not Ready) | OPEN | `shipment_evidence_import.py:1017` `_load_frames_for_job`, no allowlist / BOM handling | N-0072 (blocked) | yes — is BOM Not Ready in scope for inbound facts? |
| 045 | Import steward UI parity audit | DONE | `endpoints/shipment_evidence.py:856,890` duplicate-review same/different; `ShipmentEntityStewardPanelLegacy` 0 refs | none | no |
| 044 | Shipment steward + resolution intelligence parity | DONE | `services/imports/shipment_resolution_plan_compute_sync.py`, `..._apply_sync.py`, `shipment_bulk_steward_enqueue.py` | none | no |
| 037 | DSI validate/refresh orchestrator unification | OPEN | `distributor_sales_inventory.py:3413` `refresh_dsi_staging_line_resolution`; no `_resolve_dsi_product_post_tiers` | N-0069 | no |
| 004 | Import Flow Phase 3 capability wizard | OPEN | `ImportFlowCapability\|isShipmentEvidence` still 24 hits in `admin/imports/page.tsx`; no capability map in packages/types | N-0069 | no |
| 006 | Slim shipment mapping-candidates response | PARTIAL | `endpoints/shipment_evidence.py:295` paginated variant exists; unpaginated `:227` still returns the full list | N-0069 | no |
| 008 | DSI region hints from shipment evidence | OPEN | `shipment` in `dsi_customer_region_evidence.py`: 0 | N-0069 | no |
| 009 | PIM typed-attribute promotion | OPEN | `category_template\|typed_attribute` in app: 0 | N-0070 | no |
| 010 | Drop legacy product_attribute_value rows | DONE | `apps/api/scripts/ops/drop_legacy_product_attribute_value.py` | N-0070 (re-home now moot) | no |
| 011 | catalog_product per-row flush → bulk upsert | OPEN | `pm_commit_catalog.py:72,294` `db.flush()` | N-0069 | no |
| 013 | customer_sell_through own import surface | DONE | `services/imports/customer_sell_through_apply.py`; `/cst-steward` router `router.py:165` | none | no |
| 014 | Customer classification mapping import | OBSOLETE | `classification` not in `template_definitions.py` or app (seed gone); no request since 2026-05 (N-0030 drop proposed) | none | no |
| 016 | DSI steward finalize scoped-later items | OPEN | Bundle: no `distributor_id` CONCURRENTLY index on `shipment_evidence_line` in active `alembic/versions` (only `versions_legacy/20260607_0047`); approve row by row | N-0069 | no |
| 017 | DSI embedding duplicate detection | OBSOLETE | No evidence that dedupe rates are unacceptable; N-0030 drop proposed | none | no |
| 018 | DSI geo token indexes | OPEN | `geo_token` in active alembic versions: 0 | N-0069 | no |
| 019 | Historical lineup deferred Phase items | OPEN (bundle) | No historical duplicate-apply guard module found; slices undecomposed | N-0069 (backfill itself N-0060 blocked) | no |
| 020 | PM full job revisit in wizard | OPEN | `admin/imports/page.tsx:2877` "Full PM revisit is not yet supported" | N-0069 | no |
| 021 | Commercial Planner RBAC, recommendation store, router extraction | PARTIAL | Router split done (`commercial_planner_lineup_routes.py`, `_intelligence_routes.py`; `commercial_planner.py:4509-4510`); session gate N-0033; `commercial_planner_auth.py:10` is a feature flag only (no planner roles); no durable planner recommendation model | N-0065 (BU entitlements, RBAC part only) | no |
| 025 | Generic-pipeline apply → async | DONE | `endpoints/imports.py:112,1334` `_enqueue_import_pipeline_job`; CST surface shipped since | none | no |
| 026 | PM consolidate two apply pipelines | DONE | `apps/api/app/ingestion/pipeline.py:215,217,709` retired path raises | none | no |
| 027 | PM + historical mapping → shared panel | DONE | `admin/imports/page.tsx:57,150,3269` `CanonicalColumnMappingPanel` + `hlMappingHelpers` | none | no |
| 029 | Sell-through surface + ImportFileUploadZone | DONE | (a) `153c93c` per doc; (c) `d0a8923` confirmed, `<ImportFileUploadZone` ×4 in page.tsx; (b) CST surface `/admin/cst-steward` | none | no |
| 031 | Admin data health dashboard | OPEN | `data-health` in apps/: 0 | none | no |
| 032 | Post-delete VACUUM runbook | OPEN | `*vacuum*` script in scripts/ or apps/api/scripts: 0 | none | no |
| 057-D4 | Plan D D4: stop dual-write to legacy evidence lines | OPEN (soak-gated) | Both `models/shipment_evidence.py:23` and `models/shipment_evidence_observation.py:17` are live; N-0030 measured 50 columns | none | no |
| 058-D5 | Plan D D5: drop redundant evidence columns | OPEN (blocked by D4) | Same as D4 | none | no |
| 062 | Open→shipped fact double-count remediation | OPEN | `shipment_plan_d_cutover.py:281` diagnostic only | N-0071 | yes — retire or supersede the open-order twin? |
| 076 | Inbound amount scale corruption | DONE | `services/shipping/amount_scale.py` KPI exclusion; quarantine recorded 2026-08-10 | none | no |
| 063 | Shipment change events v2: cancelled candidate | OPEN | `cancelled_candidate\|report_coverage` in app: 0 | none | yes — what counts as "cancelled" under report coverage |
| 064 | Shipment change-event UI | OPEN | API `endpoints/shipment_evidence.py:1476` `list_shipment_change_events`; web `change.events` 0 | none | no |
| 065 | Monthly-phased 1H allocation | DONE (superseded rule) | `lineup_case_parser.py:582-618` month columns derive the half; no months → refuse (no `uniform_half`); `month_split_json` persisted `:662`; commit `1893309` | N-0058 | no |
| 034 | PM launch/retire date integrity | PARTIAL | `apps/api/scripts/ops/repair_n0047_dim_product_windows.py` (inverted windows); `is_active` vs `lifecycle_status` and before-launch classes unresolved | N-0047 (inverted only) | yes — pre-launch channel fill vs wrong launch dates; canonical eligibility driver |
| 146 | Design batch 1 mockups | DONE | `docs/design/brief.html`, `stock-cover.html` | none | no |
| 147 | Charter acceptance gate | DONE | `docs/AUTONOMOUS_BUILD_CHARTER.md`, `docs/design/CHARTER_AMENDMENTS.md`; commit `83b4290` confirmed | none | no |
| 148 | NS-1a FX display honesty | DONE | `services/cpor/settle_readiness.py`, `settlement_book_read.py` `fx_blocked`; `8b038a1` confirmed (additive) | N-0012 | no |
| 155 | NS-1b FX mode + blocked settle | DONE | `alembic/versions/20260902_0020_cpor_case_fx_mode.py` | N-0006 | no |

## 2. OPEN or PARTIAL entries with covered_by none, as proposed work packages

| Work package | ids | One-line outcome | Size | Dependency |
|--------------|-----|------------------|------|------------|
| Merge alias seal | 081 | A full customer merge mints approved loser-name aliases to the keeper, so merged tokens stop coming back as steward work (pair with BACKLOG-083 redirect, per the earlier consult) | M | BACKLOG-083 companions; clone proof |
| Background-task parity audit | 048 | One as-built matrix of dispatch, slot, poll and cancel for each importer, plus a phased fix list; no orphan slots | M | Must come before the BACKLOG-039 queue split |
| Shipment change events v2 + timeline | 063, 064 | Cancelled-candidate signal from report coverage, and an in-app event timeline on the existing API | M | Warren defines the "cancelled" rule (063) |
| Plan D legacy-column retirement | 057-D4, 058-D5 | Stop the dual-write to `shipment_evidence_line`, then drop the redundant columns by migration | M | 30-day soak passed; Warren approves D4; D5 after D4 + migration review |
| Admin data health + vacuum ops | 031, 032 | Read-only `/admin/data-health` (row counts, staging vs fact per job), plus a targeted VACUUM runbook/script | S–M | None (031); a large delete triggers 032 |
| Lineup margin-amount evidence | 052 | Amount columns capture currency margins instead of dropping them | S | Data-gated: a real workbook with Rand amounts; migration approval |

Not packaged because the cover is adjacent or closed: 053 (N-0083 adjacent; needs Warren), 055 (N-0058 closed without an evidenced retune; suggest folding the histogram into N-0069 or reopening it under N-0058), 021 (N-0065 covers RBAC only; the durable recommendation store has no owner and no current trigger).

## 3. Counts

Tally: DONE 27 · OPEN 26 · PARTIAL 6 · OBSOLETE 3 · UNCLEAR 0 = 62.
- DONE (27): 082, 075, 074, 073, 070, 071, 068, 066, 054, 060, 057, 058, 047, 045, 044, 010, 013, 025, 026, 027, 029, 076, 065, 146, 147, 148, 155
- OBSOLETE (3): 079, 014, 017
- needs_warren yes (5): 053, 046, 062, 063, 034
- OPEN/PARTIAL with covered_by none (9): 081, 048, 063, 064, 057-D4, 058-D5, 031, 032, 052 → 6 work packages. 053 and 021 have only adjacent cover.
- Doc-status drift worth correcting in BACKLOG.md: 065 (doc says Parked; the tree refuses uniform_half and derives from months), 060 (doc says Partial; completion panel shipped), 014 (template seed no longer in the tree)
- OPEN (26): 081, 080, 067, 055, 059, 053, 052, 051, 048, 046, 037, 004, 008, 009, 011, 016, 018, 019, 020, 031, 032, 057-D4, 058-D5, 062, 063, 064
- PARTIAL (6): 078, 077, 049, 006, 021, 034
- Under N-0069 (Stage 8 umbrella): 080, 078, 077, 067, 059, 051, 049, 037, 004, 006, 008, 011, 016, 018, 019, 020 (16)
