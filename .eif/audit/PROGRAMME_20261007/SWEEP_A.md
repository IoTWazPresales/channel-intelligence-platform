# SWEEP A — BACKLOG.md lines 1-1090 vs code — COMPLETE

Lenses: business-analyst (PB-003), product-manager (PB-002). Read-only sweep, 2026-10-07, branch `feat/ns-2-brief-nav-collapse`.
Scope: VERIFY-debt register (lines 9-40) plus the 62 `## BACKLOG-NNN` entries with headings on lines 44-1074 (BACKLOG-135 down to BACKLOG-083).
The earlier draft had no rows, so every row below is new.

Method: status comes from code, alembic, CI and git evidence, not from the entry's own status line. Commits were checked with `git log --oneline -1`. File:line refers to the working tree at HEAD `cc7b4f2e` plus the uncommitted files. "covered_by" names a ledger node from `.eif/ROADMAP.md`. A node marked (terminal) is complete or deferred and still leaves a residual.
A negative grep result describes what that search covered. It does not prove the code is absent.

Measured this sweep: `apps/web` `tsc --noEmit` exit 0 (2026-10-07).

## 1. Entry table

| id | short title | status | evidence | covered_by | needs_warren |
|----|-------------|--------|----------|------------|--------------|
| VERIFY-debt register | ScopeBar column-picker unit (BACKLOG-209) not Opus-verified | OPEN | `ScopeBar` at `apps/web/src/features/workbench-ui/controls.tsx:73`. No N-0034 VERIFY artifact under `.eif/audit/`. The second-validation pass is BACKLOG-211 (`a9a68ee9`). The deferred non-debt items are still open: CPOR #313 fixture, readiness evidence-chip pass unproven, historical-lineup disposition gap (no `disposition` in historical services). | N-0034 (terminal) | no |
| BACKLOG-135 | CST SOH as CPOR MAC check | PARTIAL | `services/cpor/customer_soh_check.py:31` reads only `fact_customer_sellthrough` (`3624d7e7`). Line 13 says there is no tolerance flag. Line 15 says `vat_basis` is passed through, not converted. No `fact_inventory_customer` string in `apps/web/src`. | N-0049 (terminal) | yes: tolerance and VAT basis |
| BACKLOG-136 | CPOR session auth + KAM/PM/Ken/Wayne | PARTIAL | `cpor_cases.py:94` puts `require_roles(PLANNER, ADMIN)` on writes (N-0038, `e8284511`). The `Role` enum at `core/security.py:18` has only ADMIN/STEWARD/PLANNER/VIEWER, so the PM pre-approval-only and Ken no-MAC/terms separations are not enforced. | N-0038 (terminal) | yes: role mapping |
| BACKLOG-137 | `cpor_case_line` week-aligned windows | DONE | `alembic/versions/20260924_0023_cpor_case_line_window.py`, `models/cpor.py:40,84-92` (`d8b2e7ac`). `docs/memory/CURRENT.md:11` says cip is at `20261006_0024` and `window_start` exists. The entry's "cip pending" line is stale. | N-0050 | no |
| BACKLOG-138 | Writer for `cpor_case.superseded_by_case_id` | DONE | `services/cpor/case_supersession.py:176,215` (`342bb195`). Never exercised on cip. | none | no |
| BACKLOG-139 | `status` vs `workflow_status` drift | PARTIAL | `workflow_status_for` at `cpor_cases.py:1465` and `historical_import/apply_sync.py:195`. Repair script exists. D-0035 is open: re-applying a historical import resets lifecycle status (`apply_sync.py:204`). | N-0048 (terminal) | yes: D-0035 Q3 |
| BACKLOG-140 | CIP mints customer codes | DONE | `services/customer_code_mint.py`, `customers.py:106` `mode: map|mint`, `distributor_code_mint.py`, `CustomerBulkPromoteDialog.tsx:54` (`66003db9`, 2026-07-10, on HEAD). Display half done (N-0034). This contradicts the entry's "mint was never built". Promoting TMP named accounts has not been run. | none | yes: which TMP accounts to promote |
| BACKLOG-141 | Shipment steward panel ADMIN-only | DONE | `shipment_evidence.py:205,230,307` `require_roles(Role.ADMIN, Role.STEWARD)` (N-0038). | N-0038 | no |
| BACKLOG-142 | `apps/web` typecheck red | DONE | `tsc --noEmit` exit 0, run in this sweep. `CONTEXT.md:29` (2026-10-05, "tsc not exit 0") is out of date. | none | no |
| BACKLOG-143 | Disposable leftover state | DONE | N-0046 complete (`bfbf01c0`, `cc7b4f2e`). | N-0046 | no |
| BACKLOG-144 | `cip_test` seed gap, distributor-as-customer tests | OPEN | `tests/test_lineup_distributor_as_customer_remediation.py:24` still asserts live distributor 50. No test-local seed or marker. | none | no |
| BACKLOG-133 | Merged-id leftover assert on import complete | DONE | `services/imports/merged_id_leftover_check.py:27,62`, `dsi_apply_completion.py:163` (`faad6279`). | N-0051 | no |
| BACKLOG-134 | Alias pointing at merged customer | DONE | Folded into the 133 rail (`merged_id_leftover_check.py`). N-0030 measured 0 on cip. | N-0051 | no |
| BACKLOG-132 | Post-apply shipping mailer | DONE | `services/shipping_digest/build.py:230`. SMTP is gated by `CIP_SHIPPING_MAILER_SEND`; the comment is at `shipment_apply_sync.py:241` (`6a353323`). Graph `Mail.Send` is not built and waits on IT. | none | no |
| BACKLOG-130 | Listing ↔ CPOR activation check | DONE | `services/listing_capture/cpor_activation.py` (`edf29f3b`). | N-0076 (extends) | no |
| BACKLOG-131 | P3 widget canvas | DONE | `apps/web/package.json:29,33` (`echarts`, `react-grid-layout`), `dashboard_widget` in `models/saved_reports.py` (`1bde00a3`). | none | no |
| BACKLOG-129 | CST unmappable → catalogue-gap worklist | DONE | `services/imports/product_master_gap_worklist.py:70,237` `_merge_cst_tokens`. | none | no |
| BACKLOG-123 | Promote/merge onto ResolutionWorklist | OPEN | `features/admin/{Customer,Distributor}{,Bulk}PromoteDialog.tsx` are still bespoke. None of them imports `ResolutionWorklist`. | N-0069 | no |
| BACKLOG-124 | Tokenless customer acquisition | DONE | `commercial_planner/lineup_tokenless_customer_stamp.py` (`6324f7d3`), `commercial_planner.py:111`. | none | no |
| BACKLOG-122 | W2 same-customer uses majority line customer | OPEN | `lineup_bulk_backfill_preview.py:132,452` `_majority_customer`, `lineup_bulk_rederivation.py:181,257`. Trigger-gated (no W2 pair yet). | none | no |
| BACKLOG-121 | Preview row_count parser #1 vs apply #2 | PARTIAL | `lineup_bulk_backfill_preview.py:404-406` takes `identity_rows` from parser #2 for every sheet when `parser_ctx` is present, and `:565` sets `row_count=len(slice_rows)` (`bf4d2714`, D-034). No non-split divergence regression test found. | none | no |
| BACKLOG-119 | Phantom multi-BU PO competition | DONE | `commercial_planner/lineup_po_competition.py` (`4f592731`). | none | no |
| BACKLOG-120 | Dedicated supersession_carry column | OPEN | Optional and trigger-gated. Carry is still in notes: `lineup_case_supersession.py:30`, `lineup_case_po_unlink.py:24`. | none | no |
| BACKLOG-118 | Supersession carries case_po to winner | DONE | `lineup_case_supersession.py:33` `carry_case_po_links_on_supersession` (`5d9f454d`). | none | no |
| BACKLOG-117 | Review dialog omits case/file/competitors | DONE | `PoAutoLinkConfirmDialog` in `PoAutoLinkProposalsSection.tsx` (`afe01936`). | none | no |
| BACKLOG-116 | PO auto-link not on S1–S14 | DONE | `PoAutoLinkProposalsSection.tsx:42,1430` `ResolutionWorklist`. S10 async waived. | none | no |
| BACKLOG-115 | Select-all-high ignores competition | DONE | `d7a514a8`, `selection_protected` / bulk protection. | none | no |
| BACKLOG-114 | Period filter defaults to current quarter | DONE | `PoAutoLinkProposalsSection.tsx:988` `useState('')`. | none | no |
| BACKLOG-113 | No competition / version-prefix signal | DONE | `lineup_po_auto_link.py:38-43` `version_prefix` / `file_base` (`afe01936`). | none | no |
| BACKLOG-112 | `customer_unresolved` with null line customer | DONE | `03a5c190`, `lineup_distributor_token.py`, `lineup_customer_token_stamp.py`. | none | no |
| BACKLOG-125 | Distributor-as-customer masters | DONE | `commercial_planner/lineup_distributor_as_customer_remediation.py` (`5cf513b0`, PR #20). | none | no |
| BACKLOG-126 | No-dim distributor stems | DONE | Same remediation module (PR #20). The SMD residual is left on the free-picker by Warren's rule. | none | no |
| BACKLOG-127 | Shipment DAP for attribution | DONE | `lineup_distributor_attribution.py:242,250` `offer_accept_price` / `conflict_price` (`0c88f99d`, PR #21). | none | no |
| BACKLOG-128 | Stylus case_po linkage gap | DONE | `commercial_planner.py:3172,3185` `case-po-attribution-gap/preview|apply` (PR #21). | none | no |
| BACKLOG-111 | Celery worker stale lineup parser | DONE | `apps/api/app/worker/code_pin.py:32` (`e0c8a938`). | none | no |
| BACKLOG-110 | Auto-link survivor / po_issued guard | DONE | `commercial_planner.py:2099,2111` `allow_protected`, `evaluate_case_bulk_protection` (`d7a514a8`). | none | no |
| BACKLOG-109 | Steward unlink for case_po | DONE | `commercial_planner/lineup_case_po_unlink.py`, `PoCaseLinkWorklistSection` (`d1d9000e`). | none | no |
| BACKLOG-108 | Multi-BU slice_row_mapping_failed | DONE | `lineup_bulk_slice_rows.py:94` (`bf4d2714`, D-034). | none | no |
| BACKLOG-107 | Auto-link UI hides PO competition | DONE | `PoAutoLinkProposalsSection.tsx:69,403` `competing_case_ids`. | none | no |
| BACKLOG-106 | PoAutoLink surface PARTIAL vs S1–S14 | OBSOLETE | Superseded by BACKLOG-116: VERIFY PASS on `ResolutionWorklist` (`PoAutoLinkProposalsSection.tsx:1430`), S10 waived. The entry still says Parked. Recommend closing it and removing it from the N-0069 list. | N-0069 | no |
| BACKLOG-105 | PF 1H Gaming Desktop `Qty` not units | OPEN | `Total Qty` / `total_qty` does not appear in `services/commercial_planner` or `services/lineup`. N-0058 (`.eif/audit/PROGRAMME_20260930/N-0058.md`) says "PF Qty vs Total Qty ... not changed". | N-0058 (terminal) | yes: template-family mapping |
| BACKLOG-104 | Bulk collisions miss when notes null | DONE | `lineup_bulk_backfill_preview.py:630-643` wildcard sheet match. | none | no |
| BACKLOG-103 | Unified import 1H → Q1+Q2 | DONE | The shared parser raises `HalfYearSplitRequiresMonthColumnsError` and month-derived splits apply (N-0058, `d17a1a13`). Warren 2026-10-01: no uniform 50/50 fan-out. | N-0058 | no |
| BACKLOG-102 | Lineup corpus restore apply | DONE | Ops apply verified (`3f4a21b7`). | none | no |
| BACKLOG-101 | Lineup delete actor + bulk terminal status | DONE | `lineup_bulk_backfill_apply.py:35` `completed_with_errors`, `commercial_planner.py:19` `get_optional_current_user`. | none | no |
| BACKLOG-100 | `test:api` hard CI gate | DONE | `.github/workflows/ci.yml:169-175` hard step, no `continue-on-error` (`2dec626c`). | none | no |
| BACKLOG-099 | Live API in GitHub Actions e2e | OPEN | No `uvicorn` or `CIP_E2E_LIVE_API` in `.github/workflows/*.yml`. | none | no |
| BACKLOG-098 | Report schedules poller/beat | DONE | `services/report_schedule_runner.py:62` `CIP_REPORT_SCHEDULE_POLL_SECONDS` (`bb66af08`). | none | no |
| BACKLOG-097 | Set-based A3 stock / WoC observation | DONE | `alembic/versions/20260817_0017_weeks_of_cover_observation.py` (`01c69751`). | none | no |
| BACKLOG-096 | Tenant commercial profile UI | DONE | `endpoints/auth.py:286,294` `/tenant-commercial-profile` (`bb66af08`). | none | no |
| BACKLOG-095 | CPOR over-money-ceiling reapproval | DONE | `models/cpor.py:65` `needs_reapproval`, `20260801_0002` (`fcd6157c`). | none | no |
| BACKLOG-094 | Auto MAC + history-benchmark units | DONE | `services/cpor/intake_weighted_mac.py`, `cost_suggestion.py` (`cost_basis_drift`) (`a802627d`). | none | no |
| BACKLOG-093 | Case-scoped promo-load recon | DONE | `cpor_cases.py:1571` `/promo-load-recon`. The tab was remounted by N-0032 (`ff118ec6`). | N-0032 | no |
| BACKLOG-092 | CPOR paid vs owed recon | DONE | `payment_recon` wired in `cpor_cases.py` (`1bde00a3`). | none | no |
| BACKLOG-091 | Rename "Deal-stock landing" → "Over-plan intake" | PARTIAL | The API `over_plan_intake_*` aliases are kept. The UI label went back to `"Deal-stock landing"` at `PlanVsExecutedView.tsx:696` in `5e8c89fa` (2026-10-05). The original rename was `8110cb3b`. This contradicts `docs/COMMERCIAL_SEMANTICS.md:120` (A1-02). | N-0064 (terminal) | yes: which name stands |
| BACKLOG-090 | Channel Ops WoC grain mismatch | DONE | `channel_ops.py:394-413` `sellout_velocity_52wk_by_dist_product` per pair. | none | no |
| BACKLOG-089 | Cost per incremental unit | DONE | `services/cpor/incremental_unit_cost.py:75,91` (`65c2b8d3`). | none | no |
| BACKLOG-088 | Evidence `pod_date` to view/facts | DONE | `alembic/versions/20260802_0009_sticky_pod_evidence_current.py`. | none | no |
| BACKLOG-087 | GitHub required status check | OBSOLETE | Removed by Warren 2026-08-09 (no GitHub Pro). | none | no |
| BACKLOG-086 | PM bulk upsert `channel_id` CASE | OBSOLETE | No `channel_id` in `services/catalog/product_import_sync.py`, so the hazard cannot fire (`31b09689`). | none | no |
| BACKLOG-085 | Ops-list pagination chrome | DONE | `OPS_LIST_GRID_PAGINATION` in `admin/cst-steward/page.tsx`, `CstArticleAliasesSection.tsx`, `PoManagementView.tsx`. | none | no |
| BACKLOG-084 | Shared URL helpers | OBSOLETE | No consumer. Neither `useDebouncedUrlQuery` nor `skipLimitSearchParams` appears in `apps/web/src`. 085 shipped without them. | none | no |
| BACKLOG-083 | Customer merge companions | PARTIAL | The redirect follow exists in `services/merge_redirect.py`. `customer_related_master_groups` has only a stale `.pyc` and no source. `backfill_merged_customer_alias_seals.py` and `repair_open_channel_wrong_merge.py` are not in `apps/api/scripts/ops` (only `repair_merged_customer_leftovers.py` is). There is no related-name UI. | none | no |

### Doc/code contradictions found (findings, not fixes)

- **BACKLOG-140:** the entry says "mint was never built". The mint path has been on HEAD since `66003db9` (2026-07-10).
- **BACKLOG-137:** the entry says "cip `alembic upgrade head` pending". `docs/memory/CURRENT.md:11` has cip at `20261006_0024`.
- **BACKLOG-091:** the entry is marked Resolved, but `5e8c89fa` put the old label back in the UI.
- **BACKLOG-106:** the entry is still Parked but BACKLOG-116 superseded it. N-0069 still lists it.
- **`CONTEXT.md:29`:** says "tsc not exit 0" (2026-10-05). Measured exit 0 on 2026-10-07.

## 2. OPEN or PARTIAL with covered_by none, as proposed work packages

### 2a. No ledger node at all

| work package | ids | outcome | size | dependency |
|--------------|-----|---------|------|------------|
| Test honesty on cip_test | 144, 121 | The distributor-as-customer tests seed their own rows on `cip_test` and pass there. A non-split sheet has a regression test proving preview row_count equals apply row_count. | S | none |
| Live API in CI end-to-end | 099 | GitHub Actions starts the API against `cip_test` and runs the live wipe/products specs. | M | BACKLOG-100 gate (done) |
| Customer merge companions | 083 | A related-name worklist and clone-proven repair/backfill scripts complete the merge story after the alias seal. | M | BACKLOG-081 alias seal (outside this sweep; ship as a pair) |
| Lineup supersession hardening (trigger-gated) | 122, 120 | W2 refuses mixed-customer cases. Carry provenance gets a structured column if the notes are overwritten. | S | First W2 candidate pair. 120 needs migration approval. |

### 2b. Residual left on a terminal node (no live node owns it)

| work package | ids | outcome | size | dependency |
|--------------|-----|---------|------|------------|
| CPOR role separation | 136 | KAM/PM/Ken/Wayne are mapped onto IAM. PM edits pre-approval only, and Ken cannot write MAC or terms. | M | Warren's role mapping. Related to N-0082. |
| CPOR status and SOH rules | 139, 135 | Historical re-import does not overwrite a lifecycle transition (D-0035). The SOH check gets a tolerance flag and a VAT basis rule. | S | Warren's decisions on D-0035 Q3 and the tolerance/VAT basis |
| Lineup quantity column mapping | 105 | The PF/desktop template family reads `Total Qty`/month columns, not `Qty`, without changing global aliases. | S | Warren's mapping choice |
| Plan vs Executed tile name | 091 | One name for the A1-02 tile, matched across the UI and COMMERCIAL_SEMANTICS. | S | Warren picks the name |
| ScopeBar VERIFY clearance | VERIFY-debt register (BACKLOG-209) | An independent Opus VERIFY PASS, or a written Warren waiver, before `feat/ns-2-brief-nav-collapse` is promoted to `main`. | S | Opus availability (BACKLOG-211) |

Covered by a live node, so not listed above: BACKLOG-123 (N-0069). BACKLOG-130 is DONE; N-0076 extends it.

## 3. Counts

| measure | count |
|---------|-------|
| Rows in scope | 63 (62 entries + VERIFY-debt register) |
| DONE | 46 |
| PARTIAL | 6 (135, 136, 139, 121, 091, 083) |
| OPEN | 7 (register, 144, 123, 122, 120, 105, 099) |
| OBSOLETE | 4 (106, 087, 086, 084) |
| UNCLEAR | 0 |
| needs_warren = yes | 6 (135, 136, 139, 140, 105, 091) |
| OPEN/PARTIAL with no node (2a) | 6 ids in 4 packages |
| OPEN/PARTIAL with only a terminal node (2b) | 6 ids in 5 packages |
| Doc/code contradictions | 5 |
