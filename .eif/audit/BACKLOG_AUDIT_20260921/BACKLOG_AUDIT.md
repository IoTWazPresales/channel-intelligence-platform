# Backlog audit against the running tree — N-0030

**Run:** `BACKLOG_AUDIT_20260921` · **Actor:** `backlog-audit-001` · **Date:** 2026-09-21
**Tree:** `feat/ns-2-brief-nav-collapse` @ `492795c` · **DB:** `cip` (read-only; `current_database()` printed before every batch)
**Scope:** every `docs/BACKLOG.md` entry whose Status cell did not already read closed/resolved/done/not-needed/removed/superseded/shipped — **100 entries** of 176.

**Verdicts.** `DONE` = proven in tree/DB, close · `SUPERSEDED` = replaced by an accepted decision or completed node, close · `DROP` = propose dropping, Warren confirms · `NECESSARY` = required for a feature Warren has asked to build or for correctness · `HELPFUL` = real but trigger-gated · `EIF` = out of CIP scope by the entry's own text · `HELD` = conflicts with a node acceptance criterion; do not act.
**Basis.** `VERIFIED` = grep, file, or measured `cip` row count cited · `ASSERTED` = judgment from the entry and tree context, no fresh measurement.

## 1. Corrections to prior claims (read these first)

| Claim | Truth | Evidence |
|---|---|---|
| "P1 sign-off still needs Warren" (this session, earlier) | **P1 exited 2026-08-01.** DSI and Lineups are deliberate leave-alone, not unsigned. | `ROADMAP.md:450`, `CONTEXT.md:438`, `DATA_CENSUS.md` sign-off log |
| BACKLOG-034: 319 inverted launch/retire windows | **2,795** rows today (`retired_date < launch_date`) — ~9× growth since recorded | `cip` measure |
| BACKLOG-066: cases #39/#40 duplicate | Both ids **no longer exist** (36 cases, ids 7–146, 7 superseded). The same workbook now maps to 114/115/116 + 141→117 via the supersession workflow; `lineup_duplicate_partition_repair.py` exists. | `cip` measure; tree |
| BACKLOG-142: `apps/web` typecheck red | `tsc --noEmit` **exit 0** | measured 2026-09-21 |
| BACKLOG-140: "code subordinate via `SHOW_CUSTOMER_CODE`" | Now **name-only**; flag pinned `false` | `492795c` |
| BACKLOG-077: parked | Shipping mailbox slice is **wired and live** (`services/mailbox_ingest/*`, `mailbox_ingest_runner.py`, registered in `main.py`); DSI batch-propose slice still open | tree |

## 2. Conflicts with node acceptance criteria (flag, do not act)

- **BACKLOG-200** (delete `MasterColumnPickerDialog`) vs N-0029 AC: *"Do not unify MasterColumnPickerDialog and ColumnSelectorModal."* → **HELD** for the N-0029 review.
- **BACKLOG-193** (AG Grid range selection + Excel export) vs N-0029 AC: *"Do not add range selection or Excel export (Enterprise module absent)"* **and** Warren's R0/month constraint (Enterprise is a paid licence) → **DROP**.

## 3. Classification — all 100 entries

| ID | Verdict | Basis | Evidence / note |
|---|---|---|---|
| 135 | NECESSARY | VERIFIED | `fact_inventory_customer` **0** rows; `fact_customer_sellthrough` **1,823**. Point MAC-check at CST. Stage 4.3 |
| 136 | NECESSARY | VERIFIED | Effective `cip_auth_mode=stub`; stub resolves `admin@local`. Feature 1 / Stage 3.2 |
| 137 | NECESSARY | VERIFIED | `cpor_case_line` has **no** `window_*`/`effective_*` columns. Migration, Warren approves. Stage 4.4 |
| 138 | **DONE** | VERIFIED | `services/cpor/case_supersession.py`; supersede + `/supersede/restore` endpoints in `cpor_cases.py`; `CporCaseSupersedeDialog` on the desk. `superseded_by_case_id` set on **0** rows — writer exists, unexercised. |
| 139 | NECESSARY | VERIFIED | **4** disagreeing rows: settled/ended ×2, cancelled/draft ×1, cancelled/ended ×1. Stage 4.2 |
| 140 | NECESSARY (partial) | VERIFIED | Display half done (`492795c`, name-only). Mint half open. **14** TMP-coded active customers of 4,949 (`dim_customer.code`). Stage 4.5 |
| 141 | NECESSARY | VERIFIED | `shipment_evidence.py:203,228` still `require_roles(Role.ADMIN)`. Stage 3.2 |
| 142 | **DONE** | VERIFIED | `tsc --noEmit` exit 0 |
| 143 | HELPFUL | VERIFIED | `cip_test` and `cip_merged_leftover_repair` both still exist; `.tmp_lf_rerun.txt` gone; `feat/shipping-mailer-recipients` exists local + remote |
| 144 | HELPFUL | VERIFIED | Test file exists; `cip_test` still lacks the seed rows |
| 133 | NECESSARY | VERIFIED | `customer_leftover_repair.py` exists with **zero callers** outside itself — not wired to import-complete. Stage 3.7 |
| 134 | **DONE** (fold into 133) | VERIFIED | alias→merged-customer count **0** today; the recurring assertion is 133's job |
| 130 | **DONE** | VERIFIED | Entry's own TRIGGER: "Fired and closed 2026-08-13"; roadmap P5 records residual closed |
| 123 | HELPFUL | ASSERTED | Trigger (Unit 5b PASS + disti-merge grid) not fired; pairs with Stage 9 |
| 122 | HELPFUL | ASSERTED | W2=0 today; trigger not fired |
| 121 | HELPFUL | ASSERTED | Trigger not fired |
| 120 | HELPFUL | ASSERTED | Optional column; trigger not fired |
| 106 | HELPFUL (partial) | VERIFIED | `PoAutoLinkProposalsSection.tsx` exists; S1–S14 parity ungraded since 2026-08-03 |
| 105 | HELPFUL | ASSERTED | Template-family mapping decision; Stage 6.5 |
| 103 | HELPFUL — verify | VERIFIED (partial) | Half-year fan-out lives in the **shared** `lineup_case_parser.py` / `lineup_half_year_quantity.py`, not only bulk. Needs one unified 1H import smoke to close. Stage 6.3 |
| 099 | HELPFUL | VERIFIED | No `uvicorn` in `.github/workflows/*.yml` |
| 083 | NECESSARY (merge wave) | VERIFIED | Not in tree. Stage 4.8 / 9 |
| 081 | NECESSARY (merge wave) | VERIFIED | `alias_seal` absent from tree; consult READY per memory. Stage 4.8 |
| 080 | HELPFUL → warranted | ASSERTED | P4 is live so the "CST volume" trigger has effectively fired; batch endpoints absent from `cst_steward.py` |
| 078 | HELPFUL | ASSERTED | Trigger-gated on weekly soak |
| 077 | PARTIAL | VERIFIED | Shipping slice **live**: `services/mailbox_ingest/{graph_auth,graph_fetch,graph_login,imap_fetch,shipment_intake}.py`, `mailbox_ingest_runner.py`, wired in `main.py`. DSI batch-propose slice open |
| 073 | **DONE** (coverage note) | VERIFIED | `import_job_bulk_delete.py` previews and deletes `fact_sales_sellout`, `fact_inventory_distributor`, `fact_competitor_price` rows by job with local-storage unlink. Residual: confirm shipment/CST/lineup fact coverage if ever needed |
| 067 | HELPFUL | ASSERTED | Trigger = re-audit or multi-tenant onboarding; Stage 10 |
| 066 | **DONE** | VERIFIED | ids 39/40 gone; supersession used (7 superseded cases); repair service in tree |
| 055 | HELPFUL | ASSERTED | Needs post-backfill distribution; Stage 6.5 |
| 059 | HELPFUL | ASSERTED | Before tenant #2; Stage 10 |
| 060 | HELPFUL (partial) | VERIFIED | Dialog still `onClose()` at `:269`; `:332` points at the activity bell. Completion panel open. Stage 6.4 |
| 053 | HELPFUL | ASSERTED | Business-confirmation gated |
| 052 | HELPFUL | ASSERTED | Real-workbook gated |
| 051 | HELPFUL | ASSERTED | Reconciliation report; feeds 049 |
| 049 | HELPFUL | VERIFIED | Writer side exists (`apply_exclusion` in `dsi_apply_completion.py`); reader/worklist UI absent |
| 048 | HELPFUL → Stage 3.6 | ASSERTED | Celery parity audit; belongs with the ops safety net |
| 046 | NECESSARY (next ACZA upload) | VERIFIED | `_load_frames_for_job` has no sheet allowlist / BOM handling. Stage 4.7 |
| 037 | HELPFUL | VERIFIED | `_resolve_dsi_product_post_tiers` not in tree |
| 004 | HELPFUL | ASSERTED | Gated on PM core-loop re-run + approval |
| 006 | HELPFUL | ASSERTED | Perf trigger not observed |
| 008 | HELPFUL | ASSERTED | Cross-module hints; trigger not fired |
| 009 | RE-HOME → Stage 10 | ASSERTED | PIM typed attributes belong with P6 config, not a standalone item |
| 010 | RE-HOME → Stage 10 | ASSERTED | Destructive ~2M-row drop; only after 009 and Warren approval |
| 011 | HELPFUL | VERIFIED | `pm_commit_catalog.py:72,294` still per-row `db.flush()` |
| 013 | **DONE** | VERIFIED | P4 CST shipped: `/admin/cst-steward`, `customer_sell_through_apply.py`, 1,823 facts |
| 014 | DROP (proposed) | VERIFIED | `template_definitions.py` still "intentionally deferred"; no business request in 4 months |
| 016 | HELPFUL | ASSERTED | Per-row approval list; unchanged |
| 017 | DROP (proposed) | ASSERTED | Embedding dedupe; no evidence current rates are unacceptable |
| 018 | HELPFUL (trivial) | ASSERTED | Index names not greppable in the doc; apply on `EXPLAIN` trigger |
| 019 | HELPFUL | ASSERTED | Umbrella of historical-lineup slices; several delivered since — re-slice before use |
| 020 | HELPFUL — verify | VERIFIED (partial) | "Full PM revisit is not yet supported" string gone; `isJobRevisitMode` exists for `historical_lineup`. PM-specific `?job=` revisit needs one smoke |
| 021 | NECESSARY → 136 | ASSERTED | Planner RBAC folds into the Stage 3.2 role matrix |
| 031 | HELPFUL → Stage 3.6 | VERIFIED | No `/admin/data-health` API or page |
| 032 | HELPFUL → Stage 3.6 | ASSERTED | Runbook only |
| 057 | HELPFUL | VERIFIED | `shipment_evidence_line` still **50** columns; soak-gated |
| 058 | HELPFUL | VERIFIED | Depends on 057 |
| 062 | NECESSARY (policy) | VERIFIED | Diagnostic exists in `shipment_plan_d_cutover.py`; Warren approves remediation. Stage 4.6 |
| 063 | HELPFUL | VERIFIED | v1 in `shipment_evidence.py`; v2 semantics undefined |
| 064 | HELPFUL | VERIFIED | No change-event UI in web |
| 065 | HELPFUL | VERIFIED | `monthly_phased` not in tree |
| 034 | NECESSARY — **escalate** | VERIFIED | **2,795** inverted windows (was 319). Stage 4.1 |
| 149 | **SUPERSEDED** | VERIFIED | Six-container spine replaced by domain IA (N-0013, D-0007/D-0010); `navConfig` top level is Overview / Stock & Sell-through / Supply & Inbound / …; no `/brief`. Delivered as N-0004 |
| 150 | **SUPERSEDED** | VERIFIED | Same; N-0007 complete; no `/stock` container route |
| 151 | **SUPERSEDED** | VERIFIED | N-0008 complete |
| 152 | **SUPERSEDED** | VERIFIED | N-0009 complete |
| 153 | **SUPERSEDED** | VERIFIED | N-0010 **rejected**; no `/response` |
| 154 | **SUPERSEDED** | VERIFIED | N-0011 complete |
| 160 | NECESSARY (one-liner) | VERIFIED | `market.py:12` reports `competitor_price_import: ready`; `fact_competitor_price` **0** rows, no template. Stage 2.8 |
| 156 | NECESSARY (honesty) | VERIFIED | `LineupScopeBar.tsx:106` inert **Apply**, no handler/disabled/tooltip. Stage 2.8 |
| 157 | HELPFUL (docs) | ASSERTED | Design-language rule; write with 2.8 |
| 158 | NECESSARY | VERIFIED | Design-lab still 25 tsx; primitives promoted to production but lab copies remain. Stage 2.9 |
| 161 | NECESSARY | VERIFIED | `design-lab/primitives/{DomainHeader,HeadlineFigure,Panel,EntityContextPanel,charts,controls,CapabilityStatus,…}`, `design-lab/shell/{CommandPalette,LabShell}` duplicate production. Stage 2.9 |
| 159 | EIF | — | Out of CIP scope by text |
| 166 | EIF | — | Out of CIP scope |
| 167 | EIF | — | Out of CIP scope |
| 168 | HELPFUL → gate | VERIFIED | Effective `ai_assist_enabled=False`; `_anthropic_client()` returns `None` at `:57/:61`. Must fail loud **before** the flag is flipped. Stage 3.6 |
| 169 | EIF | — | Out of CIP scope |
| 170 | EIF (accepted) | — | Operator decision recorded; N-0006 stays `proposed` |
| 171 | EIF | — | First item of the EIF-repo session |
| 172 | EIF | — | `.cursor/hooks` control plane |
| 173 | EIF | — | Guard fingerprint |
| 174 | EIF | — | R1 |
| 175 | EIF | — | R2 |
| 176 | EIF | — | R3 |
| 177 | EIF | — | R4 |
| 178 | HELPFUL (feature) | VERIFIED | `fact_inbound_shipment.line_state` only `shipped` 13,477 / `open_order` 1,775. Stage 7.5 |
| 179 | HELPFUL (feature) | ASSERTED | Stage 7.5 |
| 183 | NECESSARY (feature 8) | VERIFIED | `fact_competitor_price` 0 · `customer_listing` 218 · `listing_observation` 168. Buildable with honest empties. Stage 7.1 |
| 184 | NECESSARY (feature 8) | ASSERTED | Stage 7.2 |
| 185 | NECESSARY — **data-gated** | VERIFIED | `cpor_claim_evidence_line` **0** rows vs **211** settled cases. Unlocks with Warren's data drive, not code. Stage 7.4 |
| 186 | NECESSARY (decision) | ASSERTED | Stage 7.3 |
| 187 | HELPFUL | ASSERTED | Trigger-gated |
| 188 | HELPFUL | ASSERTED | Trigger-gated |
| 190 | NECESSARY (feature 9) | ASSERTED | Stage 6.2 |
| 193 | **DROP** | VERIFIED | Paid licence breaks R0; N-0029 AC forbids. See §2 |
| 198 | NECESSARY (Warren decision) | ASSERTED | `catalog_product` grain; Stage 10 |
| 199 | NECESSARY (small) | VERIFIED | `MarketSurface.tsx:272/1230`. Stage 2.6 |
| 200 | **HELD** | VERIFIED | N-0029 AC conflict. See §2 |
| 201 | NECESSARY — decided | — | Warren 2026-09-21: **all columns**. Stage 2.4 |
| 202 | NECESSARY — decided | — | Warren 2026-09-21: **merge the five tabs onto the desk**. Stage 2.7 |

## 4. Totals

| Verdict | Count |
|---|---|
| DONE (close) | 7 — 130, 134, 138, 142, 066, 073, 013 |
| SUPERSEDED (close) | 6 — 149, 150, 151, 152, 153, 154 |
| DROP (proposed, Warren confirms) | 3 — 193, 014, 017 |
| RE-HOME → Stage 10 | 2 — 009, 010 |
| HELD (AC conflict) | 1 — 200 |
| EIF (out of CIP scope) | 12 — 159, 166, 167, 169, 170, 171, 172, 173, 174, 175, 176, 177 |
| NECESSARY | 30 |
| HELPFUL (trigger-gated) | 39 |

Of the 100 "open" entries, **31 are not CIP build work** (done, superseded, dropped, held, or EIF). The staged plan (`docs/design/STAGED_WORK_PLAN.md`) is built on the remaining 69.

## 5. Method notes and limits

- `cip` was read only; every batch printed `current_database()` = `cip` first.
- `.eif/runtime/programme/__pycache__` was created by this run's analysis imports and tripped `RUNTIME_INTEGRITY`; removed (untracked, gitignored, created 13:51 today). `PYTHONDONTWRITEBYTECODE=1` on every `program.py` call since.
- P5 observation span not measured: `listing_observation` has `fetched_at`, not `observed_at`; not needed for any verdict.
- `ASSERTED` rows are honest judgment from the entry text and neighbouring tree evidence; they were **not** re-measured and should not be cited as proof.
- Node N-0030 was created with an explicit `--id` because the ledger's `ids.node` counter reads **5** against 29 nodes (pre-existing; cf. BACKLOG-171 class of defect).
