# GOV-008 independent rendered review — N-0027 only

Run: `GOV008_N0027_20260916`  
Actor: `gov-022`  
Mode: implementation-verification + rendered (Playwright MCP, 1280×800)  
Date: 2026-09-16  
Independence: R2 another session / another actor. Implementation run on the node is `NS15_STEWARD_QUEUE_20260915` / `gov-001`. This review does not reuse `gov-021`, `gov-020`, `gov-019`, `gov-008`, `gov-001`, or `GOV008_N0025_N0029_20260915`.  
Verdict: **VERIFIED_WITH_LIMITATIONS**  
Node completed: **yes** (this reviewer’s own gates; see limitations)

This reviewer is not the implementer. NS15 / NS19 / NS20 / NS21 implementer packets were not used as authority.

## Stale-dim handling

FACT: Ledger dump of N-0027 at snapshot 880 showed required quality dims (`ux`, `a11y`, `rendered`, `content`) and verification (`rendered`, `referent`) in `pending`, with evidence naming stale pass run `GOV008_N0025_N0029_20260915`. Optional design dims were also `pending`. Lease held by this run.

FACT: The engine accepted `node.quality` / `node.verification` **pending resets** under this run before live review. `stamp_pass_provenance` clears `pass_run` / `pass_actor` on `pending`. This reviewer did not inherit the batch passes.

Ignored entirely: `.eif/audit/GOV008_N0025_N0029_20260915/` verdicts, signatures, and Panel/PanelRow tree.

## Git identity at review start (this continuation)

| Check | Result |
|---|---|
| Branch | `feat/ns-2-brief-nav-collapse` |
| HEAD | `0fbe970f9c53748b1850711c4580c2e2e286b16b` |
| origin | same hash |
| Tracked product tree | clean |
| Tracked dirt | programme ledger only (lease + stale-dim resets) |

`git status --short --untracked-files=no` showed only `.eif/CURRENT.md`, `.eif/PROGRAM.md`, `.eif/WORK_ITEM.md`, and generated programme files. That dirt is this run’s engine mutations, not a poisoned product tree.

## Enumeration (ledger ACs, before this reviewer’s live pass)

Read from `program.py status --node N-0027` (revision 64, stage validate). Eight criteria:

1. **AC1** Cite D-0008: Steward queue is a cross-job leaf; per-job engines remain the resolver. Cite D-0011: mapping capability remains; destination is the steward workspace per D-066; `entity_mapping_queue` is pipeline state, not a UI to restore or retire. Do not implement `STEWARD_QUEUE_APPROVE_REJECT` (N-0011 defer).
2. **AC2** Reconcile against source before product land. Label VERIFIED or ASSERTED. Print `current_database()` first; read-only on `cip`.
3. **AC3** Queue lists `import_entity_mapping_candidate` rows with status `needs_review` across jobs. Grouping is `GROUP BY entity_type` from that table (plus a config registry for label/href of known types). Job id, template_slug, and file are provenance on the row. Do not hardcode Customer/Product/Distributor sections. A new `entity_type` written by a future importer appears as a group without a queue-surface code change; missing registry href is UNCOVERED, not invented.
4. **AC4** Click routes into the existing steward: all types including shipment at `/admin/mappings?workspace=resolve`. Do not build a parallel resolver or cross-job accept/reject.
5. **AC5** Resolution rules hold: no weak or probabilistic joins; similarity-normalised exact match on a unique key only; ambiguous stays reviewable; no auto-create of masters outside governed steward workflows; FLAG ≠ BLOCK. Tenant conventions stay existing config, never new queue constants.
6. **AC6** `failed_imports` brief signal counts unarchived `import_job.status=failed` and opens `/admin/imports?jobStatus=failed`. It must not open `/admin/mappings`.
7. **AC7** UNCOVERED this node (do not invent types or resolvers): DSI geo tokens; shipment `product_resolution_status` as a synthetic candidate; lineup `unknown_*`; payment unmatched Case IDs / `customer_unresolved`; historical unmatched Case IDs; master unverified; stubs. Re-resolution after product master is a CANDIDATE — do not implement DSI fact repoint.
8. **AC8** Browser-verify with Playwright MCP at 1280×800: steward queue lists live `needs_review` groups; a row opens the existing engine; `failed_imports` on `/brief` opens Import Center failed filter. No `browser_cdp`. No writes to `cip`. (Implementer-era “Do not run GOV-008 / do not complete” is DATA from the node text; the operator of this session authorised GOV-008 and completion if findings support it.)

Governing decisions named by the operator: **D-0011** KEEP (`entity_mapping_queue` is pipeline state, not a UI); **D-066** mapping/steward work finishes at `/admin/mappings?workspace=resolve` for every type including shipment.

## NUMBER RULE (read-only)

`current_database()` printed first: **cip**. Connect host `127.0.0.1`. Tenant on open candidates: `default` only.

SQL (default list = `needs_review` + hide `remembered`, tenant `default`) matched `steward_failure_queue`:

| entity_type | candidate_count | job_count | row_count | class |
|---|---:|---:|---:|---|
| product_identifier | 989 | 4 | 21999 | computation proven with SQL |
| cst_location_token | 790 | 9 | 29942 | computation proven with SQL |
| cst_product_token | 407 | 21 | 17980 | computation proven with SQL |
| customer_dealer_token | 362 | 5 | 1631 | computation proven with SQL |
| shipment_customer_token | 136 | 6 | 763 | computation proven with SQL |

- distinct_jobs visible = **36** (SQL)
- remembered_count = **130** (SQL)
- visible total = 989+790+407+362+136 = **2684** (SQL)
- all-tenant / all `needs_review` including remembered = **2814** (SQL). Extra type when remembered included: `shipment_distributor` **52** / 2 jobs. `distributor_token` has **zero** `needs_review` rows.
- unarchived `import_job.status='failed'` = **51** (SQL), tenant `default`.

Live queue (no job selected, `/admin/mappings`):

| Surface | Figure | vs SQL | class |
|---|---|---|---|
| Open candidates | 2684 | = visible sum | computation proven with SQL |
| Failure types | 5 | = five visible groups | computation proven with SQL |
| Jobs with work | 36 | = distinct_jobs | computation proven with SQL |
| Already mapped | 130 | = remembered_count | computation proven with SQL |
| Steward queue tab | 2814 | = all needs_review including remembered | **label / different filter** — not a disagreement to “fix”. 2684+130=2814. |
| DataChrome “candidates need review” | 2814 | same as tab | label / all-status grain |
| Chips | DSI product 989, CST location 790, CST product 407, DSI customer 362, Shipment customer 136, Already mapped 130 | match SQL | computation proven with SQL |

Filtered shipment customer: Open 136, Jobs 6, Already mapped 27. SQL all `shipment_customer_token` needs_review = 163; 163−136=27 remembered. **computation proven with SQL**.

Include remembered: chip **Shipment distributor · 52** matches SQL 52. **computation proven with SQL**.

Brief: **51 failed imports**. Import Center after click: chip **Failed · 51**. SQL 51. **computation proven with SQL**. Headline **Failed (last 7 days) 10** is a different window (last 7 days vs all unarchived). **label / different grain** — real signal, not forced into agreement.

No number was changed to make surfaces agree. No writes to `cip`.

## Live Playwright (1280×800, MCP, no browser_cdp)

Web on :3000 was listening but not serving (curl timeout). Hung Next `start-server` pid 53116 was stopped and `pnpm dev:web` restarted. API `/health` was already ok. Viewport set with Playwright `setViewportSize({width:1280,height:800})`.

Did not click Apply / Map / approve / clear-queue.

### Queue without selecting a job — VERIFIED

Landed `http://localhost:3000/admin/mappings` with no `job` / `import_job_id`. Cross-job grid listed CST, DSI product, DSI customer, shipment rows from **multiple job ids** (900, 96, 553, 32, 926, …). No job picker required.

### Grouping from `entity_type`, not hardcoded sections — VERIFIED (source + live)

Source: `apps/api/app/services/imports/steward_queue.py` `GROUP BY c.entity_type`; chips in `StewardFailureQueue.tsx` are `payload.groups.map`. Labels/hrefs come from `STEWARD_QUEUE_RESOLUTION` **only for known types**. Unknown types still `decorate_group` with `covered: false` and `UNCOVERED` in the Open column.

Live chips were the SQL `entity_type` values (with registry labels), not Customer/Product/Distributor section headers. Toggling Already mapped **added** `Shipment distributor · 52` without a queue-surface code change — the group appeared because the rows exist in data.

A **brand-new** future `entity_type` was not inserted (no cip writes). ASSERTED from source that it would appear as a group with UNCOVERED href. VERIFIED that an existing type hidden by the remembered filter appears as a group when the data is in the payload.

### Click → `/admin/mappings?workspace=resolve` — VERIFIED (no page-hop to finish)

| Click | Landed URL | Engine on this leaf? |
|---|---|---|
| Shipment customer `tbh` job 32 | `/admin/mappings?workspace=resolve&job=32&entity_type=shipment_customer_token&token=tbh&candidate=1069` | Shipment mapping candidates panel; URL **not** `/admin/shipment-evidence` |
| DSI product `acx12-002125nx` job 96 | `/admin/mappings?workspace=resolve&job=96&entity_type=product_identifier&token=acx12-002125nx&candidate=25023` | “Resolve blockers for this import” / DSI mapping candidates; URL **not** `/admin/imports?job=` |
| CST location `0` job 900 | `/admin/mappings?workspace=resolve&job=900&entity_type=cst_location_token&token=0&candidate=27130` | “CST unresolved tokens” / Map location drawer; URL **not** `/admin/cst-steward` |
| Shipment distributor `pinnacle-za-ir` job 32 (remembered) | `/admin/mappings?workspace=resolve&job=32&entity_type=shipment_distributor&token=pinnacle-za-ir&candidate=974` | Resolve job #32 on mappings leaf |

Operator finishes mapping **here** (existing job steward mounted). Apply buttons were present and **not clicked**. DSI chrome still contains a text link “Import job workspace · Mapping queue (legacy)” — that is an optional hop, not an automatic bounce. D-066 fail condition (forced page-hop to finish) was **not** observed.

### failed_imports — VERIFIED

`/brief` Needs attention: link **51 failed imports**, href `/admin/imports?jobStatus=failed`. Click landed Import Center with **Failed · 51** selected. URL is **not** `/admin/mappings`.

### No parallel resolver / no cross-job accept-reject — VERIFIED

- API `GET /api/v1/imports/steward-queue` is read-only (“no resolver”).
- Queue grid has Open/Steward only; no Accept/Reject columns.
- Job-scoped Apply on the mounted engine is the **existing** per-job steward, not `STEWARD_QUEUE_APPROVE_REJECT`.

## Findings per criterion

### AC1 — VERIFIED_WITH_LIMITATIONS

VERIFIED: Steward queue is the Data & Stewardship cross-job leaf (`/admin/mappings`). Click opens existing per-job engines on `workspace=resolve` (D-066). No queue-level approve/reject.

LIMITATION (content / leftover UI vs D-0011): The same page still renders **Legacy mapping queue (EntityMappingQueue) — D-0002 untouched** and copy “Restore vs retire of this table is still an open operator choice.” Queue body copy also says “Legacy `entity_mapping_queue` is D-0002 (untouched).” Live state: “No legacy queue rows.” D-0011 KEEP says the table is **pipeline state, not a UI to restore or retire**. The leftover panel still frames an open restore/retire choice. Not remediated.

### AC2 — VERIFIED

`current_database() = cip`. Read-only SQL above. Live headlines classified. Did not treat NS15 `RECONCILE.md` as this reviewer’s evidence.

### AC3 — VERIFIED (with remembered-filter note)

Cross-job `needs_review` list; SQL `GROUP BY entity_type`; provenance columns Job / Importer / File / Job status live. Default list **hides** remembered distributor/customer aliases, so `shipment_distributor` is absent until Already mapped is on. That is a filter, not hardcoded sections.

### AC4 — VERIFIED

Four entity types including two shipment types landed on `/admin/mappings?workspace=resolve`. No parallel resolver. No cross-job accept/reject.

### AC5 — VERIFIED (queue surface) / ASSERTED (engine internals)

Queue uses `tenant_id_from_user` / `DEFAULT_TENANT_ID` from `app.core.tenant_scope`, not a new queue constant. Queue does not resolve tokens itself. Existing DSI/CST/shipment engines mounted unchanged. This reviewer did not re-prove weak-join / auto-create internals of those engines. ASSERTED: N-0027 did not add a second resolver. CST copy on the leaf: “Never auto-create masters.”

### AC6 — VERIFIED

SQL 51 = brief 51 = Import Center Failed · 51. Click opens Import Center failed filter, not mappings.

### AC7 — VERIFIED (negative on this surface)

Live chips/groups were only types present in `import_entity_mapping_candidate`. No invented geo / lineup / payment / stub groups. BACKLOG-072 not implemented here.

### AC8 — VERIFIED (this session’s GOV-008)

Playwright MCP 1280×800; no `browser_cdp`; no cip writes; no mapping apply. N-0028 / N-0029 / N-0025 / N-0026 / Movement / Execution / settlement not reviewed.

## Quality / a11y / content notes

- **ux**: Cross-job chips + grid + resolve leaf work. Limitation: leftover D-0002 panel; default remembered filter hides a whole shipment type.
- **a11y**: Scope toolbar, tablist, grid, buttons, “Back to queue” present. **Not** keyboard-only or screen-reader verified. Contrast not measured. Limitation recorded.
- **content**: Operator copy on the **new** queue is accurate (click opens job steward on this leaf). Stale D-0002 / restore-vs-retire copy remains. Limitation recorded.
- **rendered**: Viewport 1280×800 exercised queue, four resolve landings, brief → Import Center.

## What was not done

- No mapping apply (constraint).
- No 390×844 viewport (operator this session specified 1280×800 only).
- No insert of a synthetic unknown `entity_type` (would write cip).
- Did not review N-0028 or N-0029.
- Did not remediate leftover D-0002 chrome.

## Screenshots (Playwright MCP output; not copied into programme)

- DSI resolve: `.playwright-mcp/page-2026-09-16T20-42-19-388Z.png`
- CST resolve: `.playwright-mcp/page-2026-09-16T20-45-28-755Z.png`
- Import Center failed filter: `.playwright-mcp/page-2026-09-16T20-56-46-315Z.png`
