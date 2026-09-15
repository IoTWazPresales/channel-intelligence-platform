# N-0027 implementer evidence — steward queue grouped by failure type

**Run:** `NS15_STEWARD_QUEUE_20260915` · **Actor:** `gov-001` · **2026-09-15**
**Do not complete.** Independent GOV-008 is a later session, different run and actor. Do not reuse NS14 or the N-0025 review run.
**Playwright MCP only.** No `browser_cdp`. No writes to `cip`.

Cites **D-0008** (accepted): Data & Stewardship Steward queue is a cross-job leaf; per-job engines remain the resolver.
Cites **D-0006**: **D-0002** mapping-queue restore vs retire stays deferred — `entity_mapping_queue` not restored or retired.
N-0011 `STEWARD_QUEUE_APPROVE_REJECT` stays deferred. No parallel resolver.

Reconcile: `.eif/audit/NS15_STEWARD_QUEUE_20260915/RECONCILE.md`. `current_database()=cip` printed first on SQL probes this session.

---

## Charter (re-read from ledger seq 656 before close)

N-0027: Queue lists `import_entity_mapping_candidate` rows with `status=needs_review` across jobs. Grouping is `GROUP BY entity_type` from that table (plus a config registry for label/href of known types). Job id, template_slug, and file are provenance. Click routes into the existing steward: DSI/CST `/admin/imports?job={id}`; shipment `/admin/shipment-evidence?importJobId={id}`. `failed_imports` opens `/admin/imports?jobStatus=failed`. Resolution rules hold. Do not complete.

---

## Live cip (VERIFIED)

`current_database()='cip'`. Open `needs_review` candidates **2814** across six `entity_type` groups on completed / completed_with_errors jobs. `entity_mapping_queue` empty. Unarchived `import_job.status=failed`: **47**.

---

## Playwright 1280×800 (VERIFIED)

| Step | Result |
|---|---|
| `/admin/mappings` signed in Local Admin | Open candidates **2814**. Failure-type chips from API groups (not hardcoded Customer/Product/Distributor sections). Legacy mapping-queue empty |
| Steward `steward-queue-open-27112` | Landed `/admin/imports?job=900`. Text **Job #900** visible — existing Import Center job steward, not a new resolver |
| `/brief` Needs attention | **47 failed imports** · `unarchived import_job.status = failed` · href `/admin/imports?jobStatus=failed` (not `/admin/mappings`) |
| Click that signal | Import Center **Failed · 47**. Grid rows with `failed` (mailbox ingest, historical_lineup `test.xlsx`, …) |

---

## Product land

| Path | Role |
|---|---|
| `apps/api/app/services/imports/steward_queue.py` | SQL `GROUP BY entity_type`; registry is href/label config only; unknown types still listed (`covered=false`) |
| `apps/api/app/api/v1/endpoints/imports.py` | `GET /imports/steward-queue` |
| `apps/api/app/services/brief_signals.py` | `failed_imports` → `/admin/imports?jobStatus=failed` |
| `apps/web/src/features/data-stewardship/StewardFailureQueue.tsx` | Queue surface; chips from `groups`; Steward routes to existing engines |
| `apps/web/src/app/(app)/admin/mappings/page.tsx` | Mounts the queue; legacy `entity_mapping_queue` remains secondary (D-0002 untouched) |
| `apps/web/src/features/data-stewardship/DataChrome.tsx` | Steward count uses `candidates_needs_review` |

Tests: `pytest tests/test_steward_queue.py` and `tests/test_brief_signals_href.py`; vitest `StewardFailureQueue.test.tsx` and mappings `page.test.tsx`.

---

## UNCOVERED (not invented)

| Finding | Backlog |
|---|---|
| Re-resolution after catalogue-gap / product master; DSI fact `source_key` embeds `product_id` | BACKLOG-187 |
| Non-candidate failures: DSI geo tokens, lineup `unknown_*`, payment unmatched / `customer_unresolved`, shipment `product_resolution_status`, historical unmatched Case IDs, master unverified, stubs | BACKLOG-188 |

---

## Untouched

D-0002, N-0006, N-0013, D-0010, BACKLOG-181, Movement/Execution relocated workspaces, N-0025 remediation, N-0026 (not re-audited). No GOV-008 on this node. FLAG ≠ BLOCK. No auto-create of masters. Tenant identity via `tenant_id_from_user`, not a queue constant.
