# Backlog — intentionally deferred work

**Scope:** Intentionally deferred / future work. Each entry has a **trigger condition** for when to resume. Distinct from **`docs/memory/CURRENT.md`** (what is true now), **`docs/ROADMAP.md`** (phase-level path — authoritative for what's next), and **`CONTEXT.md`** (changelog router). Legacy phased notes may still exist under `docs/memory/ROADMAP.md` — prefer `docs/ROADMAP.md`.

**Entry template:** ID + title · status/parked-date · effort · the idea · why it matters (and why deferrable) · what the work is · regression traps / hard constraints · behavior to retain · out-of-scope · **TRIGGER**

---

## BACKLOG-129 — CST unmappable products → catalogue-gap worklist (`ignore_no_catalogue`)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed** · 2026-08-08 · CST source on catalogue-gap worklist + ignore_no_catalogue stamp |
| **Effort** | Medium |
| **Source** | Warren (2026-08-08 Takealot WEEK pilot): unmappable CST tokens must be ignored and filed into the missing-PM / Product catalogue gaps surface — same as DSI `ignore_no_catalogue`, not left as permanent open steward on the import job. |
| **Idea** | Extend `product_master_gap_worklist` with `source=cst` (CST `ImportEntityMappingCandidate` product tokens status `needs_review`/`ignored`); CST Bulk ignore stamps `context.steward_ignore_reason_code=ignore_no_catalogue` (and optional `catalogue_gap=true`); gap Confirm-resolve can clear them after PM lands. |
| **Why it matters / deferrable** | Without this, CST ignore is job-local only — operators lose the token when the job scrolls away. Deferrable while WEEK pilot uses job Bulk ignore; wire before multi-retailer CST scale. |
| **What the work is** | (1) `ignore_cst_candidate_sync` / bulk ignore accept reason code default `ignore_no_catalogue`; (2) `_merge_cst_tokens` in `product_master_gap_worklist.py` + API `source=cst`; (3) UI filter chip on `/admin/product-master-gaps`; (4) gap resolve applies to CST candidates + re-opens staging when PM matches. |
| **Regression traps** | Never auto-create dim_product from CST; FLAG≠BLOCK — ignored tokens must not block apply of resolved lines; do not fork DSI ignore UI — reuse gap worklist. |
| **Behavior to retain** | Job steward Bulk ignore still works; resolved CST lines still apply; multi-token resolve (sales model / barcode / sku) unchanged. |
| **Out of scope** | PM catalogue load itself; auto-map accessories; changing DSI/shipment gap sources. |
| **TRIGGER** | — closed (Warren continue 2026-08-08). |

---

**Prune note (2026-07-20):** Removed shipped items (001, 005, 007, 012, 015, 022–024, 028, 030, 033, 035–036, 038–042, 043, 050, 056, 061, 061-U2, 069, 072) and ignored Supabase/deploy items (002, 003). Plan D follow-ons renumbered **057-D4** / **058-D5** to end the 057/058 ID collision with bulk-backfill entries. Full disposition archive: `.tmp/backlog_prune_consult_opus_response.md`.

**ID remap (2026-07-27 merge):** On merge of `feat/dsi-unified-multifile`, that branch’s **074** (email ingest) and **075** (layout-coalesce) were renumbered to **077** / **078** because this branch already used 074/075 for CST E2 / Unit F (shipped) and **076** for amount-scale junk.

**P0 extract (2026-07-29 / D-021 / D-022):** From `feat/ops-master-grid-shell-parity` + stash `park-dsi-asus-dealer-name-automap` — BACKLOG-**079**–**086**. Branch **deleted** local + remote after fuller extract (D-021). Channel-ops KPI cards + `shippingUtcDates.ts` **not** backloged (superseded by main commercial KPI rebuild).


## BACKLOG-123 — Migrate promote/merge surfaces onto ResolutionWorklist

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-05 |
| **Effort** | Large |
| **Source** | PROGRAM-A Unit 5a / D-036; Phase-0 seam rows 2–6; CONSULT mandate that distributor-merge auto-link grid is the **2nd consumer** validating the non-PO contract seams (target selection + async slot). |
| **Idea** | After PO pilot (Unit 5b) proves the presentation contract, migrate (in order): (1) distributor-merge auto-link grid when built — exercises `requiresTarget` + `ResolutionAsyncApplyAdapter`; (2) CustomerPromoteDialog; (3) CustomerBulkPromoteDialog; (4) DistributorPromoteDialog; (5) DistributorBulkPromoteDialog. |
| **Why it matters / deferrable** | Four promote dialogs + merge grid are bespoke today; leaving them off the shared worklist re-fossils PO-shaped naming. Deferrable until 5b VERIFY PASS and merge grid exists (or promote UX rewrite is scheduled). |
| **What the work is** | Mount `ResolutionWorklist` with promote/merge actions (`requiresTarget`, `targets`, `renderTargetPicker`); wire sync adapters (chunk 500 for bulk) or async Celery for merge; retire bespoke dialog shells once parity proven. |
| **Regression traps** | Do not genericize `importJobId` engine; never auto-create master on promote/merge; do not invent importer-prefixed files under `features/import-steward/`; keep Unit-2 protection semantics if any contested rows appear. |
| **Behavior to retain** | Preview→Promote confirm false→true; TMP visibility; merge survivor selection; FLAG≠BLOCK. |
| **Out of scope** | Migrating promote/merge inside Unit 5a or 5b; absorbing DSI into this contract. |
| **TRIGGER** | Unit 5b VERIFY PASS **and** (distributor-merge auto-link grid is built **or** Warren schedules promote-dialog UX rewrite). Also resume S10 slot build when merge grid needs Celery, or if PO batch >500 / p95 apply >30s. |
| **Note** | Unit 6b is the **first live** `opts.target` consumer (customer-token stamp). Promote/merge migration remains parked per TRIGGER. |

---

## BACKLOG-124 — Tokenless customer acquisition for blank lineup customer_token

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed** · 2026-08-08 · Mechanism D on `feat/backlog-124-empty-token` |
| **Effort** | Medium |
| **Source** | PROGRAM-A Unit 6 CONSULT Q0/D6; Unit 6b scope — empty_token bucket (esp. case 127 matched-null lines) |
| **Idea** | Acquisition path for lineup lines with blank/null `customer_token` that still need a customer stamp (cannot mint `CustomerSourceTokenAlias` without a token). Hint: D6 showed 13/13 medium POs were single-customer on ship side. |
| **Why it matters / deferrable** | Blocks residual `customer_unresolved` where ship is resolved but lineup token is empty. Stamp (C) cannot run. Deferrable while stampable tokens (clean/specificity) clear first. |
| **What the work is** | Steward stamps `customer_id` by `line_ids` with explicit confirm; ship/PO customers are hints only; never invent `customer_token`; never mint alias; never auto-create dims. API: `…/tokenless/preview|apply`. Worklist: per-case empty_token items with free pick. |
| **Regression traps** | Never auto-create dim_customer; never invent tokens silently; FLAG≠BLOCK; do not use Mechanism C stamp path for blank tokens. |
| **Behavior to retain** | Empty-token rows remain visible in worklist; stamp enabled via tokenless path only after explicit target pick + reason + confirm. |
| **Out of scope** | Unit 6b stamp/alias path for non-empty tokens; Drive Control rename; DAP confirmer. |
| **TRIGGER** | — closed. |

---

## BACKLOG-122 — W2 same-customer predicate uses majority line customer (no case.customer_id)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-05 |
| **Effort** | Small–Medium |
| **Source** | PROGRAM-A Unit 4 discovery: `commercial_lineup_case` has no `customer_id` column; W2 A1 same-customer hard predicate resolves via majority `commercial_lineup_line.customer_id`. A mixed-customer case could pass on majority alone. W2=0 today so not live. |
| **Idea** | Strengthen W2 customer equality: require identical customer *sets* (or explicit single-customer cases only), and/or add a case-level customer identity when the domain warrants it — without inventing silent auto-create. |
| **Why it matters / deferrable** | Majority-only can mis-classify a multi-customer file as same-customer for prefix supersession. Deferrable while no W2 candidates exist. |
| **What the work is** | When W2 fires: compare full customer distributions (or refuse W2 when either case has >1 non-null customer); optional schema only if Warren approves. |
| **Regression traps** | Do not treat null-majority open-channel as a shared customer without OPEN_CHANNEL canon rules; do not weaken A1 hard predicate. |
| **Behavior to retain** | A1: same stripped base + same period + SAME CUSTOMER; differing → leave_live accept-both. |
| **Out of scope** | Fixing this before the first real W2 candidate pair. |
| **TRIGGER** | First time Unit 4 / contested residual W2 produces a candidate pair. |

---

## BACKLOG-121 — Non-split sheets: preview row_count from parser #1 vs apply parser #2

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-05 |
| **Effort** | Medium |
| **Source** | PROGRAM-A Unit 3 CONSULT latent finding: even for non-split sheets, preview `row_count` historically came from parser #1 while apply persists parser #2 rows — they can disagree; NB 221==221 was coincidence. D-034 fixed multi-BU identity only. |
| **Idea** | For all bulk-backfill proposals (including single-BU sheets), derive `row_count` from apply-parser (#2) rows when `parser_ctx` is present so preview totals always match apply. |
| **Why it matters / deferrable** | Silent preview/apply count drift on non-split sheets misleads steward review. Deferrable while multi-BU identity (108/D-034) is the active corpus risk. |
| **What the work is** | Extend D-034 identity_rows path to non-split proposals; regression tests with engineered header/summary divergence. |
| **Regression traps** | Do not reintroduce cross-parser aligner; do not fuzzy-match. |
| **Behavior to retain** | D-034 multi-BU native `source_row_number`; subset-sheet exclusion. |
| **Out of scope** | Unifying the two parsers into one module. |
| **TRIGGER** | Steward reports preview vs applied line-count mismatch on a single-BU sheet, or next bulk-backfill corpus restore. |

---

## BACKLOG-119 — Competition detector flags multi-BU shared POs as conflicts (phantom)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed** · 2026-08-05 · shipped D-033 |
| **Effort** | Medium |
| **Source** | 9→122 unit Phase D: 33 competing PO norms; refined vs shipment product∩lineup: **25** class (a) multi-BU legitimate (NB+NR both hit shipped products), **7** cross-period, **1** same-BU same-period (`PURMIDR26009979` / 9·121·122·128). Detector = residual classifier `len(cases for po_norm)>1` (`.tmp/clear_211_queue.py` ~524–536); propose engine emits multi-case proposals without shipment consult |
| **Idea** | When classifying “competition”, consult shipment product evidence: if ≥2 claiming cases each overlap shipped products on that PO and BUs differ, treat as multi-BU share (not a pick-one conflict). Keep genuine same-BU / cross-period queues. |
| **Why it matters / deferrable** | 25/33 residual “conflicts” are phantom under Warren’s multi-BU-share-PO rule. Inflates steward queue. Deferrable until carry (118) + 9→122 land. |
| **What the work is** | Classification helper for residual/UI chips; **do not** change match key (BU stays out). Optional UI badge “multi-BU shared”. |
| **Regression traps** | Do not auto-accept both without steward; FLAG≠BLOCK for over-plan. Do not fold cross-period into (a). |
| **Behavior to retain** | CRAD-primary key; BU not in key; multiple proposals per PO allowed. |
| **Out of scope** | Changing propose SQL; bulk-select guard (115/110). |
| **TRIGGER** | Immediate — 118 + 9→122 landed; or Warren starts residual competition triage. |
| **Closed** | Live re-derive after 9→122: 35 multi-case → **13 contested** / **22 multi_bu_shared** / 0 indeterminate. `lineup_po_competition.py` + wire in `po_auto_link_proposals`. D-033. Residual decision list in CONTEXT. UI chip polish still optional (BACKLOG-113). |

---

## BACKLOG-120 — Dedicated supersession_carry provenance column (optional)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-04 |
| **Effort** | Small |
| **Source** | BACKLOG-118 B1: carry records provenance in existing `commercial_lineup_case_po.notes` (`supersession_carry:from_case=<id>`). No schema change this unit. |
| **Idea** | If notes collide with steward free-text, add a dedicated nullable provenance column (or JSONB) for carry/auto-link origin. |
| **Why it matters / deferrable** | Notes work today; only matters if operators routinely edit link notes and overwrite carry markers. |
| **What the work is** | Migration + backfill from notes prefix; update carry writer. |
| **Regression traps** | Do not migrate without Warren approval; never delete loser links. |
| **Behavior to retain** | Copy-not-move carry; unique (case_id, purchase_order_id). |
| **Out of scope** | Changing carry semantics. |
| **TRIGGER** | Steward reports notes overwrite / needs structured provenance filter. |

---

## BACKLOG-118 — Supersession must carry commercial_lineup_case_po to winner

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed** · 2026-08-04 · shipped D-032 |
| **Effort** | Medium |
| **Source** | 9→122 unit A2 STOP: `lineup_bulk_backfill_apply.py` 377–382 only sets `superseded_by_case_id` + `commercial_status='superseded'`; no carry/move of `commercial_lineup_case_po`. Case 9 has **28** PO links; case 122 has **0**. Active filters would orphan links if 9 superseded without carry. D-031. |
| **Idea** | On soft-supersession of a loser→winner, copy (or reassign) `commercial_lineup_case_po` rows to the winner idempotently on `(case_id, purchase_order_id)`; leave audit trail; do not delete PO master rows. Prefer a named service used by bulk apply + steward ops. |
| **Why it matters / deferrable** | Without carry, superseding po_issued cases silently unlinks POs from active planned/coverage consumers. Not deferrable for D2 — **blocked**. |
| **What the work is** | Service + call from supersession path; steward audit; test with real case_po rows; then resume 9→122 + f3 apply. |
| **Regression traps** | Never hard-delete cases; never drop PO numbers; unique (case_id, purchase_order_id); survivors 7/90 untouched unless Warren says. |
| **Behavior to retain** | Soft-supersede via existing fields; `link_case_to_existing_po` idempotency semantics. |
| **Out of scope** | Hand-written SQL inserts as one-off; changing competition detector. |
| **TRIGGER** | Immediate — next unit before any 9→122 / po_issued D-030 supersession. |
| **Closed** | `soft_supersede_lineup_case` + `carry_case_po_links_on_supersession`; wired bulk apply; clone C2–C6; cip 9→122 (28/28); f3→case 145 2025 Q4; D-032. Provenance via notes → BACKLOG-120. |

---

## BACKLOG-117 — PO auto-link Review dialog omits case id / source file / competitors


| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Small |
| **Source** | Browser queue unit: Review on `P2605495` / OPEN_CHANNEL showed customer, period, confidence, reason, PO units, matched products — **no case_id, no `file_name`, no competing-case list** (`PoAutoLinkConfirmDialog` ~L259–370) |
| **Idea** | Show case id + source file + sibling competing proposals for the same PO before Confirm. |
| **Why it matters / deferrable** | Operator cannot three-source-check from the dialog alone; must leave UI. Deferrable while Warren decides NB↔NR offline. |
| **What the work is** | Extend confirm + row chips; optional link to lineup case page. |
| **Regression traps** | Do not invent drawer chrome; keep confirm sync path until S10/S11 addressed. |
| **Behavior to retain** | Optional notes; matched products table. |
| **Out of scope** | Full import-steward drawer migration (BACKLOG-116). |
| **TRIGGER** | Next browser accept session for residual competitions. |

---

## BACKLOG-116 — PO auto-link panel is not on STEWARD_EXPERIENCE_CONTRACT S1–S14

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Large |
| **Source** | Browser queue unit grading vs `docs/STEWARD_EXPERIENCE_CONTRACT.md`: panel is bespoke `PoAutoLinkProposalsSection` cards, not `import-steward` engine |
| **Idea** | Level PO auto-link triage to steward engine slots (or explicitly Warren-waive rows with dated waiver lines). |
| **Why it matters / deferrable** | Contract gaps block VERIFY PASS; operators feel friction vs DSI/shipment. Deferrable until residual queue policy is settled. |
| **What the work is** | Gap analysis → shared workspace / drawer / bulk preview / async progress as required; or waive. |
| **Regression traps** | Do not fork `Dsi*`/`Shipment*` into `import-steward/`; extract generics only. |
| **Behavior to retain** | CRAD propose; dismiss/restore; over-plan copy; chunked apply. |
| **Out of scope** | Changing match key / BU-in-key. |
| **TRIGGER** | Warren prioritizes steward-engine parity for PO auto-link after residual policy decisions. |

---

## BACKLOG-115 — Select-all-high / bulk Link ignores competition + survivor policy

| Field | Detail |
|-------|--------|
| **Status / parked** | **Done** · 2026-08-05 (PROGRAM-A Unit 2) |
| **Effort** | Medium |
| **Source** | Browser unit: **Select all high** selected **81** including competing POs and survivor cases **7/9/90**; no competition warning; bulk confirm breakdown is customer counts only (`openBulkConfirm` / `bulkConfirmBreakdown` ~L978–995) |
| **Idea** | Exclude survivors/`po_issued` from select-all; flag or block multi-case same-PO selections; preview competing case ids before apply. |
| **Why it matters / deferrable** | One click would decide Warren conflicts + mutate survivors (policy). Deferrable while agents refuse bulk on residual. |
| **What the work is** | Selection filters + bulk preview conflict rows; wire BACKLOG-110 guard. |
| **Regression traps** | Do not auto-pick winners; FLAG≠BLOCK for over-ship stays. |
| **Behavior to retain** | Select-all-high for clean solo queues. |
| **Out of scope** | Auto-supersede from UI. |
| **TRIGGER** | Before any production bulk accept of residual 92, or with BACKLOG-110. |
| **Done note** | Property-based `bulk_protection` on proposals; select-all excludes selection_protected; bulk confirm lists excluded; competition chips via payload. |

---

## BACKLOG-114 — Period filter defaults to current quarter and hides residual queue

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Small |
| **Source** | Browser unit: expand panel → Period=`26Q3` via `useState(() => currentQuarterLabel())` at `PoAutoLinkProposalsSection.tsx:797`; Select all high disabled until period cleared; residual 2025/Q1–Q2 proposals invisible |
| **Idea** | Default period empty (or “all”) when opening triage; keep optional current-quarter quick chip. |
| **Why it matters / deferrable** | Operators believe the queue is empty/small. Deferrable while documented workaround (clear Period + Refresh) exists. |
| **What the work is** | Change initial state + empty-state copy; optional persist last filter in `cip.*` localStorage. |
| **Regression traps** | Do not break coverage gap worklist period defaults elsewhere. |
| **Behavior to retain** | Period/customer/confidence filters. |
| **Out of scope** | Server-side default period. |
| **TRIGGER** | Next PO auto-link UX polish unit. |

---

## BACKLOG-113 — PO auto-link has no competition / version-prefix signal in the list

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Medium |
| **Source** | Browser residual: 33 competing PO norms all RULE-DOES-NOT-APPLY (NB↔NR / different base / survivor); UI shows per-customer cards with no “competes with case X” chip; D-030 winners already applied offline |
| **Idea** | Surface `conflicts` / competing case ids + file base/prefix on rows and group headers so operators can apply D-030 / leave Warren conflicts. |
| **Why it matters / deferrable** | Without signal, Select-all-high looks safe. Deferrable while residual is Warren-only. |
| **What the work is** | API already has conflict hints in warren export; expose on propose payload + chips. |
| **Regression traps** | Do not auto-apply version rule from UI without confirm. |
| **Behavior to retain** | Soft-supersede via `superseded_by_case_id` (D-030). |
| **Out of scope** | Deciding NB vs NR. |
| **TRIGGER** | Warren wants browser-led residual triage after NB↔NR policy. |

---

## BACKLOG-112 — Auto-link `customer_unresolved` when ship is resolved but lineup line customer is null

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed steward-complete** · 2026-08-07 · Unit 6c (D-038/D-039). Distributor-token residual stamped OC+`line.distributor_id`; W4 false stamps 5767/5768 revoked+restamped; free-picker residual remains for retailer/no-dim tokens; empty_token → BACKLOG-124. Count need not be 0. |
| **Effort** | Medium |
| **Source** | Clear-211 unit: all 17 medium proposals have `fact_inbound_shipment.resolved_customer_id` + exact `customer_source_token_alias` hits; align still `unresolved` because matched lineup lines lack `customer_id` |
| **Idea** | Steward path to stamp lineup line customer from the already-resolved shipment customer (exact, no fuzzy) then re-propose/accept; or surface this as a distinct reason (`lineup_customer_missing`). |
| **Why it matters / deferrable** | Blocks ~8–17 residual proposals that look “unresolved” but are not alias misses. Deferrable while Warren clears NB↔NR competitions first. |
| **What the work is** | Lineup steward customer apply for matched products; do not auto-create dims. |
| **Regression traps** | Exact match only; FLAG≠BLOCK for over-ship; never touch survivors without override. |
| **Behavior to retain** | CRAD-primary match key; BU not in key. |
| **Out of scope** | Fuzzy customer match; ZA legal-form auto-merge as blocker. |
| **TRIGGER** | — closed. Free-picker leftovers + 124 empty_token are separate. |
| **Closed** | Unit 6c: classifier + dual-write stamp; clone C1–C9; cip D1–D7. Residual free-picker: `jd furn`, `pick & pay`, `sadc - superdisti`, `sadc homeless`, `smd`, `88`. |

---

## BACKLOG-125 — Distributor-as-customer masters (dim_customer 1152 / 4145 / syntech→4145)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed** · 2026-08-08 · Warren lock + cip absorb on `feat/backlog-125-126-masters-stems` |
| **Effort** | Medium |
| **Source** | Unit 6c Phase A E12: approved customer alias `syntech`→`dim_customer` 4145; related distributor-as-customer master pollution (also noted around 1152). Masters problem — not a lineup stamp rule. |
| **Idea** | Steward masters cleanup: retire/merge distributor-named `dim_customer` rows; revoke misleading customer aliases; ensure Syntech identity lives only on `dim_distributor` 51 + OPEN_CHANNEL for channel tokens. |
| **Why it matters / deferrable** | Customer alias can pre-select wrong named customers for tokens that should be distributor-parked. Deferrable while D-038 stamp path correctly forces OC for distributor tokens. |
| **What the work is** | Revoke aliases to 4145/1152; stamp Syntech→OC+dist 51; absorb 4145+1152 into OPEN_CHANNEL via `open_channel_absorb`; ship evidence: Compuspeed dist 12 → OC majority. |
| **Regression traps** | Never auto-create dims; do not change D-038 strip/match; Compuspeed-as-customer = OC (Warren). |
| **Behavior to retain** | D-038 distributor-token dual-write; OPEN_CHANNEL canon; Channel Syntech = OC + Syntech. |
| **Out of scope** | Rectron/Pinnacle/Mustek twin masters (separate if TRIGGER); inventing distributors. |
| **TRIGGER** | — closed. |

---

## BACKLOG-126 — No-dim distributor stems in customer column (`smd` / `superdisti` / `sadc homeless`)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed (partial residual SMD)** · 2026-08-08 · Warren lock |
| **Effort** | Small |
| **Source** | Unit 6c A1 + D5 residual: tokens with no `dim_distributor` exact match after strip; free-picker only under D-038. |
| **Idea** | Either mint/approve real `dim_distributor` (+ aliases) for these stems, or steward free-pick retailer/OC with reason — do not invent fuzzy distributor match. `sadc homeless` can Accept OC+Stylus via ship corroboration when sole+exact qty (D-040). |
| **Why it matters / deferrable** | Leaves unresolved free-picker stems without ship sole. Deferrable while planning is not blocked. |
| **What the work is** | **Done:** `superdisti`→dist **50** Superdist alias; `sadc - superdisti` stamped OC+50; homeless already Stylus 45. **Residual:** `SMD` is a **customer** token (Warren) — no ship customer named SMD; product 5376 ships multi-customer → leave free-picker (2 lines). |
| **Regression traps** | No substring/fuzzy distributor match; no auto-create from stamp; do not treat SMD as distributor. |
| **Behavior to retain** | Free picker + preview-first; D-040 Accept ship-corroborated. |
| **Out of scope** | Expanding D-038 strip patterns without Warren lock; inventing SMD dim_customer. |
| **TRIGGER** | — closed for distributor stems. Reopen only if Warren names an SMD customer target or ship evidence appears. |

---

## BACKLOG-127 — Shipment DAP (or priced confirm) for distributor attribution

| Field | Detail |
|-------|--------|
| **Status / parked** | **Done** · 2026-08-08 · `feat/backlog-127-128-dap-case-po` |
| **Effort** | Medium |
| **Source** | Unit 6d/6e discovery: `fact_inbound_shipment` has `unit_price`/`amount` only — no DAP field; qty-only confirmer cannot collapse multi-dist INDETERMINATE tokens. |
| **Idea** | Persist DAP (or a defined map to ship price + currency rules) on shipment facts so confirmer Phase 2 can confirm/conflict on price as well as product+period+qty. |
| **Why it matters / deferrable** | Raises confirmation hit-rate for OC distributor tokens. Deferrable while Phase-1 sole-qty confirmer + steward review work. |
| **What the work is** | Schema/contract for DAP on ship facts or evidence→fact mapping; currency rules; extend D-040 confirmer; never invent DAP from margin. |
| **Regression traps** | Do not conflate DAP with PM bottom / landed cost; do not use margin→distributor. |
| **Behavior to retain** | D-040 Phase-1 rules; exact token match. |
| **Out of scope** | Drive Control rename; DSI resolution order. |
| **TRIGGER** | Warren opens priced shipment confirmation or multi-dist unproven volume blocks planning. |
| **Resolution** | D-041: reuse ship `unit_price` as DAP-evidence (no migration); Phase-2 unique within 2% of `dap_evidence_local` → confirm_price / conflict_price / offer_accept_price. |

---

## BACKLOG-128 — PO-linkage gap: Stylus / case_po incomplete vs shipment sole

| Field | Detail |
|-------|--------|
| **Status / parked** | **Done** · 2026-08-08 · `feat/backlog-127-128-dap-case-po` |
| **Effort** | Small–Medium |
| **Source** | Unit 6e: `sadc homeless` ships sole Stylus 45 with exact qty; Stylus absent from some case_po sets (e.g. case 114) — PO-linkage gap, not cancel. |
| **Idea** | Worklist / auto-link repair so shipment-resolved distributors appear on case_po when commercially linked. |
| **Why it matters / deferrable** | Attribution can be correct while case_po still incomplete. Deferrable after D-040 Accept. |
| **What the work is** | Diagnose missing case_po for Stylus; steward or auto-link path without treating case_po as attribution oracle. |
| **Regression traps** | Do not use case_po absence to revoke D-038/D-040 stamps. |
| **Behavior to retain** | D-040 propose/confirm; PO auto-link competition rules. |
| **Out of scope** | Changing auto-link key / D-033 / D-034. |
| **TRIGGER** | After D-040 Accept for homeless, or case_po gaps block planning for Stylus volume. |
| **Resolution** | `…/case-po-attribution-gap/preview|apply` — unique PO covering attributed products via PO-bearing ships; never clears attribution. cip: case 114 ↔ PO 10473 (Stylus). |

---

## BACKLOG-111 — Lineup parse Celery worker can run stale code (uniform_half after D-028)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Small |
| **Source** | f4 apply created case 144 via job 790 with `allocation=uniform_half` / null `month_split_json`; re-parse in-process with current tree → month_derived 289/289 |
| **Idea** | Ensure worker restart / version pin after parse-path commits so enqueued jobs cannot invent retired allocations. |
| **Why it matters / deferrable** | Silent wrong quantities until re-parse. Deferrable while operators re-parse after code deploy. |
| **What the work is** | Dev topology note + optional worker bootstrap hash check; document restart in apply checklist. |
| **Regression traps** | Do not re-introduce uniform_half on parse path. |
| **Behavior to retain** | D-028 month-derived / refuse. |
| **Out of scope** | Rederivation path uniform_half. |
| **TRIGGER** | Next bulk lineup apply that enqueues parse jobs after a parser commit. |

---

## BACKLOG-110 — Auto-link apply has no survivor / po_issued guard

| Field | Detail |
|-------|--------|
| **Status / parked** | **Done** · 2026-08-05 (PROGRAM-A Unit 2) |
| **Effort** | Small |
| **Source** | Steward PO-link unit: acceptable apply linked `PURMIDR26009976` onto survivor case **7** (pols 1→2); reverted by deleting `commercial_lineup_case_po.id=657` |
| **Idea** | Refuse (or require explicit confirm) auto-link apply when target case is `po_issued` / survivor, unless Warren opts in. |
| **Why it matters / deferrable** | Hard constraint “do not modify survivors 7/9/90” is operator policy; API currently allows any confirmable status. Deferrable while Warren reviews competing proposals manually. |
| **What the work is** | Gate in `apply_auto_link_proposals` / `link_case_to_existing_po` or UI exclude list; audit log. |
| **Regression traps** | Do not block draft_imported linking; FLAG≠BLOCK for over-ship stays. |
| **Behavior to retain** | Idempotent re-link no-op; multi-PO append on drafts. |
| **Out of scope** | Changing match engine. |
| **TRIGGER** | Next auto-link bulk accept session, or Warren asks for survivor protection. |
| **Done note** | `evaluate_case_bulk_protection` + `allow_protected` override; bulk never sets override. Case 145 (`draft_imported`, 0 links) needs `CIP_LINEUP_PROTECTED_CASE_IDS`. |

---

## BACKLOG-109 — No steward unlink/undo for commercial_lineup_case_po

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed** · 2026-08-07 (PROGRAM-A Unit 6a VERIFY PASS) |
| **Effort** | Medium |
| **Source** | Revert of mistaken case-7 link required direct SQL DELETE — no API/UI unlink |
| **Idea** | Steward-facing unlink (or undo last apply) that deletes `commercial_lineup_case_po` and adjusts status ladder safely. |
| **Why it matters / deferrable** | Mistakes and survivor policy need reversible workflow without raw SQL. |
| **What the work is** | Endpoint + panel action; steward audit; status recompute when last PO removed. |
| **Regression traps** | Never cascade-delete POs; never touch shipment facts. |
| **Behavior to retain** | Link idempotency on (case_id, purchase_order_id). |
| **Out of scope** | Dismiss/restore of *proposals* (already exists). |
| **TRIGGER** | First production need to reverse a bad link, or BACKLOG-110 ships. |
| **Done note** | Unit 6a: `lineup_case_po_unlink` + `PoCaseLinkWorklistSection` on ResolutionWorklist; W6-2 refuse superseded; W6-3 DELETE+audit; Unit 2 `allow_protected`; clone C1–C4 on `cip_unit6a_smoke`. Close after VERIFY PASS. |

---

## BACKLOG-108 — Multi-BU slice_row_mapping_failed blocks full NR sheets

| Field | Detail |
|-------|--------|
| **Status / parked** | **Closed** · 2026-08-05 (PROGRAM-A Unit 3 / D-034) |
| **Effort** | Medium |
| **Source** | Session 752: `f15:Sheet1:NR:2026 Q2`, `f16:NR:NR:2026 Q3` status `needs_attention` / `slice_row_mapping_failed`; only thin NB slices applied (cases 128/129/131) |
| **Idea** | Fix slice→source_row mapping for the residual BU group after multi-BU split so the primary NR body can apply. |
| **Why it matters / deferrable** | Explains NR 2026 thinness vs 2025 (131–141 lines): files are full (~147/131 rows); corpus missing the NR body cases. Not a silent parser drop on applied slices. |
| **What the work is** | Reproduce on disposable DB; fix `map_slice_rows_to_source_row_numbers` / preview grouping; re-apply those keys only. |
| **Regression traps** | Do not auto-create dims; do not re-apply whole session 752. |
| **Behavior to retain** | Multi-BU sheet → per-BU proposals with `slice_source_rows`. |
| **Out of scope** | Relabeling NB-from-NR cases (product-derived BU is intentional). |
| **TRIGGER** | Warren wants full NR 2026 Q2/Q3 corpus before linking those periods. |
| **Resolution** | D-034: identity from apply-parser rows; Sheet1 ⊆ NR excluded. cip case **146** NR 2026 Q3 = **120** lines (was case 130 Sheet1 = 14). Evidence-pack "~126" was sheet rows before BU split. |

---

## BACKLOG-107 — Auto-link UI does not surface PO competition across cases

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Small–Medium |
| **Source** | 211 Warren-queued proposals; 87 competing PO norms (e.g. cases 119 vs 120 for same PO; 118 vs 125 NB vs NR) |
| **Idea** | Show “also proposed for case X” on each row / confirm dialog so steward does not accept both sides blindly. |
| **Why it matters / deferrable** | Engine correctly emits one proposal per case×PO; competition is domain-real (1H Q1 vs file-2 Q1; NB vs NR). UI hides the conflict. |
| **What the work is** | Annotate proposals sharing `po_number_norm`; optional single-winner apply. |
| **Regression traps** | Do not auto-pick winner; catalogue absence / over-ship remain FLAG≠BLOCK. |
| **Behavior to retain** | Exact customer+product+CRAD-in-period match key. |
| **Out of scope** | Changing confidence reason codes. |
| **TRIGGER** | Warren starts clearing the 211-queue, or next auto-link UX pass. |

---

## BACKLOG-106 — PoAutoLink steward surface is PARTIAL vs S1–S14

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Large |
| **Source** | S1–S14 grade of `PoAutoLinkProposalsSection.tsx` (2026-08-03) |
| **Idea** | Bring PO↔lineup link review to import-steward contract bar (or document permanent waivers). |
| **Why it matters / deferrable** | Works as card UI; gaps are shell/tabs/plan/async. Deferrable while HTTP apply path works. |
| **What the work is** | See grade table in CONTEXT 2026-08-03; extract shared drawer/bulk where slots apply. |
| **Regression traps** | Do not invent importer-prefixed files under `features/import-steward/`. |
| **Behavior to retain** | Chunked POST `/lineup/po-auto-link/apply`; dismiss/restore; over-plan expected copy. |
| **Out of scope** | Match-engine rewrite. |
| **TRIGGER** | Steward UX parity pass for commercial PO linking, or VERIFY unit for this surface. |

---

## BACKLOG-105 — PF 1H Gaming Desktop Qty column is not unit totals

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-03 |
| **Effort** | Small |
| **Source** | STATE_AUDIT §6 Q3; file `Copy of ACZA 1H 2025 Consumer Lineup - Gaming Desktop PD 13 Feb 2025.xlsx` (cases 134/135) |
| **Idea** | Workbook maps header `Qty` → `quantity_units` via alias, but cell values are ~0.15 while real units live in `Total Qty` / `May\n(TBC)`. Alias map must not be broadened blindly. |
| **Why it matters / deferrable** | Month-derived half now uses month columns (correct for May), but any path that still trusts `Qty` as units is wrong for this file. Deferrable while month columns drive 1H quantity. |
| **What the work is** | Steward/mapping decision: prefer `Total Qty` for this template family, or file-specific override — without breaking NB files where `Qty` is correct. |
| **Regression traps** | Do not change global `quantity_units` aliases without archive-wide proof. |
| **Behavior to retain** | Month-derived 1H from real month columns (D-028). |
| **Out of scope** | Re-apply session 752; changing historical_lineup. |
| **TRIGGER** | Next PF/desktop lineup import or Warren asks to fix Qty vs Total Qty mapping. |

---

## BACKLOG-104 — Bulk existing_case_collisions miss when case.notes is null (sheet)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-02 |
| **Effort** | Small |
| **Source** | Corpus restore preview session_import_job_id=752; surviving cases 7/9/90 have `notes=NULL` so `_sheet_from_case_notes` → None while proposals use sheet `Sheet1`/`NB` → `existing_case_collisions=0` despite same `file_name` |
| **Idea** | When existing case has no sheet in notes, treat sheet match as wildcard (or compare file_name+BU+period only) so po_issued / unified survivors are surfaced as collisions instead of silent duplicate-ready proposals. |
| **Why it matters / deferrable** | Apply of ready proposals for filenames of cases 9/90 (and period-shifted 7) would create parallel draft cases without superseding survivors — corpus duplication, not wipe. Deferrable until Warren picks exclude keys or detector fix before apply. |
| **What the work is** | Adjust `detect_existing_case_collisions` sheet equality; add regression covering notes=NULL vs Sheet1; do not auto-pick winner for po_issued (keep existing-as-default-winner). |
| **Regression traps** | Do not hard-delete; do not silently supersede po_issued; steward confirmations remain Warren’s. |
| **Behavior to retain** | Default `winner_member_key=existing:{id}` skip path. |
| **Out of scope** | Corpus apply itself; BACKLOG-101 terminal status. |
| **TRIGGER** | Before next bulk lineup apply that overlaps unified_lineup_import survivors **or** Warren asks to resume corpus restore apply. |

---

## BACKLOG-103 — Unified lineup import has no 1H → Q1+Q2 fan-out

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-02 |
| **Effort** | Medium |
| **Source** | `docs/STATE_AUDIT_2026-08-02.md` §5 Q3; corpus restore preview 2026-08-02 (bulk path fans via `half_year_allocation_half`) |
| **Idea** | Port bulk’s 1H → Q1+Q2 fan-out (`period_half_split_q*` + `half_year_allocation_half` / `allocation=uniform_half`) into the unified lineup import path so a single 1H workbook does not land as one half-plan case. |
| **Why it matters / deferrable** | Silent half-plan loss on unified imports. Bulk already implements fan-out; unified creates one case per file. Deferrable while restores use bulk backfill. |
| **What the work is** | Resume-context: bulk path in `lineup_bulk_period_inference` / apply parse options; wire equivalent into unified dispatch/parser without changing DSI rules. |
| **Regression traps** | Do not double-count quantities across Q1+Q2; preserve steward supersession confirmations. |
| **Behavior to retain** | Bulk fan-out semantics already live. |
| **Out of scope** | Changing COMMERCIAL_SEMANTICS formulas. |
| **TRIGGER** | Next 1H import via the **unified** lineup path (not bulk backfill). |

---

## BACKLOG-102 — Lineup corpus restore apply (await collision exclusions)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Shipped** · 2026-08-02 (verify complete) |
| **Effort** | Medium (apply + D1–D4 validation) |
| **Source** | Preview job 752 on cip; archive copy under `.tmp/ProductLineupArchive`; A3 stop gate passed but Phase B unexplained overlap with cases 7/9/90 |
| **Idea** | Resume Phase C–D: apply ready proposals from session 752 (or re-preview), excluding or steward-confirming overlaps with surviving po_issued cases 7/9/90; then pct/PO/reader/PvE checks. |
| **Why it matters / deferrable** | ~~Preview complete; apply blocked on exclusions.~~ **Done:** Warren exclusion set applied (30 applied / 5 skipped); worker drained parse jobs 753–779; D1–D4 verification recorded in CONTEXT. |
| **What the work is** | Apply with `excluded_proposal_keys` or confirmations; verify 7/9/90 unchanged; D1–D4; CONTEXT append counts. |
| **Regression traps** | Never modify cases 7/9/90; no migration; expect session job left `running` (BACKLOG-101). |
| **Behavior to retain** | Preview session 752 payload; default existing-wins if collisions appear. |
| **Out of scope** | Fixing BACKLOG-101 in the same unit. |
| **TRIGGER** | ~~Warren supplies exclude/confirm list~~ — fired and completed. Residual steward work is not this entry (auto-link proposals; failed parses 759/760; period flags on needs_attention). |
| **Outcome** | Cases 33 (30 active + 3 superseded shells); lines 2450; po_links 52 (unchanged). Survivors 7/9/90 unchanged. Session 752 still `running` (BACKLOG-101). Child parses: 25 completed / 2 failed (`Promo R19999` on `2. ACZA 1H 2026…`, cases 120/121 empty). D1: 0 implausible pct rows (stored fraction-ish 0–1). D2: linked still 52; 355 auto-link proposals waiting. D4: PvE lineup-linked quarters still 2026 Q1+Q2 only (no new PO links). |

---

## BACKLOG-101 — Lineup delete audit actor + bulk apply terminal status

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-02 |
| **Effort** | Small |
| **Source** | Corpus-safety unit 2A–2D (2026-08-02); `delete_lineup_case` still has no auth dependency; `apply_bulk_lineup_batch_sync` leaves `import_job.status='running'` after apply |
| **Idea** | (1) Wire `get_current_user` (or optional user) on `DELETE /lineup-cases/{id}` so steward_audit actor is not always `anonymous`. (2) Set bulk lineup session job to an existing terminal status (`completed` / `completed_with_errors`) when apply finishes so reaper/UI do not treat finished applies as live work. |
| **Why it matters / deferrable** | Audit trail now exists (2B) but actor is weak without auth. Job 255 was stuck `running` partly because apply never terminals the session job. Deferrable while corpus rebuild proceeds; anonymous audit + manual failed clear already unblock rebuild. |
| **What the work is** | Auth dependency + tests; terminal status write at end of `apply_bulk_lineup_batch_sync` matching lifecycle vocabulary; do not invent new statuses. |
| **Regression traps** | Do not change draft_imported-only delete gate; do not auto-create masters; keep steward_audit in same transaction as delete. |
| **Behavior to retain** | steward_audit row on every lineup case delete path; payload carries case_id/source_context/period/BU/line_count/po_link_count/reason. |
| **Out of scope** | Schema change to steward_audit; corpus rebuild itself. |
| **TRIGGER** | Next commercial-planner auth pass **or** next bulk lineup backfill session after corpus rebuild. |

---

## BACKLOG-100 — Make `pnpm test:api` on cip_test a hard CI merge gate

| Field | Detail |
|-------|--------|
| **Status / parked** | **Shipped** · 2026-08-01 · PR #15 |
| **Effort** | Large (batch-fix known defect classes on disposable DB) |
| **Source** | `docs/CI_API_DEFECT_LOG_2026-07-29.md`; CI run on PR #14 (~87 failed / 30 errors); workflow had a hard `exit 1` after record-only API step which blocked merge despite green e2e/build |
| **Idea** | Fix API suite against ephemeral `cip_test` so CI can hard-fail on API regressions (restore real merge gate for backend). |
| **Why it matters / deferrable** | ~~Today API runs with `continue-on-error` + artifact log~~ — suite green on cip_test (1760 passed); hard gate restored. |
| **What the work is** | Batch-fix defect classes in the 2026-07-29 log; drop continue-on-error; restore hard fail step; keep `ALLOW_TESTS_ON_DEV_DB` unset in CI. |
| **Regression traps** | Do not point CI API tests at `cip`; do not set `ALLOW_TESTS_ON_DEV_DB=1` in Actions. |
| **Behavior to retain** | Alembic migrate assert tip == sole `ScriptDirectory` head (tracks migrations); upload pytest log on API failure. |
| **Out of scope** | Live e2e API wiring (BACKLOG-099); required-check unlock (BACKLOG-087). |
| **TRIGGER** | — shipped — |

---

## BACKLOG-099 — Wire live API into GitHub Actions e2e

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-01 |
| **Effort** | Medium (CI job wiring + seed/auth for live specs) |
| **Source** | PR #13 CI — e2e red: Next proxy `ECONNREFUSED :8001`; wipe/products specs need live API (`CIP_E2E_API_URL` / `:8010`) |
| **Idea** | Run FastAPI in GitHub Actions against already-migrated `cip_test`, point Next proxy + `CIP_E2E_API_URL` at it, enable `wipe-and-products-delete` (and future live specs). |
| **Why it matters / deferrable** | Live wipe/delete e2e currently skipped in CI (`CIP_E2E_LIVE_API` gate). Mocked/static e2e still run. Deferrable while docker:e2e / local API cover the live path. |
| **What the work is** | CI step: start uvicorn on :8001 with `cip_test` URLs + `CIP_AUTH_MODE=stub` (or session + login helper); seed minimal products (`SKU-ALPHA-01`); set `CIP_E2E_LIVE_API=1` / `CIP_E2E_API_URL`; unset `CIP_DISABLE_NEXT_API_PROXY` for webServer. |
| **Regression traps** | Do not point CI e2e at `cip`; keep `ALLOW_TESTS_ON_DEV_DB` unset; do not weaken steward/wipe safety flags. |
| **Behavior to retain** | Mocked e2e (dashboard / getting-started / navigation) stay API-free and green without this. |
| **Out of scope** | Full browser soak of Import Centre; required-check unlock (BACKLOG-087). |
| **TRIGGER** | Warren asks for green live e2e on GitHub CI **or** live wipe/products specs start failing locally without a clear docker:e2e path. |

---

## BACKLOG-098 — P3-5 Celery beat + import-complete report schedules

| Field | Detail |
|-------|--------|
| **Status / parked** | **Shipped 2026-08-08** — code on `main` (`reports.run_due_schedules` beat task + `reports.fanout_import_complete` fan-out, `apps/api/app/worker/tasks.py`); `report_schedule` id=1 (`weekly_monday_0700`, `tenant_id=default`, `enabled=true`) exists on `cip` with a real `last_run_at` (2026-08-01), confirming the run-now path has executed against it. |
| **Effort** | Medium (beat task + import hook; small) |
| **Source** | P3-5 authored 2026-08-01 — `report_schedule` + `run-now` inbox path; ROADMAP P3-5 calendar + event delivery |
| **Idea** | Wire Celery beat for `weekly_monday_0700` / `daily_0700` and fan-out `on_import_complete` schedules after DSI/shipment apply completes. |
| **Caveat** | Confirmed proof so far is the **run-now path** (`POST /reports/schedules/{id}/run-now`) and the fan-out task existing and being callable — not an unattended overnight Monday-07:00 beat firing in production. Unattended beat requires `CIP_ENABLE_DEV_BEAT=1` locally (Windows dev defaults beat **off** — see `dev_beat_disabled()` in `apps/api/app/worker/celery_queues.py`); production beat scheduling posture is untouched by this note. |
| **What the work is** | Done — beat entry + task iterating enabled schedules due; import apply progress-complete hook for `on_import_complete`; optional email_stub channel later remains a separate idea, not required for "shipped". |
| **Regression traps** | Never skip delivery when metric returns empty — missing data is the alert; always stamp `data_vintage`. |
| **Behavior to retain** | Inbox channel + missing_data_alert + tenant scope. |
| **Out of scope** | External SMTP productization; P3-6 SQL viewer. |
| **TRIGGER** | — shipped — reopen only if Warren wants true unattended overnight delivery proven end-to-end with `CIP_ENABLE_DEV_BEAT=1` left running across a real Monday 07:00. |

---

## BACKLOG-097 — P3-2 materialised aggregates / set-based A3 stock

| Field | Detail |
|-------|--------|
| **Status / parked** | **Resolved 2026-08-01** — set-based `derived_stock_components_by_dist_product` (latest join + aggregated sell-out/POD-landed); cold WoC ~7.4s→~3.2s; value parity 13.600643219087154 on cip. No MV needed yet. |
| **Effort** | Medium–Large (SQL rewrite + optional refresh job; maybe MV) |
| **Source** | P3-2 live soak 2026-08-01 — cold `weeks_of_cover` full portfolio ~7.4s / `fill_rate` ~5.7s vs ROADMAP report render &lt;5s p95; warm cache &lt;1ms OK |
| **Idea** | Replace per-pair scalar sell-out/landed loops in `derived_stock_by_dist_product` with set-based CTEs; optionally Postgres MATERIALIZED VIEW + refresh on import apply; keep latest-per-(distributor,product) invariant. |
| **Why it matters / deferrable** | Meets NFR for cold governed report without relying only on 60s result cache. Deferrable while warm-cache path + report builder (P3-3) are primary; P3-2 ships process-local/Redis TTL cache. |
| **What the work is** | Done for set-based path; MV deferred unless cold misses return. |
| **Regression traps** | Never sum SOH snapshot history; pipeline/open_order must stay out; tenant_id filter required. |
| **Behavior to retain** | Formula: latest reported − sell-out since + POD-landed shipped since; WoC at distributor×product only. |
| **Out of scope** | Report builder UI (P3-3); changing COMMERCIAL_SEMANTICS formulas. |
| **TRIGGER** | — shipped set-based; reopen only if cold `/query/execute` regularly exceeds 5s again — then consider MV. |

---

## BACKLOG-096 — Commercial tenant profile onboarding UI

| Field | Detail |
|-------|--------|
| **Status / parked** | **Done / shipped 2026-08-08** (P6) |
| **Effort** | Medium (settings/onboarding form + persistence) |
| **Source** | Warren 2026-08-01 Q-resolve — answers are current-tenant defaults; must stay TENANT-VARIABLE |
| **Idea** | Expose `commercial_tenant_profile` keys in Getting Started / tenant settings: `constraint_axis`, `over_budget_action`, `reservation_source`, `pm_attribution_mode`. Persist per tenant; stop relying on module-level defaults alone. |
| **Shipped 2026-08-08** | File-persistence (no migration): `apps/api/app/services/commercial_tenant_profile.py` — `load_tenant_profile_overrides` / `save_tenant_profile_overrides` read/write `{local_storage_path}/tenant_profiles/{tenant_id}.json`; `profile_snapshot(tenant_id="default")` merges file overrides over module defaults (back-compat — existing no-arg call sites unaffected). API: `GET`/`PUT /api/v1/auth/tenant-commercial-profile` (GET any authenticated role, PUT admin-only via `require_roles(Role.ADMIN)`). UI: new "Commercial tenant profile" section on `/settings` (`apps/web/src/app/(app)/settings/page.tsx`) — four selects + save, `data-testid="tenant-profile-*"`, read-only for non-admins. |
| **Why it matters / deferrable** | Second customer / multi-tenant readiness (P6); ASUS SA answers must not be baked into application law. Now editable per tenant without a migration. |
| **What the work is** | Done — settings form; API read/write; file persistence keyed by `tenant_id`; module defaults remain the fallback when no override file exists. |
| **Regression traps** | Do not hardcode NB/NR/NV/NX or ZAR-only assumptions in UI copy as the only options. |
| **Behavior to retain** | Profile stub defaults remain valid until overridden. |
| **Out of scope** | Full multi-tenant IAM; hosting (Q-003); moving these keys into a DB table (file persistence chosen deliberately — no migration). |
| **TRIGGER** | — shipped — |

---

## BACKLOG-095 — CPOR over-money-ceiling reapproval

| Field | Detail |
|-------|--------|
| **Status / parked** | **Resolved 2026-08-01** — `needs_reapproval` on `cpor_case` (alembic `20260801_0002`); gates on approve/export; UI reapprove CTA; `HARD_ENFORCE_BUDGET=true`; optional `MONEY_CEILING_USD` |
| **Effort** | Medium–Large (case lifecycle + gate) |
| **Source** | Warren Q-001 2026-08-01 — money ceiling binding; over → case must be reapproved |
| **Idea** | When drawn/planned spend exceeds money reservation, mark CPOR case as needing **reapproval** (and eventually block approve/export until reapproved). Honour `over_budget_action` from commercial tenant profile. |
| **Why it matters / deferrable** | Prevents silent overspend vs target reservation. |
| **What the work is** | Done: flag + `confirm_over_budget_reapproval` on approve; export 409 while flagged/over; banner on case detail. |
| **Regression traps** | Do not block on support-% when `constraint_axis=money`. Ceiling optional — without `MONEY_CEILING_USD`, gate is flag-only. |
| **Behavior to retain** | Dual-track explainability; cancel frees budget (domain §1.6). |
| **Out of scope** | Hosting; support-% as binding axis (unless profile changes). |
| **TRIGGER** | — shipped — |

---

## BACKLOG-094 — Promo planning: auto MAC + price-delta sales forecast

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-01 |
| **Effort** | Large (planning write-path + cost/forecast contracts) |
| **Source** | Warren 2026-08-01 A-lane wrap — automated promo planning economics |
| **Idea** | When **promotion planning** runs: (1) **MAC auto-computed** from **current MAC** and **buy plan** (not free-typed); (2) if planned **new dealer / sell-out price** differs from current MAC, surface **forecasted sales** under that price delta (elasticity/volume lift path — define formula in semantics before build). |
| **Why it matters / deferrable** | Funding + volume truth for promo cases; wrong MAC or silent price-delta = bad support math. Deferrable until promotion-planning authoring surface / B-lane promo planning is active. |
| **What the work is** | Lock MAC formula (current MAC × buy-plan mix — exact weights TBD); wire into planning UI/API; price≠MAC → forecasted units with explainable factors; AMBER design gate on formulas in `COMMERCIAL_SEMANTICS`. |
| **Regression traps** | Do not auto-rewrite **approved** cost basis (existing MAC staleness rule — flag drift, KAM/PM decides). Do not invent elasticity without a locked formula. DAP ≠ MAC ≠ controlled_cost. |
| **Behavior to retain** | Cost-basis as-of dates; `cost_basis_drift` flag on recompute; steward approval for master creates. |
| **Out of scope** | Distributor **paid** recon (BACKLOG-092); customer promo-load recon (BACKLOG-093). |
| **TRIGGER** | Promotion planning authoring unit starts **or** Warren locks MAC + price-delta forecast formulas in semantics. |

---

## BACKLOG-093 — Case-scoped customer sales recon for promo load correctness

| Field | Detail |
|-------|--------|
| **Status / parked** | **Done** · 2026-08-08 · `feat/a-lane-residual-closeout` |
| **Effort** | Large (CST/customer-file join × CPOR case window) |
| **Source** | Warren 2026-08-01 A-lane wrap — automated promo verification path |
| **Idea** | For a specific CPOR case, reconcile **customer sales / sell-through files** against the case’s promo window and products to check whether the **customer loaded the promotion correctly** (price/units/timing vs approved support). |
| **Why it matters / deferrable** | Closes the loop between approved CPOR and what the retailer actually ran. Deferrable until automated promo-ops path is prioritized; not needed to close A-lane. |
| **What the work is** | Case-scoped recon surface: expected promo terms vs customer-file observed sell-through; exception buckets (missing load, wrong price, wrong window). Prefer shared import/steward patterns — no one-off sync scripts as smoke. |
| **Regression traps** | Sell-out (disti→reseller) ≠ sell-through (retailer→end user). Do not treat DSI sell-out as customer promo load proof. |
| **Behavior to retain** | CPOR case truth for approved support; CST facts as evidence; no auto-create masters. |
| **Out of scope** | Distributor payment paid-vs-owed (BACKLOG-092); inventing claim “owed”. |
| **TRIGGER** | Warren starts automated promo-ops / asks for case-level customer-file promo recon **after** payment path is separate. |
| **Resolution** | `GET /cpor/cases/{id}/promo-load-recon` + case detail **Promo load** tab; CST-only; buckets ok/missing_load/wrong_window/wrong_price/price_unknown/no_cst; 2% price tol. |

---

## BACKLOG-092 — CPOR “paid” vs owed — distributor payment reconciliation

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked · Warren-owned** · 2026-08-01 — leave payment **file supply** to Warren; agents do not chase Ken extracts |
| **Effort** | Large (new evidence type + recon surface) |
| **Source** | Warren 2026-08-01 (owed vs paid wording on Q-008 / D-027); wrap 2026-08-01 leave files to Warren |
| **Idea** | Capture what distributors **paid** (processed payments), separate from **owed** (settlement support due). Source: Ken / admin payment extracts. |
| **Why it matters / deferrable** | Paid ≠ owed; without payments, any “paid rate” fabricates. Deferrable until payment files + Ken process exist. **Warren owns bringing the files.** |
| **What the work is** | Import/recon path for payment evidence; join to cases/lines; metrics that compare paid vs owed. Later: more automated approach (not this A-lane). |
| **Regression traps** | Do not rename “owed” to “paid”; do not use claim-evidence units as paid. |
| **Behavior to retain** | Delivery rate; computed `ttl_result`; claim-rate stays non-computable until distinct **owed** exists. |
| **Out of scope** | Inventing paid from result_qty × support_unit; agent-chasing Ken without Warren files. |
| **TRIGGER** | Warren provides distributor payment extracts **and** asks for a paid-vs-owed surface. |

---

## BACKLOG-091 — Rename PvE “Deal-stock landing” tile → “Over-plan intake”

| Field | Detail |
|-------|--------|
| **Status / parked** | **Resolved 2026-08-01** — UI label **Over-plan intake**; exception “Over-ships / over-plan intake”; API `over_plan_intake_*` aliases |
| **Effort** | Trivial (UI string + tooltip; optional test ids) |
| **Source** | `docs/COMMERCIAL_SEMANTICS.md` A1-02; Warren 2026-08-01 (end POD collision) |
| **Idea** | Rename scorecard label “Deal-stock landing” to **Over-plan intake** (and exception copy “Over-ships / deal-stock” accordingly) so it cannot be read as POD landing. |
| **Why it matters / deferrable** | Docs already renamed; live UI still says landing. Deferrable to next A1 touch. |
| **What the work is** | `PlanVsExecutedView.tsx` (+ tests if they assert the string). |
| **Regression traps** | Do not change the formula (still Σ max(S−P,0)); do not add POD. |
| **Behavior to retain** | Same units/value secondary line. |
| **Out of scope** | Shipping POD tiles. |
| **TRIGGER** | **Next A1 unit** that touches Plan vs Executed UI. |

---

## BACKLOG-090 — Channel Ops summary WoC mixes customer-grain velocity with channel stock

| Field | Detail |
|-------|--------|
| **Status / parked** | **Resolved 2026-08-01** — sell-out velocity at distributor×product; portfolio Σstock/Σvelocity |
| **Effort** | Medium (need dist×product velocity or sell-out-derived velocity at same grain) |
| **Source** | `docs/COMMERCIAL_SEMANTICS.md` A3-02; live code audit 2026-08-01 |
| **Idea** | Fix Channel Ops weeks-of-cover so numerator and denominator share **distributor × product** grain. |
| **Evidence (wrong today)** | `GET /api/v1/channel-ops/summary` (`channel_ops.py` ~165–181): `total_inv` = `sum_derived_channel_stock` (dist×product); `weeks_of_cover` = that stock ÷ `avg(FactCustomerVelocity.velocity_52wk)`. `FactCustomerVelocity` is keyed **distributor × product × customer** (`fact_customer_velocity.py`). Averaging customer-grain rows against channel stock is a grain mismatch. Inventory tab (~360–383) picks **max** customer `velocity_52wk` per product — still customer-grain, not dist×product sell-out velocity. |
| **Why it matters / deferrable** | Summary “weeks of cover” on `/sell-out` is wrong on screen. Deferrable until A3 unit; do not patch with another mismatched average. |
| **What the work is** | Define/implement velocity at dist×product (or document sell-out rate at that grain); wire summary + inventory WoC; zero velocity → undefined. |
| **Regression traps** | Do not “fix” by averaging harder; do not use CST `/channel-intelligence` customer×site grain for Channel Ops. |
| **Behavior to retain** | Derived stock latest-per-pair; `weeks_of_cover_or_none` near-zero → None. |
| **Out of scope** | Replenishment engine (flag v1 only). |
| **TRIGGER** | A3 weeks-of-cover / replenishment unit starts. |

---

## BACKLOG-089 — Cost per incremental unit (promo) — do not build without baseline

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-08-01 · removed from ROADMAP A2 scope |
| **Effort** | Large (requires validated counterfactual / baseline model) |
| **Source** | Warren 2026-08-01 metric lock; `docs/COMMERCIAL_SEMANTICS.md` A2-X |
| **Idea** | Cost per **incremental** unit sold under promo (support attributable to lift vs baseline). |
| **Why it matters / deferrable** | Without a validated baseline, the number is fabricated. Deferrable until a baseline model exists; A2 ships **support cost per unit sold** (`support ÷ result_qty`) instead. |
| **What the work is** | Define and validate a baseline/lift model; then add the metric to `COMMERCIAL_SEMANTICS` and build on CPOR. |
| **Regression traps** | Do not ship a placeholder “incremental” that is just support÷qty under another name. |
| **Behavior to retain** | Delivery rate / claim rate / support÷result_qty remain the A2 unit-economics set. |
| **Out of scope** | Inventing a baseline in the A2 unit. |
| **TRIGGER** | **Validated baseline model exists** (Warren + domain sign-off). |

---

## BACKLOG-088 — Propagate evidence `pod_date` to current view / facts (P1-D004)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Resolved** · 2026-08-02 · sticky POD write-path + view `20260802_0009` + fact backfill (5961 rows; 156 remain without evidence POD) on `fix/commercial-foundation-pod` |
| **Effort** | Medium (apply-path / view COALESCE / optional fact backfill — may need approved migration for view redefine) |
| **Source** | `docs/P1_LOAD_DEFECT_LOG.md` P1-D004; Shipping owns POD (`docs/SURFACE_OWNERSHIP.md`); apply already copies `pod_date` on new writes (`shipment_inbound_facts.py`) |
| **Idea** | Make Shipping landed/POD KPIs truthful: `shipment_evidence_current` and `fact_inbound_shipment` must expose the same `pod_date` as active `shipment_evidence_line` for shipped rows (COALESCE or rewrite observation/fact). |
| **Why it matters / deferrable** | Landed-week / awaiting-POD cohorts under-count when fact/current omit POD that evidence has. Blocks truthful B2 landed-basis budget. |
| **What the work is** | (1) Root-cause why current observation / older facts lack POD while evidence has it. (2) Fix write path and/or redefine current view. (3) Backfill facts only with approved data repair (clone-proof if destructive). (4) Prove Shipping `/shipping` landed/POD cohorts match evidence. |
| **Regression traps** | Do **not** put POD completeness tiles on Plan vs Executed; do not gate fill on POD; do not invent a second lifecycle owner. |
| **Behavior to retain** | Shipping = lifecycle authority; evidence is source of truth for POD; fill = shipped-basis. Sticky POD: later null snapshots must not clear a prior POD. |
| **Out of scope** | Landing-quarter reattribution KPI (BACKLOG-068); PvE rebuild. |
| **TRIGGER** | Warren prioritized 2026-08-02 (mapping-audit Q6). **Done:** observation sticky + fact sticky + view COALESCE + backfill script. |

---

## BACKLOG-087 — ~~GitHub required status check~~ — REMOVED

| Field | Detail |
|-------|--------|
| **Status** | **Removed** · 2026-08-09 · Warren: will not purchase GitHub Pro; do not track |
| **Note** | Process gate stays discipline-only: CI + `scripts/verify-gate`; no required status check on `main`. |

---

## BACKLOG-086 — PM bulk upsert `channel_id` CASE + typed cast (redo `558d088`)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-29 · cherry-pick skipped |
| **Effort** | Small–Medium |
| **Source** | `fix/pm-bulk-upsert-coercion-and-sql-types` @ `558d088`; ROADMAP P0 item 3; hygiene session conflict abort |
| **Idea** | Re-apply the psycopg3 typeless-NULL fix: typed casts on VALUES staging columns mixed with ORM columns in CASE (notably `channel_id`), plus any still-needed tabular coercion from that commit. |
| **Why it matters / deferrable** | Untyped `None` → PostgreSQL `text` NULL; CASE vs Integer/Date ORM columns raises `DatatypeMismatch`. Real hazard on PM bulk upsert. Deferrable until next PM bulk-write / import-apply touch. |
| **What the work is** | Redo natively on current `main` `product_import_sync.py` — do **not** force-merge the old branch tip. Cherry-pick `558d088` already **conflicted** there (abort). |
| **Conflict location** | `apps/api/app/services/catalog/product_import_sync.py` (main already has some date `cast()` work; `channel_id` CASE still missing / diverged). |
| **Regression traps** | Project gotcha: wrap non-text VALUES staging columns in `cast(col, Type)` inside CASE/SELECT mixing ORM columns; string columns usually OK. Must prove with real DB execution (SQL validation rule), not mocks only. |
| **Behavior to retain** | Existing PM upsert semantics / source keys; do not broaden into unrelated coercion unless still required after conflict resolve. |
| **Out of scope** | Landing the whole `fix/pm-bulk-upsert-coercion-and-sql-types` branch; schema migrations. |
| **TRIGGER** | Next PM bulk upsert / product-import-sync change; **or** a live `DatatypeMismatch` on `channel_id` CASE; **or** Warren prioritizes P0 item 3. |

---

## BACKLOG-085 — Ops-list pagination chrome (fold into phase — not standalone)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-29 · extracted from `feat/ops-master-grid-shell-parity` per D-021 |
| **Effort** | Small (mechanical per page) |
| **Source** | D-021 fuller diff; CST steward / CPOR / PM gaps / PO gap / PVE list paging chrome on ops-master |
| **Idea** | When touching those ops list pages, bring skip/limit (or equivalent) pagination UX to the current route layout — same fold-in rule as BACKLOG-079. |
| **Why it matters / deferrable** | Consistency for long ops queues. **Do not schedule standalone.** |
| **What the work is** | Native pagination on current post–Unit F routes; may use BACKLOG-084 helpers if still missing. |
| **Regression traps** | Do not revive pre–Unit F paths; do not pull channel-ops KPI or shippingUtcDates from ops-master (D-021 supersede). |
| **Behavior to retain** | Existing filter/query contracts; Enterprise AG Grid pattern. |
| **Out of scope** | Standalone pagination epic; ops-master merge. |
| **TRIGGER** | Phase work that already edits the named ops list pages; **or** Warren asks for paging on a named page. |

---

## BACKLOG-084 — Shared URL helpers (`useDebouncedUrlQuery` + `skipLimitSearchParams`)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-29 · extracted from `feat/ops-master-grid-shell-parity` per D-021 |
| **Effort** | Small (mechanical) |
| **Source** | D-021; ops-master shared helper modules used by ops list paging |
| **Idea** | Debounced URL query sync + skip/limit search-param helpers for list pages. |
| **Why it matters / deferrable** | Reduces duplicated URL↔filter glue. Cheap to redo natively when a consuming page needs them. |
| **What the work is** | Re-implement on `main` against current App Router patterns when first consumer needs them (often with BACKLOG-079/085). |
| **Regression traps** | Do not import from deleted ops-master tip; keep debounce UX (~300ms) consistent with steward search where applicable. |
| **Behavior to retain** | Shareable URL state for filters/paging. |
| **Out of scope** | Pulling unrelated ops-master chrome. |
| **TRIGGER** | First ops/list page change that needs URL-synced skip/limit or debounced query; **or** fold-in with BACKLOG-079/085. |

---

## BACKLOG-083 — Customer merge companions (redirect, related-name, repair/backfill)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-29 · extracted from `feat/ops-master-grid-shell-parity` per D-021 |
| **Effort** | Medium–Large |
| **Source** | D-021 fuller diff; `customer_merge_redirect.py`, `customer_related_master_groups.py`, RelatedName UI, ops scripts `backfill_merged_customer_alias_seals.py` / `repair_open_channel_wrong_merge.py` (and peers on tip) |
| **Idea** | Merge-engine adjacent surfaces: follow redirects after merge, related-name worklist for subset merges, repair/backfill scripts for wrong OPEN_CHANNEL / seal gaps. |
| **Why it matters / deferrable** | Completes alias-seal (BACKLOG-081) into a safe merge story. Deferrable until merge-heavy steward wave. |
| **What the work is** | Rebuild against current `main` merge APIs; **clone-proven end-to-end** before claiming done (project clone-gate / disposable DB rule — not mock-only). |
| **Regression traps** | Merge-engine adjacent — wrong redirect or related-name mapping corrupts identity; OPEN_CHANNEL must not absorb wrong merges; scripts must verify `current_database() = cip` (or disposable clone) before writes. |
| **Behavior to retain** | Steward-initiated merges only; no auto-create dims from import evidence. |
| **Out of scope** | Alias seal core (BACKLOG-081); ops-master wholesale merge. |
| **TRIGGER** | Pairs with BACKLOG-081 when customer-duplicate cleanup is prioritized; **or** Warren schedules merge-engine wave. |

---

## BACKLOG-082 — DSI header vocabulary → template config (ASUS seed + denylist; D-022)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Done** · 2026-08-01 · P1-1 — `20260730_0075` applied on cip; `_policy` on `distributor_inventory`; precedence memory>alias>heuristic; pytest header suite 20/20 |
| **Effort** | Medium |
| **Source** | D-022; ROADMAP P0 item 1 → pulled into P1 as DSI load-blocker; stash `park-dsi-asus-dealer-name-automap` (knowledge only — implementation dropped) |
| **Idea** | Retire hardcoded header strings in `dsi_mapping_workflow.py`. Per-template header-alias map + never-auto-map denylist. Precedence: **confirmed memory > template alias > heuristic** (today `apply_exact_raw_customer_header_overrides` beats memory — backwards). |
| **Why it matters / deferrable** | Mis-mapped identity columns poison customer resolution / aliases permanently. **Not deferrable inside P1** — blocks clean ASUS weekly load (P1-2). |
| **What the work is** | Config surface for template aliases + denylist; migrate RAW/ASUS seeds; fix precedence; remove literal tenant headers from workflow heuristics (config lives in `template_definitions`). |
| **ASUS template seed (from stash — domain knowledge only)** | **Map:** `Dealer Name` → `customer_dealer_token` (Source customer name); prefer RAW `Customer name` when both present; `Dealer Name Group` → `dealer_group_token`; `ASUS Part No.` → `product_identifier`; prefer `Unit Price` over `Total Price` / line totals. **Never auto-map (denylist):** `Customer Code (Dealer Code)`; `Dealer Name 1` (and `dealer_name_1` / `dealer-name-N` pattern). Also treat distributor dealer-code headers (`dealer code`, `customer code`+`dealer`) as non-identity. |
| **Regression traps** | Do not land stash implementation as constants; do not let heuristic override confirmed memory; denylist must clear prior wrong maps on those columns. |
| **Behavior to retain** | Steward-confirmed mapping memory wins; FLAG≠BLOCK leftovers stay reviewable. |
| **Out of scope** | Landing `park-dsi-asus-dealer-name-automap` as written; new importer surfaces. |
| **TRIGGER** | **Fired** — P1 entered; implement as P1-1 before P1-2 DSI weekly. |

---

## BACKLOG-081 — Customer merge alias seal

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-29 · extracted from `feat/ops-master-grid-shell-parity` per D-021 |
| **Effort** | Medium–Large |
| **Source** | D-021 extract; branch tip `customer_merge_alias_seal.py` |
| **Idea** | On full customer merge, mint approved aliases from loser display names → keeper so future DSI resolution does not re-steward merged tokens. |
| **Why it matters / deferrable** | Without seal, merged customers keep reappearing as unresolved steward work. Deferrable until a merge-heavy steward wave or P1 entity-resolution volume forces it. |
| **What the work is** | Port/rebuild seal against current `main` (post–Unit F / post–BACKLOG-061). Companions → BACKLOG-083. |
| **Regression traps** | Never overwrite third-party aliases; never abort merge on conflict; OPEN_CHANNEL must not absorb wrong merges; idempotent seal; clone-proven E2E when paired with BACKLOG-083. |
| **Behavior to retain** | Steward-initiated merges only; no auto-create dims from import evidence. |
| **Out of scope** | Redirect / related-name / repair scripts (BACKLOG-083); ops-master wholesale merge. |
| **TRIGGER** | P1 steward volume shows re-open tokens after merges; **or** Warren prioritizes customer-duplicate cleanup. |

---

## BACKLOG-080 — CST article-alias batch Confirm/Reject (partial-success envelope)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-29 · extracted from `feat/ops-master-grid-shell-parity` @ `bf2afd4` per D-021 |
| **Effort** | Small–Medium |
| **Source** | D-021; commit `bf2afd4` — `cst_steward.py` batch endpoints + `/admin/cst-steward` UI |
| **Idea** | Batch Confirm/Reject for CST article aliases with partial-success envelope (not only per-row). |
| **Why it matters / deferrable** | Operators waste time confirming aliases one-by-one before P3. Deferrable until CST ops volume rises; import-steward CST E1/E2 already shipped separately. |
| **What the work is** | Re-implement batch confirm/reject + UI against current `cst_steward` on `main` (do not merge ops-master wholesale). |
| **Regression traps** | Partial success must surface per-id failures; do not confuse with CST **import** token steward (`D-018` — Import Centre path). |
| **Behavior to retain** | Per-row confirm/reject still works; no silent apply to facts. |
| **Out of scope** | CST historical backfill; import-job resolution plan (already BACKLOG-074 shipped). |
| **TRIGGER** | P3 CST forward pilot; **or** `/admin/cst-steward` alias queue volume justifies batch. |

---

## BACKLOG-079 — Ops-list MasterDataGridShell parity (fold into phase — not standalone)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-29 · extracted from `feat/ops-master-grid-shell-parity` per D-021 |
| **Effort** | Medium (mechanical per page) |
| **Source** | D-021; commits `ddb712c`…`d789ad9` — shell on CPOR cases, PM gaps, shipment evidence, PVE |
| **Idea** | Re-apply `MasterDataGridShell` / ops list chrome to CPOR cases, product-master gaps, shipment evidence, PVE exception lists when those pages are touched. |
| **Why it matters / deferrable** | Masters already have the shell (BACKLOG-061 Theme B on main). Ops lists lag for consistency. **Do not schedule as a standalone project** — fold into whichever phase next edits those pages (P1 / A-lane touch CPOR and PM gaps). |
| **What the work is** | Native re-application on current routes (post–Unit F `shipment-evidence/` paths). Pagination → BACKLOG-085; URL helpers → BACKLOG-084. |
| **Regression traps** | Do not revive pre–Unit F paths; do not force community AG Grid (`fix/web-grid-community-stabilization` rejected). Per D-021: **do not resurrect** channel-ops KPI cards or `shippingUtcDates.ts` from ops-master — superseded by main’s commercial KPI rebuild. |
| **Behavior to retain** | Enterprise AG Grid pattern; existing filters/paging contracts. |
| **Out of scope** | Standalone “ops shell parity” epic; KPI/shippingUtcDates from ops-master; merging the whole ops-master branch. |
| **TRIGGER** | Phase work that already edits CPOR cases / PM gaps / shipment evidence / PVE pages; **or** Warren asks for chrome parity on a named page. |

---

## BACKLOG-075 — Unit F remainder (DSI relocate + inboundEvidence + rename shared helpers)

| Field | Detail |
|-------|--------|
| **Status** | **Shipped** · Unit F Tiers 1–3 · 2026-07-27 |
| **Effort** | Large (Tier 1–3 from `.tmp/unit_f_inventory.md`) |
| **Source** | Steward contract Known-gap Unit F; inventory 2026-07-27; Tier 0 orphan retire shipped same day |
| **Shipped as** | `inboundEvidence*` → `shipment-evidence/`; DSI cluster → `admin/imports/dsi/`; shared helpers → `steward*` in `import-steward/`; DSI filter logic → `dsi/dsiStewardCandidateFilterLogic` |
| **TRIGGER** | ~~After E2 commit lands; **or** Warren prioritizes import-steward barrel cleanup before next importer.~~ **Fired** — Warren finished Unit F. |

---

## BACKLOG-074 — CST import steward E2 (resolution-plan compute/apply-async)


| Field | Detail |
|-------|--------|
| **Status** | **Shipped** · Unit E2 · 2026-07-27 |
| **Effort** | Medium (mirror CPOR D-013 plan path + web toolbar) |
| **Source** | Unit E CONSULT NEED_HUMAN + Warren no-Opus E1 authorization; D-018; contract v1.5 Known-gap |
| **Shipped as** | `cst_resolution_plan*.py` + `/jobs/{id}/cst-resolution-plan*` endpoints + `CST_IMPORT_ENGINE_CONFIG` + `SLOT_CST_RESOLUTION_PLAN` (D-019) |
| **TRIGGER** | ~~Unit E1 Opus VERIFY PASS (or Warren waives VERIFY); or Warren prioritizes CST plan async before Unit F.~~ **Fired** — Warren prioritized E2 (VERIFY waived). |

---

## BACKLOG-078 — DSI layout-coalesce follow-ons (templates, fuzzy match, sheet-exclude UI)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-20 · renumbered from multifile **075** on 2026-07-27 merge |
| **Effort** | Medium–Large |
| **Source** | Fable CONSULT U6 READY (2026-07-20) + browser smoke job 553: presentation layout tabs shipped; API `dsi_excluded_mapping_keys` works; UI still lacks Exclude-sheet control on layout tab. |
| **Idea** | (1) Cross-batch layout memory/templates so next week’s same layouts auto-map. (2) Fuzzy/near-match layout grouping (superset headers). (3) Mapping-step UI to exclude undateable sheets (calls existing exclusions endpoint). (4) Optional per-member stamp chips inside a layout group. |
| **Why it matters / deferrable** | Operators still re-map weekly and must API/hack sheet exclude for junk Sell out sheets. Core coalesce + stamps soak first. |
| **What the work is** | UI exclude sheet; persist layout→mapping templates per source; optional fuzzy signature; stamp chips in group panel. |
| **Regression traps** | Do not re-key `field_mapping` away from `file::sheet`; do not auto-apply facts; stamps stay confirm-always. |
| **Behavior to retain** | One capable job; layout tabs with fan-out; detach/map separately; Dist/Period file stamps. |
| **Out of scope** | Exact-header batch splits (capability-merge locked). |
| **TRIGGER** | After job 553 (or successor) weekly soak completes steward→apply; **or** Warren hits undateable sheet again without API; **or** operators ask for “remember this layout”. |

---

## BACKLOG-077 — DSI weekly email-attachment auto-ingest (mailbox → propose queue)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-18 · renumbered from multifile **074** on 2026-07-27 merge |
| **Effort** | Large (mailbox connector + allowlist + activity-feed failures + same propose/batch path) |
| **Source** | Warren product discussion (2026-07-18): weekly DSI ops speed — email attach → app auto-upload; agree not silly, but premature until unified multi-file batch + mapping autosave + per-file distributor stamps soak-stable. |
| **Idea** | Inbound mailbox (allowlisted senders) drops attachments into the existing DSI **batch-propose** path: capability merge (one job for all mappable files), mapping memory, file stamps, steward queue. Never silent apply to facts. |
| **Why it matters / deferrable** | Removes manual Downloads→upload friction for weekly MUSTEK/PINNACLE/etc. Deferrable while batch UX still soaking; email would amplify wipe/gate/automap breakages. |
| **What the work is** | (1) Mailbox/poll or webhook + attachment extract. (2) Sender/subject/filename → source_id rules. (3) Call same `batch-propose` / `batch-jobs` as UI. (4) Land jobs in Import Centre review (mapping/stamps/steward). (5) Activity-feed FLAG on parse/auth failures — no silent drop. (6) Ops runbook for mailbox credentials. |
| **Regression traps** | No auto-create masters; no skip steward; no auto-apply; do not invent a second ingest pipeline; respect weekly vs historical mode; FLAG≠BLOCK leftovers stay reviewable. |
| **Behavior to retain** | Unified multi-file capability batch (not exact-header splits); per-file distributor stamps; durable mapping autosave; one steward surface for sell-out + SOH. |
| **Out of scope** | Silent fact apply from email; arbitrary public inbox; splitting sell-out vs SOH into separate steward products. |
| **TRIGGER** | Weekly multi-file batch soak passes (stamps + autosave + no mapping wipe) **and** Warren prioritizes mailbox ingest; **or** operators request email drop as the weekly intake path. |

---

## BACKLOG-073 — Import-job fact rollback / purge (test-junk cleanup; not park/exclude)


| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-10 |
| **Effort** | Large (per-importer fact contracts + audited purge + UI gate) |
| **Source** | Warren U-G2 smoke (2026-07-10) + Fable CONSULT: customers blocked from hard-delete by sell-out refs are **test import junk**, not bad production data. Park/exclude makes the master look messy and is the wrong tool (TMP provisional workflow only). Cheap default-hide of dispositioned rows **refused**. |
| **Idea** | Governed **import-job rollback/purge**: remove the junk **facts** (and related staging) that a test import wrote, so orphaned `dim_customer` / `dim_product` / `dim_distributor` hard-delete unblocks via existing usage guards — without weakening fact immutability for real sell-out. |
| **Why it matters / deferrable** | Test junk masters clutter admin grids and cannot be deleted while facts remain; operators need a clean path. Deferrable while real commercial data is healthy and junk is confined to known test jobs on cip/dev. |
| **What the work is** | (1) Discovery: which importers/jobs mint facts that block master delete (DSI sell-out first). (2) Preview: job → fact counts by table + affected dim ids. (3) Confirm purge: audited, chunked deletes of **that job’s** facts/staging only (respect latest-job-wins vs transaction-immutable contracts). (4) Then steward may hard-delete unreferenced dims. (5) Hard gate: never available as casual “delete customer with history” — job-scoped only. |
| **Regression traps** | Do **not** delete sell-out from the customer master delete UI; do not reassign FKs to OPEN_CHANNEL/sink to fake-clean; do not loosen `customer_usage` blockers for prod convenience; do not use park/exclude as archive; FLAG≠BLOCK leftovers must stay reviewable. |
| **Behavior to retain** | Hard-delete blocked while refs exist; park/exclude stays TMP no-code disposition only; merge soft-redirect for real duplicate identity. |
| **Out of scope** | Default-hiding parked/excluded rows as a substitute; prod cascade-purge tool; inventing `archived` status until a real-facts/no-merge case appears. |
| **TRIGGER** | Warren prioritizes cleaning test-import junk from cip/admin masters; **or** operators cannot promote/steward because TMP/test dims dominate lists; **or** after BACKLOG-061 Theme B (U-G2/U-B2) when master UX cleanup is next. |

---

## BACKLOG-070 — Frontend ESLint v9 flat-config gap (repo-wide lint broken)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-08 |
| **Effort** | Small–medium (web + root lint wiring) |
| **Source** | Agent session (2026-07-08): shipment apply hardening gate; `eslint` v9 installed; no `eslint.config.js` / flat config; `eslint .` fails repo-wide; `ESLINT_USE_FLAT_CONFIG=false` required for Next.js only; zero enforced frontend lint in default dev path. |
| **Idea** | Restore a single working lint entrypoint for `apps/web` and shared packages — either adopt ESLint 9 flat config (Next.js-compatible) or pin/document the legacy config path in CI and `pnpm lint`. |
| **Why it matters / deferrable** | Drift accumulates without lint gate; deferrable while Vitest + typecheck cover critical paths. |
| **What the work is** | (1) Audit `pnpm lint` / `apps/web` ESLint integration. (2) Add flat config or explicit legacy shim. (3) Wire CI to fail on lint. |
| **Regression traps** | Breaking Next.js 15 ESLint plugin; duplicate configs; CI false greens. |
| **Behavior to retain** | `pnpm test:web` unchanged; no rule thrash without cause. |
| **Out of scope** | Full design-system lint overhaul. |
| **TRIGGER** | Next frontend-heavy unit or CI hardening pass. |

---

## BACKLOG-071 — Clone-gate tooling: pg_dump/pg_restore not on shell PATH

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-08 |
| **Effort** | Small (docs + helper script) |
| **Source** | Agent session (2026-07-08): shipment apply clone gate; `pg_dump` not on PATH in PowerShell; binaries at `C:\Program Files\PostgreSQL\18\bin\`; gate used explicit full paths; prior session used `CREATE DATABASE … TEMPLATE cip` (not pg_dump proof). |
| **Idea** | Standardize disposable clone creation for destructive-class gates: `scripts/ops/clone_cip_db.py` wrapping explicit `pg_dump`/`pg_restore` paths (Windows + Linux), env override for bin dir, refuse `current_database()='cip'` writes. |
| **Why it matters / deferrable** | Agents substitute synthetic/template clones when PATH fails — invalid proof. Deferrable until next clone gate. |
| **What the work is** | (1) Document `PG_BIN` / `SMOKE_ADMIN_PASSWORD` in ops README. (2) Shared clone helper used by Plan D + shipment gates. (3) Optional: add PostgreSQL bin to dev PATH in onboarding doc. |
| **Regression traps** | Cloning while cip has active connections; wrong admin creds; partial restore. |
| **Behavior to retain** | Never write to `cip` from gate scripts; drop clone after proof. |
| **Out of scope** | Cloud/Supabase clone automation. |
| **TRIGGER** | Any future clone-gate or destructive-class apply proof task. |

---

## BACKLOG-068 — Landing-quarter attribution for landed-basis KPI (pod_date)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-07 · **A1 gating settled 2026-07-30** (Open Decision #4) |
| **Effort** | Medium (recon read model gains a landed sub-state + landing-quarter reattribution; new KPI surface; no schema — `pod_date` already on evidence + fact) |
| **Source** | PvE shipped/pipeline taxonomy fix (2026-07-07). Fill rate now correctly counts `line_state='shipped'` only, but recon still has **no landed gate**: `reconcile_case` reads `resolved_customer_id, product_id, quantity, amount, unit_price` — never `pod_date`. Confirmed on cip: of shipped-state units on linked POs, ~3% (88 rows / 5,331 units) have `pod_date IS NULL` (shipped, in-transit, not yet delivered) yet are credited as executed in the plan quarter. `docs/PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md` §Landed. |
| **Idea** | Add **Landed** as a sub-state of Shipped (`pod_date IS NOT NULL`) and, for a **landed-basis sales KPI**, attribute landed units to the **quarter they landed** (pod_date quarter), not the plan quarter. PvE v1 fill deliberately stays plan-quarter shipped-basis; landed is an additional lens, not a replacement. |
| **Why it matters / deferrable** | Sales/finance care about stock that actually **arrived** in a period (revenue recognition, sell-in timing). Deferrable because v1 fill (shipped-basis) is now correct and the shipped-not-landed gap is small (~3%); becomes material when landed-basis reporting or DSI landing attribution is scoped, or when transit times lengthen. |
| **What the work is** | (1) ~~Decide the KPI contract~~ **Decided 2026-07-30:** A1 v1 stays shipped-basis ungated; form = separate "Landed this quarter" tile + shipped-not-landed sub-signal (not landed-basis fill). (2) `reconcile_case` (or a sibling read) reads `pod_date`; split shipped into shipped-not-landed vs landed; optionally reattribute landed units to pod_date quarter. (3) Surface a Landed tile + shipped-not-landed pending sub-signal. (4) Tests: landed excluded from a plan-quarter landed KPI until pod_date present; reattribution to landing quarter. **P1 obligation:** shipment census reports `pod_date` present vs NULL % (measurement only — not this build). |
| **Regression traps** | Do NOT gate v1 shipped-basis fill on landed (keep the two lenses distinct); do not double-count a unit in both plan quarter (shipped) and landing quarter (landed) within the same KPI; `pod_date` is nullable — null must mean "not landed yet", never "excluded"; no migration (fields exist). |
| **Behavior to retain** | Shipped-basis fill = `line_state='shipped'` (BACKLOG-068 does not change it); pipeline = `open_order`; shipping module remains lifecycle authority for `pod_date`. |
| **Out of scope** | Cancellation modeling (BACKLOG-063); sell-through/velocity (DSI); changing the shipped/pipeline gate; branch/location tagging; re-opening A1 fill gating (settled ungated). |
| **TRIGGER** | When **Shipping** (not PvE) scopes landing-quarter reattribution / budget consumption lens; **or** transit lag makes shipped-not-landed gap material. Prerequisite: BACKLOG-088 POD propagation so measurement is truthful. |

---

## BACKLOG-067 — Backfill file-provenance gap (unified_lineup / bulk_backfill paths)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-06 |
| **Effort** | Medium (wire `RawFileMetadata` + `StorageBackend.save` on unified/bulk paths **or** document intentional omission + archive path contract) |
| **Source** | PO Management identical-BU-pairs forensic audit (2026-07-06): implicated cases from `unified_lineup` and `bulk_lineup_backfill` have **empty** `raw_file_metadata`; original `.xlsx` bytes **not recoverable** from disk. Standard `imports.py` upload path persists bytes via `StorageBackend.save()` + `RawFileMetadata.storage_key`. Evidence: `.tmp/audit_po_recon_identical_bu_pairs_output.json` provenance samples. |
| **Idea** | Close the auditability hole: backfill/unified lineup imports should retain original uploaded bytes (or a durable archive pointer) the same way the standard import pipeline does. |
| **Why it matters / deferrable** | `CommercialLineupLine.raw_row_payload` + `source_row_number` suffice for **DB-only** fingerprint/duplication audits today. Deferrable until file-level re-audit or compliance requires source retention. Critical for a product whose wedge is auditability when stewards must re-open the workbook. |
| **What the work is** | (1) Trace unified-import and bulk-backfill dispatch — where file bytes go after parse. (2) Either persist via existing `RawFileMetadata` pattern or formalize external archive path + DB pointer. (3) Verify read path for steward re-download. (4) Document which paths guarantee retention vs heuristic `file_name` only. |
| **Regression traps** | Do not break async parse fan-out; do not store secrets in `staged_metadata`; large archive backfills may need size guards; disposable-smoke DBs should not inherit prod storage keys. |
| **Behavior to retain** | `raw_row_payload` on parsed lines; `import_job_id` + `file_name` on cases; standard import path retention unchanged. |
| **Out of scope** | Re-parsing all historic cases; changing rollup projection (`1586f1e`). |
| **TRIGGER** | When **file-level re-audit or re-ingest of backfill cases** is needed; **or** before **multi-tenant onboarding** where source retention is a compliance expectation. |

---

## BACKLOG-066 — #39/#40 duplicate-ingestion repair (ACZA Q1 2025 Consumer Lineup)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-06 |
| **Effort** | Small (steward supersession of duplicate case; disposable-clone proof before apply) |
| **Source** | `check_lineup_duplicate_ingestion` on cip (2026-07-06): one workbook `Product Lineup/NB/2025/Q1/1. ACZA Q1 2025 Consumer Lineup - Sales.xlsx` parsed into **two** active cases — **#39** (NR) and **#40** (NV) — identical 72-line fingerprint (`source_row_number`, `product_id`, `quantity_units`). Pre-`6b84187` fan-out; forward fix did not repair existing rows. Evidence: identical-BU-pairs audit JSON in `.tmp/`. |
| **Idea** | Repair via **steward panel** — soft-supersede the duplicate case (`commercial_status=superseded`, `superseded_by_case_id` on keeper), never raw SQL delete. Test on disposable clone before apply on `cip`. |
| **Why it matters / deferrable** | After rollup projection (`1586f1e`), duplicated lines **double-count within a BU group** wherever both cases link into the same period×product_line group (e.g. 24Q4 PF/NR share cases 39+40). Deferrable until data-hygiene unit or before intelligence view is trusted on affected periods. |
| **What the work is** | (1) Confirm keeper case (correct BU label for workbook intent). (2) Supersede loser via existing supersession workflow. (3) Re-run `check_lineup_duplicate_ingestion` → 0 clusters. (4) Verify PO Management backlog for 24Q4/25Q1 affected groups. |
| **Regression traps** | Do not delete cases or lines; do not break `commercial_lineup_case_po` links without steward review; preserve `raw_row_payload` on keeper; no special-case filters in `backlog()` — fix data not projection. |
| **Behavior to retain** | Latest-wins supersession semantics (`20260701_0065`); PO links on keeper case; projection logic unchanged. |
| **Out of scope** | Bulk repair of all historical duplicate-ingestion clusters; changing parse fan-out for new imports (separate if still needed). |
| **TRIGGER** | **Next data-hygiene unit**; **or** before **intelligence view** is trusted on periods where cases **#39** / **#40** (or successor duplicates) participate in linked PO reconciliation. |

---

## BACKLOG-054 — Disposable-smoke migrate safety gap (`DATABASE_URL_SYNC_MIGRATE` fall-through)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-01 |
| **Effort** | Small (env override checklist + optional guard in alembic preflight or smoke helper script) |
| **Source** | Spec C Step A session (2026-07-01): disposable `cip_alembic_smoke` migration smoke briefly applied `20260701_0064` to `cip` because `DATABASE_URL_SYNC` alone was overridden while `DATABASE_URL_SYNC_MIGRATE` in `.env` still pointed at `cip`. Caught and downgraded before review; approved apply to `cip` followed in a separate step. |
| **Idea** | Disposable-smoke migrate runs must **never** fall through to `.env`'s `DATABASE_URL_SYNC_MIGRATE` (which points at `cip` for local dev). Require **both** `DATABASE_URL_SYNC` and `DATABASE_URL_SYNC_MIGRATE` in the smoke override set; optionally refuse `alembic upgrade` when a smoke-run marker is set and the resolved migrate DB is `cip`. |
| **Why it matters / deferrable** | A single missed override can mutate the shared dev DB during what was meant to be a read-only or disposable clone test. Deferrable until the next disposable-smoke migration — but the inverse mistake (smoke env left set → downgrade hits wrong DB) is equally dangerous. |
| **What the work is** | (1) Document in `AGENTS.md` / dev notes: smoke migrate requires **both** sync URLs overridden to the disposable DB name. (2) Optional: `scripts/ops/` or `.tmp/` helper that prints resolved migrate URL + `current_database()` and aborts if target is `cip` when `CIP_SMOKE_MIGRATE=1`. (3) Update migration smoke test docs to set `DATABASE_URL_SYNC_MIGRATE` explicitly. |
| **Regression traps** | Do not block legitimate `cip` upgrades when env is clean; do not change default `.env` migrate URL semantics for normal dev; `get_settings()` LRU cache must be cleared or subprocess used when testing overrides. |
| **Behavior to retain** | `database_url_sync_migrate` optional override for postgres-superuser migrations on `cip`; disposable clone workflow via `cip_alembic_smoke` template. |
| **Out of scope** | Changing Alembic revision chain; auto-creating smoke DB in CI. |
| **TRIGGER** | Before the **next** disposable-smoke migration run; **or** any session that runs `alembic upgrade` with partial env overrides. |

---

## BACKLOG-055 — Lineup BU resolver thresholds provisional (25% / 5% guesses)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-01 |
| **Effort** | Small (distribution audit + constant retune + tests; no schema) |
| **Source** | Spec C Step A (`lineup_business_unit_resolution.py`): `PRODUCT_DERIVED_MIN_RESOLVED_FRACTION = 0.25` and `LIKELY_NOT_LINEUP_RESOLUTION_RATE = 0.05` mirror product-line inference guesses, not empirical lineup-archive rates. |
| **Idea** | Retune product-tier win threshold and `bu_likely_not_lineup` cutoff from **real** resolution-rate distribution after bulk backfill — thin-catalogue BUs (accessories, networking) may legitimately resolve low without being PF spec-dumps. |
| **Why it matters / deferrable** | Wrong thresholds either false-flag real lineups as `bu_likely_not_lineup` or let spec-dumps through on sheet/folder fallback. Deferrable until Step C produces a resolution-rate histogram across ~30+ archive files. |
| **What the work is** | (1) After Step C backfill, aggregate per-sheet `product_resolution_rate` + flag rates by BU/folder. (2) Adjust `PRODUCT_DERIVED_MIN_RESOLVED_FRACTION` / `LIKELY_NOT_LINEUP_RESOLUTION_RATE` with documented percentiles. (3) Add regression tests for thin-catalogue BU files if any exist in archive sample. |
| **Regression traps** | Do not block linking/reconcile on low resolution (flags only); do not conflate `product_line` majority with `business_unit`; preserve multi-BU and label-mismatch flags independent of threshold retune. |
| **Behavior to retain** | BU derivation tier order (product → shipment → sheet → folder → manual); flag ≠ block. |
| **Out of scope** | Changing product resolution tiers; DSI eligibility. |
| **TRIGGER** | After **first full lineup backfill** (Spec C Step C) produces a resolution-rate distribution; **or** steward reports systematic false `bu_likely_not_lineup` / wrong product-tier wins on thin-catalogue files. |

---

### Q4 — Supersession retention

**RESOLVED 2026-07-01.** Soft latest-wins — superseded case retained + flagged, not deleted. See §7.

---

## BACKLOG-059 — Catalogue upload: explicit column semantic mapping + cross-check fallback

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-01 |
| **Effort** | Medium (mapping UI + validation + fallback cross-check rules) |
| **Source** | Spec C production-ready pass (2026-07-01): `dim_product.business_unit` (division) vs `product_line` (folder-grain BU) trap exposed by bulk backfill BU resolver fix; same class of error one level up on catalogue import column mapping. |
| **Idea** | On catalogue (Product Master) import, each source column must be **explicitly mapped** to its semantic role — product line / folder-grain BU vs division (`business_unit`) vs series vs other attributes — so relationships build correctly. Add a **fallback cross-check** against a second mapped column when the primary mapped column looks mislabelled or gamed (e.g. division values in a product_line slot). |
| **Why it matters / deferrable** | Silent mis-mapping poisons entity resolution, BU inference, and lineup backfill product-tier corroboration. Deferrable until second-tenant catalogue onboarding when column layouts may diverge from ACZA conventions. |
| **What the work is** | (1) Extend catalogue import mapping to require semantic role per column (not just field name). (2) Post-map validation: flag when mapped `product_line` values look like division codes or vice versa. (3) Optional second-column majority cross-check when primary column fails sanity rules. (4) Steward surface to confirm/correct before commit. |
| **Regression traps** | Do not auto-rewrite mapped values; do not conflate `product_line` with `business_unit` in persistence; preserve existing PM upsert keys and steward governance. |
| **Behavior to retain** | PM owns products; import evidence is evidence; no auto-create without steward approval. |
| **Out of scope** | Lineup bulk backfill resolver; DSI product tiers. |
| **TRIGGER** | Before **second-tenant catalogue onboarding**; **or** steward reports division/product_line mis-mapping on a new catalogue file layout. |

---

## BACKLOG-060 — Bulk backfill post-apply completion UX (progress, summary, next-step CTAs)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-02 |
| **Effort** | Medium (dialog apply-step state machine + read-only session status endpoint + activity-feed registration fix; optional bell aggregation) |
| **Source** | Warren session (2026-07-02): first live bulk backfill apply on `cip` — 31 `parse_lineup_case` tasks succeeded in Celery worker, but `BulkLineupBackfillDialog` closed immediately with no success signal; operator had to read worker logs. Chat proposal (same session): layered completion UX vs `UnifiedLineupImportDialog` (stays open with per-file results + bell guidance). Paths: `BulkLineupBackfillDialog.tsx`, `lineup_bulk_backfill_api.py`, `lineup_bulk_backfill_apply.py`, `backgroundTaskRegistry.ts`, `GlobalBackgroundTasksIndicator.tsx`, `PoManagementView.tsx` / `/admin/po-management`. |
| **Idea** | After bulk backfill **Apply**, steward must see **in-app** progress and a **completion summary** with explicit **next steps** — not silence + dialog close. Minimum: applying/parsing/done phases in dialog (or persistent snackbar), counts (cases created, parses ok/failed, superseded), primary CTA **Link POs** → `/admin/po-management`, secondary **Review lineup cases** → Commercial Planner. Activity bell should show one aggregated session job (`importJobId` = session job) with parse progress; fix current `registerClientBackgroundTask` call missing `importJobId`. Optional read-only `GET …/bulk-backfill/sessions/{id}/status` aggregating `staged_metadata.bulk_lineup_backfill_apply` + child parse outcomes. **No auto-redirect** to PO Management. |
| **Why it matters / deferrable** | Without completion UX, operators cannot tell apply succeeded, how many cases parsed, or that Spec C Step C continues with period-by-period PO link-apply. Deferrable immediately after first successful apply proved the pipeline works — but before a second steward session or onboarding another operator. |
| **What the work is** | (1) **Apply step UI** — replace instant `onClose()` with dispatched → parsing → complete/failed; optional "run in background". (2) **Completion panel** — case id range, applied/superseded/unresolved line counts, collision losers noted. (3) **Next-step CTAs** — PO auto-link (primary), lineup cases, import session `job_id`. (4) **Bell parity** — register session with `importJobId`; poll aggregated status; label e.g. `Bulk lineup backfill · 18/31 parsed`. (5) **Status endpoint** (read-only) for dialog + bell poll. Reference bar: `UnifiedLineupImportDialog` post-upload results table + `ImportJobLoadedSuccessCallout` pattern on other importers. |
| **Regression traps** | Do not block navigation; do not auto-run PO link-apply; do not spam 31 separate bell entries; preserve async apply + per-case parse enqueue; fix `registerClientBackgroundTask` without breaking DSI/shipment kinds. |
| **Behavior to retain** | Preview-first apply; soft supersession; parse jobs async via worker; PO link-apply remains separate steward workflow on PO Management page. |
| **Out of scope** | Auto-filter PO Management by earliest period; email/push notifications; post-apply reconciliation report (see BACKLOG-051). |
| **TRIGGER** | Before **second** steward bulk backfill session **or** onboarding another operator to backfill; **or** any report of "did apply work?" without checking Celery logs; **or** when starting PO link-apply UX polish (pair with Spec C Step C). |

---

## BACKLOG-057 — Bulk preview persists ImportJob on live API (not read-only)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-01 |
| **Effort** | Small (in-memory preview session **or** loud docs + size guard) |
| **Source** | Step B `persist_preview_session` — writes `ImportJob.staged_metadata` + base64 file manifest; ~60 files may be heavy. |
| **Idea** | "Preview is read-only" is false against lineup tables but still writes coordinator `ImportJob` rows on live API. Fix: non-persisting preview **or** document loudly + optional manifest externalization. |
| **TRIGGER** | Before first live-API backfill session. |

---

## BACKLOG-058 — Bulk apply `import_background_slots` dedicated registry entry

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-01 |
| **Effort** | Small |
| **Source** | `lineup_bulk_backfill_api.py` uses `SLOT_MAIN`; DSI apply uses dedicated slot + registry. |
| **Idea** | Dedicated slot/registry entry for bulk lineup apply to match DSI parity and avoid orphan-slot clears. |
| **TRIGGER** | If bulk apply contends with DSI for the main slot. |

---

## BACKLOG-053 — Per-line ROE (rate of exchange) override on lineup lines

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-28 |
| **Effort** | Small (explicit override field on `commercial_lineup_line` + pricing-chain source tag + UI affordance + tests; migration if persisted) |
| **Source** | Warren session (2026-06-28) lineup workbench review. Question raised: "should rate of exchange be editable?" Current behaviour: ROE is resolved (file evidence → trade-term defaults) and stored in `pricing_chain_json`, edited only via Planner defaults. Code: `apps/api/app/services/commercial_planner/lineup_pricing_resolution.py` (`roe_local_per_cost_currency`, `_pick(file_roe, defaults.roe_local_per_cost_currency, normalise_pct=False)`); defaults editable in `PlannerDefaultsMaintenance.tsx`. Deferred explicitly by Warren: "PUT ROE on backlog because we are still working on what's already approved/shipped." |
| **Idea** | Allow a **deliberate, labelled** per-line ROE override (e.g. a deal locked at a specific FX rate) instead of the resolved default. Recorded in the pricing chain as `source: line_override` so it stays auditable. NOT an anonymous editable cell. |
| **Why it matters / deferrable** | Real deals sometimes lock an FX rate that differs from the standing default. Deferrable because: (1) no confirmed business case yet that a per-line locked rate is needed; (2) a free-typed per-line ROE invites silent inconsistency across a lineup and can undermine the value-reconciliation FX bridge (`commercial_sku_assumption.fx_plan_currency_per_cost_currency`); (3) current work is focused on already-approved/shipped scope (confirm-with-PO, suggested POs, distributor suggestion, grid migration). |
| **What the work is** | (1) Add an explicit override input (and, if persisted, a nullable `roe_override_local_per_cost_currency` column on `commercial_lineup_line` — STOP/report before migration). (2) `resolve_line_pricing` prefers the override and records `sources["roe_local_per_cost_currency"] = "line_override"` in `pricing_chain_json`. (3) UI: an explicit "Override ROE" action on the line that visibly marks the line as overridden and shows the default it replaced — never a silently-editable number. (4) Tests: override wins over default + file; chain records `line_override`; clearing override falls back to resolved value. |
| **Regression traps** | Don't turn ROE into an unlabelled editable cell (breaks explainability); don't `/100` or otherwise mutate the rate; don't break the FX-bridge value reconciliation when an override is present; preserve trade-term default fallback when no override. |
| **Behavior to retain** | ROE default-driven by Planner defaults; every pricing input carries its source in the chain; DAP evidence-only; value reconciliation FX bridge intact. |
| **Out of scope** | Changing the standing default editing surface; per-line overrides of other pricing inputs (margins/rebate) — those follow their own decision; any change to the value-reconciliation bridge itself. |
| **TRIGGER** | Business confirms a real need for per-deal locked FX on a lineup (a deal negotiated at a fixed rate that must override the standing default); **or** Warren explicitly approves building the override. |

---

## BACKLOG-052 — Lineup margin-amount evidence capture (when a margin column holds currency, not a %)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-28 |
| **Effort** | Small (migration: 3 nullable Numeric columns on `commercial_lineup_line` + parser routing + tests) |
| **Source** | Warren session (2026-06-28) lineup fix pass. Guard shipped: `apps/api/app/services/commercial_planner/lineup_pricing_resolution.py` (`sanitize_pct_evidence`) + `lineup_case_parser.py` (`_PCT_EVIDENCE_FIELDS`, `pct_evidence_out_of_range` diagnostic). Discovery DB evidence: in live cases #3/#4/#5 the `Dealer margin` / `Disti margin` / `Rebate` columns are genuine fractions (`0.08`, `0.0724`, `0.06`); the only currency-in-margin-column case was the corrupt case #6 file (now ignored). No live file pairs a margin **pct** with a margin **amount**, so building amount-capture now has no real driver. |
| **Idea** | When a margin/rebate column value is out-of-range for a percentage (the `sanitize_pct_evidence` trigger), route the **amount** to a dedicated `*_amount_evidence` column instead of only dropping it. Today the guard drops it (keeping it in `raw_row_payload` + flags `pct_evidence_out_of_range`) to prevent `Numeric(8,4)` overflow. |
| **Why it matters / deferrable** | Captures real Rand margin evidence without overflow and without it silently becoming a pct. Deferrable because **no current real file** carries margin amounts in the margin columns (they carry pct + separate price columns `Dealer price` / `Net price` / `Disti Cost`). Acting now risks adding columns + a migration to capture values that only appeared in a known-corrupt file. |
| **What the work is** | (1) **Migration (STOP/report first):** add `dealer_margin_amount_evidence`, `rebate_amount_evidence`, `distributor_margin_amount_evidence` (Numeric(18,4), nullable, local currency) on `commercial_lineup_line`. (2) **Parser:** in `lineup_case_parser`, when `sanitize_pct_evidence` rejects a value as a pct, write the amount to the matching `*_amount_evidence` column instead of only dropping; keep `sanitize` as the overflow guard; genuine pcts still populate the `*_pct_evidence` columns. (3) **Tests:** Rand amount in margin column → amount lands in `*_amount_evidence`, pct column null, no overflow; true pct → pct populated, amount null. |
| **Regression traps** | Do not let an amount silently become a pct (no `/100`); keep `sanitize_pct_evidence` as the guard; do not change trade-term fallback (pricing still falls back to `commercial_customer_term` / `commercial_distributor_term` when pct absent); preserve `raw_row_payload` audit. |
| **Behavior to retain** | `pct_evidence_out_of_range` diagnostic; overflow-safe parse; pricing chain fallback to trade-term defaults; DAP evidence-only. |
| **Out of scope** | Header detection / wrong-header-row fixes for malformed workbooks (that is a per-file data issue, e.g. case #6); changing the pct normalisation rule; any qty mapping change for files without a separate `Total Qty` column. |
| **TRIGGER** | A real lineup workbook arrives that carries margin/rebate **amounts** (Rand) in the margin columns (with or without a separate pct), **and** Warren wants those amounts persisted as evidence; **or** pricing needs amount-based margin evidence for a customer/period where pct is unavailable. |

---

## BACKLOG-051 — Post-apply import reconciliation report (file vs facts)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-28 |
| **Effort** | Medium (API read model + DSI UI panel + export); small follow-on per importer |
| **Source** | Warren session (2026-06-28): manual RAW.xlsx vs `import_job #96` facts audit after large-volume DSI apply. Script: `.tmp/audit_raw_vs_db.py` / `.tmp/audit_raw_vs_db_summary.json`. Job #96: 178,067 staged rows; 20,618 Excel rows expected facts but not applied (mostly unresolved product; 111 unresolved customer). Distributor SOH snapshots (no customer name + disti + SOH): 63,408 rows, 54,435 applied inventory, 8,275 blocked on product. Chat: Warren asked whether system should automate this — agreed good feature, deferred to backlog. |
| **Idea** | **Post-apply reconciliation** on an import job: compare stored raw file + staging lines + committed facts; report what from the file did **not** land as facts and **why** (unresolved product/customer, auto-excluded, deduped by `source_key`, staged-only). Aggregated by default; CSV export for steward action. |
| **Why it matters / deferrable** | Operators need trust after large applies (“did my SOH / sell-out actually load?”). Data already exists on the job (raw bytes, `import_distributor_si_staging_line`, facts). Deferrable while one-off script + steward workflow closes job #96 gaps; becomes essential at volume and for on-prem handoff. |
| **What the work is** | (1) **API** `GET /import-jobs/{id}/reconciliation` (DSI first): row counts by expectation type (sell-out, return, disti SOH snapshot), applied vs missing, top blocked tokens, volume sums. (2) **Semantics:** document disti SOH snapshot rule (no customer + distributor + SOH → `fact_inventory_distributor` at `as_of_date`); separate row-level from `source_key` dedup. (3) **UI** on DSI apply-complete / loaded step: summary panel + “Download gap report”. (4) **Reuse raw on job** — no re-upload. (5) Port pattern to shipment after DSI proves shape. |
| **Regression traps** | Treating `source_key` dedup as data loss; comparing Excel tokens to fact IDs without staging join; loading 178k-row detail in browser (aggregate + export only); conflating validate blockers with apply gaps. |
| **Behavior to retain** | Staging `source_row_number` as join key; `apply_status` + `diagnostic_codes` as reason source; transaction-immutable / latest-job-wins fact semantics unchanged. |
| **Out of scope** | Auto-fixing unresolved entities; re-apply; changing resolution tiers; BACKLOG-049 unresolved worklist (complementary — reconciliation is per-job, worklist is cross-job). |
| **TRIGGER** | Warren requests reconciliation UI; **or** second large DSI apply needs gap audit; **or** BACKLOG-049 unresolved worklist starts (reconciliation feeds worklist inputs). |

---

## BACKLOG-049 — Unresolved module (ignore → unresolved worklist)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-25 |
| **Effort** | Medium (read model + steward UI worklist surface) |
| **Source** | Warren session (2026-06-25): DSI steward legibility + auto-exclude at validate. `apps/api/app/services/imports/dsi_product_running_change.py` (`steward_ignored_line:<reason>`, `build_dsi_apply_exclusion_summary`); `dsi_apply_completion.py` (`apply_exclusion` in completion payload); candidate `context.steward_ignore_reason_code` JSONB; `docs/BACKLOG.md` TRIGGER defers full module until PM catalogue or operational reporting need |
| **Idea** | **Reader** over reasoned exclusions (`apply_exclusion` summary + candidate `steward_ignore_reason_code` / staging `steward_ignored_line:<reason>`). Surfaces excluded volume as a **tracked worklist**, grouped by reason: `ignore_no_catalogue` → re-attempt when PM catalogue loads; `ignore_no_receipt_evidence` → re-attempt as shipment coverage grows; `ignore_sku_indeterminate` → stays parked (genuinely undecidable; needs SKU in feed). |
| **Why it matters / deferrable** | Excluded lines carry real units/value; this is the path to reclaim them, not lose them. Reason codes are the contract — already split three ways. Deferrable until PM consolidated catalogue loads or first operational need to report/action excluded volume. |
| **What the work is** | (1) Read model aggregating `apply_exclusion` + per-job excluded tokens from staging diagnostics and ignored candidates. (2) Worklist UI (module or steward tab) with reason-grouped rows, units, value, dominant month, re-attempt triggers. (3) Wire `apply_exclusion` into imports wizard apply-complete step (API-only today). (4) Optional: reverse ignore → needs_review using `steward_ignore_remap_context`. |
| **Regression traps** | Treating auto-excluded-at-validate lines as silent (must stay in `apply_exclusion`); conflating parked indeterminate with reclaimable no-catalogue; migration for reason codes (not needed — JSONB + diagnostics). |
| **Behavior to retain** | Reason codes in candidate `context` + staging diagnostics; no fact write for `rpid is None`; steward-ignore demotion semantics; apply_exclusion as honest counterpart to resolution-quality denominator. |
| **Out of scope** | Resolver tier/eligibility edits; new facts; auto-exclude logic itself (shipped separately on validate). |
| **TRIGGER** | PM consolidated catalogue loaded; **or** first need to report/action excluded volume operationally; **or** build **after** job #96 applied (need real exclusion data to read). |

---

## BACKLOG-048 — Import Celery + background-task parity audit (dispatch, slots, polls, cancel)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-24 |
| **Effort** | Medium–large (audit doc + phased fixes); overlaps BACKLOG-039 queue split |
| **Source** | Warren session (2026-06-24): request for Celery and task parity audit in backlog. `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` §1b–1c (per-importer slot copy-paste, orphan slots on cancel); `apps/api/app/services/imports/import_background_slots.py` (`TASK_SLOTS` registry — partial Phase 2); `background_tasks.py` discovery readers; `import_job_task_control.py` + `import_job_background_metadata.py` (`clear_background_task_metadata` legacy gaps); `docs/memory/derived/platform_async_and_background_truth.md`; `.cursor/rules/import-parity.mdc` (apply = async dispatch + registered slot); existing poll/queue items **BACKLOG-039** (queue split), **BACKLOG-041** (compute poll grace), **BACKLOG-038** (dev beat/reaper), **BACKLOG-015** (cancel revoke all tasks); shipment vs DSI dispatch (`_dispatch_shipment_apply`, `_dispatch_dsi_apply`, `dsi_resolution_plan_enqueue`, `product_master_workflow` PM validate/commit slots) |
| **Idea** | Background work across importers is **not at one parity bar**: Celery task names, enqueue helpers, `staged_metadata` slot keys/kinds, activity-feed registration, cancel/retry slot clearing, dev `in_process_thread` fallback, and frontend poll budgets differ per template. Orphan slots, invisible progress, and false queue-timeout UX recur when a new path writes a slot without registry entry or poll wiring. |
| **Why it matters / deferrable** | Solo-worker dev topology masks some gaps; shipment backfill and DSI historical soak exposed queue-wait vs execution confusion. Deferrable as an **audit-first** deliverable before wide refactors — but should run before scaling imports or on-prem cutover. |
| **What the work is** | (1) **Audit matrix** (per `template_slug` / pipeline): validate dispatch, apply/commit dispatch, steward bulk, plan compute, derive side-effects (velocity/SOH/forecast/lineup parse); Celery task id; slot key + kind; sync fallback; progress callback; frontend poll route + grace. (2) **Registry gaps:** any writer not using `import_background_slots`; any clearer not using `clear_all_task_slots`; duplicate enqueue helpers (e.g. velocity). (3) **Cancel/retry:** full revoke list vs slot registry; confirm no orphan feed entries after cancel. (4) **Parity targets:** shipment apply/bulk/validate aligned with DSI; PM commit/validate visible in feed; generic `process_job` vs dedicated tasks documented. (5) **Output:** update `IMPORT_FLOW_CAPABILITY_CONTRACT.md` + `platform_async_and_background_truth.md` with as-built table; phased fix list (may feed BACKLOG-039). |
| **Regression traps** | Breaking `in_process_thread` dev path; revoking wrong Celery ids; clearing slots before worker finishes; changing poll semantics without `DEV_TOPOLOGY` doc; DSI historical auto-apply timing (BACKLOG-040). |
| **Behavior to retain** | Broker → dev in-process thread → sync fallback chain; every background task registered in activity feed; import-parity governance; latest-job-wins / evidence semantics unchanged. |
| **Out of scope** | Full Phase 3 declarative wizard (`page.tsx` contract codegen); production multi-worker provisioning (unless audit TRIGGERs infra sprint); changing DSI resolution tier order. |
| **TRIGGER** | Warren requests Celery/task parity audit; **or** new background task added without `import_background_slots` entry; **or** orphan-slot / invisible-progress incident on any importer; **or** BACKLOG-039 queue split starts (audit is prerequisite). |

---

## BACKLOG-047 — Import wizard: stale column-mapping UI after Back + re-upload

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-24 |
| **Effort** | Small–medium (web); may touch shared `CanonicalColumnMappingPanel` |
| **Source** | Warren session (2026-06-24): on inbound shipment import, click **Back**, re-upload a **new** file — dropdown mapping UI still reflects the **previous** file (column/target selections stale) while validate/apply still proceeds on the new job. `apps/web/src/app/(app)/admin/imports/page.tsx` (`shipmentMapDraft`, `shipment-mapping-state` query, upload `onSuccess` invalidation, wizard Back handlers without full draft reset); `CanonicalColumnMappingPanel.tsx` (Autocomplete sections: “Selected for this column”, “Already mapped in this file”); parallel DSI path (`dsiMapDraft`, `dsi-mapping-state`) likely same class of bug |
| **Idea** | Wizard **client state** (mapping draft, query cache, panel local filter) is not fully reset when the operator navigates back to upload and creates a **new** job with different headers. UI misleads (old column names / targets in Maps-to dropdown); server uses new job file — **silent mismatch** until operator notices or validate surfaces errors. |
| **Why it matters / deferrable** | Confusing for weekly ACZA re-uploads and BOM-tab workbook iterations; risk of wrong mappings saved if operator trusts stale UI. Deferrable while operators can hard-refresh or avoid Back+re-upload (upload once per session); fix should be shared across shipment + DSI mapping steps. |
| **What the work is** | (1) **Repro matrix:** shipment + DSI (+ PM if applicable) — Back from mapping → re-upload → Next; with/without `?job=` deep link. (2) **Reset contract:** on new `lastJobId` from upload — clear `shipmentMapDraft` / `dsiMapDraft` immediately; `removeQueries` or `resetQueries` for prior job mapping-state keys; reset `upload.isSuccess` gate if it pins poll job id; optional `key={lastJobId}` on `CanonicalColumnMappingPanel` to remount. (3) **Loading guard:** do not render mapping table until `shipment-mapping-state` / `dsi-mapping-state` matches current `lastJobId` and infer complete (spinner, not stale rows). (4) **Tests:** vitest for draft reset + query key on re-upload. (5) **UX:** banner “New file — previous mapping cleared” when job id changes mid-wizard. |
| **Regression traps** | Breaking revisit `?job=` remap flow (`shipmentPostValidateRemap`); wiping intentional draft edits on same job; race with server-derived step auto-advance (`shipmentDerivedStepRef`); DSI `dsiContinueToApplyAllowed` gate keys. |
| **Behavior to retain** | Post-validate re-map without re-upload; server `field_mapping` as source of truth after load; save-before-validate gate; deep-link job revisit. |
| **Out of scope** | Server-side re-upload on same job id; full wizard contract refactor (IMPORT_FLOW_CAPABILITY_CONTRACT Phase 3). |
| **TRIGGER** | Warren reports stale mapping UI again after ACZA/BOM workbook iteration; **or** BACKLOG-046 sheet-policy work touches mapping infer; **or** import UX hardening sprint (BACKLOG-045/044). |

---

## BACKLOG-046 — Shipment ACZA workbook: exclude / handle non-operational sheets (e.g. BOM Not Ready)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-24 |
| **Effort** | Small–medium (API + web mapping UX); optional phase 2 if BOM tab becomes first-class feed |
| **Source** | Warren session (2026-06-24): `ACZA Shipped Unshipped 20260623.xlsx` new **BOM Not Ready** tab pollutes shipment column-mapping stage (different columns); research in chat (no code). `apps/api/app/services/imports/shipment_evidence_import.py` (`_load_frames_for_job` — all sheets); `shipment_field_mapping.py` (`_union_frame_headers` — unions headers from every sheet for mapping UI); `shipment_evidence_report_detect.py` (`detect_report_type` — `REPORT_UNKNOWN` skipped at validate); CST precedent: `customer_sell_through_period.py` (`is_summary_sheet_name`); `docs/platform_import_system_truth.md` / BACKLOG-001 area (multi-sheet mapping deferred) |
| **Idea** | ACZA shipment workbooks can include **non-operational tabs** (e.g. **BOM Not Ready** — BOM / readiness exception queue) alongside **Shipped** and **Unship**. CIP unions **all** sheet headers into one mapping surface but only ingests sheets that pass `detect_report_type`. Operators see confusing extra columns at map time; risk that a tab with Unship-like headers is **misclassified and ingested** as open-order evidence. |
| **Why it matters / deferrable** | Blocks clean weekly ACZA uploads without manual Excel surgery. Deferrable while operators can trim workbooks (Shipped + Unship only) for current uploads; product fix should follow explicit business rule on whether BOM-hold rows belong in inbound shipment facts. |
| **What the work is** | (1) **Business rule (Warren):** confirm BOM Not Ready is **out of scope** for `fact_inbound_shipment` / standard ACZA apply (recommended default: exclude). (2) **Sheet inclusion policy:** ACZA allowlist (`Shipped`, `Unship`) and/or denylist patterns (`BOM`, `Not Ready`, summary/index) — mirror CST `is_summary_sheet_name` pattern in shipment load path. (3) **Mapping UX:** union headers **only from in-scope sheets**; surface skipped sheets in `inferred_schema.sheets` / validate summary with `report_type: unknown` + “ignored” badge (extend `CanonicalColumnMappingPanel` manifest if needed). (4) **Safety:** audit `detect_report_type` column heuristics so exception tabs sharing Unship/Shipped headers cannot silently ingest (sheet name + allowlist guard). (5) **Optional phase 2:** dedicated `report_type` + per-sheet mapping only if planning needs BOM-hold rows in-platform. |
| **Regression traps** | Dropping real Shipped/Unship rows; breaking historical ACZA backfill jobs that relied on full workbook; changing `source_key` / line_status for ingested rows; mapping saved on job that no longer matches unioned headers after rule change. |
| **Behavior to retain** | Shipped + Unship ingest semantics; `REPORT_UNKNOWN` skip at validate; evidence preserved per job; no auto-create masters; latest-job-wins fact upsert. |
| **Out of scope** | Full per-sheet mapping parity with historical lineup (unless TRIGGER fires for broader multi-sheet mapping); BOM / configurator as separate product module; changing DSI corroboration tier order. |
| **TRIGGER** | Warren approves product direction after BOM-tab business sign-off; **or** second ACZA upload blocked by mapping noise / wrong-sheet ingest; **or** ASUS workbook adds more non-operational tabs; **or** shipment import parity sprint (BACKLOG-044) starts and sheet policy is prerequisite. |

---

## BACKLOG-045 — Import steward UI parity audit (side drawer + workspace layout)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-24 |
| **Effort** | Medium–large (web); audit-first then phased fixes |
| **Source** | Warren session (2026-06-24): shipment apply step UX; steward side panel vs DSI; `ShipmentCandidateStewardDrawer` + `ShipmentMappingStewardPanel` vs `DsiCandidateStewardDrawer` + `DsiMappingStewardPanel`; `ShipmentImportJobResolutionSection` vs `DsiImportJobResolutionSection`; `.cursor/rules/import-parity.mdc` steward surface rule; partial parity shipped on `feat/dsi-async-topology` (tabs, toolbar, plan apply, drawer apply banner) — **gaps remain** |
| **Idea** | Several import steward surfaces are **not fully component-paritied** with DSI. Operators see slight layout/behaviour differences: side steward drawer (duplicate review, open channel, peer compare, row-action lifecycle), workspace chrome (pagination placement, bulk slot, plan toolbar), entity-type API wiring (`/mappings/` vs `/shipment-evidence/`), and apply-step completion UX (shipment now has `ImportJobLoadedSuccessCallout`; DSI/historical lineup not unified). |
| **Why it matters / deferrable** | Shipment backfill (#147) is unblocked enough to apply; full UI parity is polish + regression-risk reduction before scaling steward work across importers. Deferrable until a dedicated UX parity sprint — but **audit should be explicit** so drift does not accumulate. |
| **What the work is** | (1) **Audit matrix:** per importer row in `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` — side drawer component, workspace layout, plan toolbar, bulk section, apply-loaded callout, row actions (Review vs inline), API family. (2) **Extract shared primitives** where duplication is stable: steward drawer shell, plan-ready banner, apply-complete callout (extend `ImportJobLoadedSuccessCallout`), duplicate-review blocks (shipment may need shipment API adapters). (3) **Close shipment gaps:** wire `DsiMappingStewardPanel`-equivalent behaviours still missing on shipment (duplicate cluster dialogs, open channel if applicable, `onStewardFastComplete` cache eviction, peer lookup). (4) **DSI apply step:** adopt same loaded success callout pattern. |
| **Regression traps** | Wrong steward API paths; breaking shipment entity types (`shipment_customer_token` vs `customer_dealer_token`); removing shipment-only special-category / reject flows; forked bespoke panels instead of shared layout. |
| **Behavior to retain** | Shipment-evidence steward API family; governance (no auto-create); evidence vs fact semantics; import-parity locked async DB config. |
| **Out of scope** | Full `DsiMappingStewardPanel` → single mega-component for all importers without adapter layer; product steward on shipment. |
| **TRIGGER** | Warren requests steward UI parity audit; **or** second importer steward surface added without shared drawer/workspace; **or** shipment parity PR merged and next sprint is import UX hardening. |

---

## BACKLOG-044 — Shipment import: steward UX + resolution intelligence parity with DSI

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-06-23 |
| **Effort** | Large (web + API services); likely phased after BACKLOG-001 workspace swap |
| **Source** | Warren session audit (2023 vs 2026 ACZA backfill — evidence vs fact confusion, manual per-row steward); `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` (`steward_surface`: `shipment_evidence_admin` vs `dsi_resolution_section`); `apps/web/src/app/(app)/admin/shipment-evidence/ShipmentEntityStewardPanel.tsx` (bespoke panel); `apps/web/src/app/(app)/admin/imports/DsiImportJobResolutionSection.tsx` + `ImportStewardCandidateWorkspace` (DSI reference); `apps/api/app/services/imports/dsi_resolution_plan.py` (no shipment equivalent); `apps/web/src/features/import-steward/dsi-mapping-steward-panel.tsx` (comment: shipment remains separate); **BACKLOG-001** (workspace adapter only — does not cover plan intelligence) |
| **Idea** | Shipment evidence import still uses a **different steward surface** and **weaker resolution intelligence** than DSI / other import-parity importers. Operators lack entity tabs, resolution-plan suggestions, ready vs needs-work queues, bulk “apply all ready”, historical/previously-resolved hints at the same bar, and the shared steward workspace patterns documented in `.cursor/rules/import-parity.mdc`. |
| **Why it matters / deferrable** | Blocks efficient backfill + current-report workflows (historical landed lines, product corroboration gaps, per-row confirm loops). Deferrable while DSI steward and alias-scope work completes and until shipment bitemporal/backfill model (BACKLOG-033) is scoped — but **steward/intelligence gap is independent of schema** and should be audited before scaling shipment uploads. |
| **What the work is** | (1) **Steward surface:** complete BACKLOG-001 (`ImportStewardCandidateWorkspace` adapter for shipment) — entity-grouped tabs, confidence bands, bulk progress, shared invalidate/refetch. (2) **Resolution intelligence:** shipment-specific plan builder (or shared abstraction): suggested map/provisional/ignore, ready vs needs_review, blockers, target labels — aligned with `dsi_resolution_plan` patterns where domain fits; wire `try_ai_token_resolution` / shared candidates helpers per import-parity rule. (3) **Apply orchestration:** bulk grouped writers + async apply + tab-count coherence (shipment bulk paths exist but UX/plan layer lags DSI). (4) **Operator docs:** evidence (all snapshots per job) vs `fact_inbound_shipment` (current keyed row) — when to apply, backfill vs current. (5) **Audit session findings:** corroboration reads evidence not fact; upload alone insufficient; product `resolved_unique` still required. |
| **Regression traps** | Wrong API family (`/mappings/` vs `/shipment-evidence/`); entity type mismatch (`shipment_*` tokens); breaking Phase 2 shipment batching; conflating evidence append with fact latest-job-wins (BACKLOG-033); auto-create masters from evidence. |
| **Behavior to retain** | Evidence preserved per import job; fact upsert on global `source_key`; steward governance (no silent master creation); existing shipment-evidence endpoints until deliberately migrated. |
| **Out of scope** | Full bitemporal observation store (BACKLOG-033); ETA prediction ML; changing corroboration tier order or DSI eligibility. |
| **TRIGGER** | Warren requests shipment import parity audit; **or** second production backfill/current shipment workflow (e.g. ACZA historical + rolling current) before BACKLOG-033 ships; **or** BACKLOG-001 workspace swap signed off and next import-parity sprint starts. |

---

## BACKLOG-037 — DSI validate/refresh post-resolution orchestrator unification

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-19 |
| **Effort** | Medium (extract shared orchestrator + index loaders + tests) |
| **Source** | DSI temporal supersession / receipt-tier wiring audit; `refresh_dsi_staging_line_resolution` in `distributor_sales_inventory.py` |
| **Idea** | Extract `_resolve_dsi_product_post_tiers(...)` shared by bulk validate and `refresh_dsi_staging_line_resolution`: `_resolve_product` → receipt tier → temporal supersession → canonical collapse (as each ships). |
| **Why / deferrable** | Tier B/C wire validate-only first; wiring new tiers into refresh without receipt upstream would make refresh weaker than validate. Unification is correct but larger than individual tier commits. |
| **What the work is** | Single orchestrator called from validate row loop and `refresh_dsi_staging_line_resolution`; load `DistributorReceiptProductIndex` + product-id shipment window index once per job/refresh; parity tests that validate and refresh produce identical `resolved_product_id` for the same staging line. |
| **Regression traps** | Refresh without receipt tier (existing gap today); memo key `(token, evidence_date)` diverging across paths; missing index loaders on steward refresh. |
| **Behavior to retain** | Validate remains canonical until unified; steward manual alias override unchanged; cross-distributor auto-resolve guard. |
| **Out of scope** | Changing resolution tier semantics; schema migration. |
| **TRIGGER** | After Tier B + Tier C validate soak on job #43; or steward refresh bug where post-receipt auto-resolve is expected on re-resolve. |

---

## BACKLOG-004 — Import Flow Phase 3: capability-driven wizard componentization

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Very large |
| **Source** | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` (§7 Phase 3, §9 D2/D4); `CONTEXT.md` (May 31 “Next: Phase 3 … GATED behind PM core-loop re-run”) |
| **Idea** | Replace `isPm` / `isDsi` / `isShipmentEvidence` branches in `admin/imports/page.tsx` with `ImportFlowCapability` from static client map (`packages/types/`), mounting `mapping_ui` and gating steps per importer. |
| **Why / deferrable** | Contract Phase 1 is design-only done; implementation gated until PM core loop is re-proven end-to-end. |
| **What the work is** | Static capability map; flag-gated rollout per importer; optional later promotion to `GET /templates` `capability` field (D2 upgrade path). |
| **Regression traps** | Breaking shipment 4-step inline steward; PM 6-step commit; DSI validate/apply modes. |
| **Behavior to retain** | Per-importer legitimate differences in `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` §5 matrix. |
| **Out of scope** | Phase 4 write optimizations (separate entry). |
| **TRIGGER** | PM core-loop re-run passes on target branch **and** explicit approval to start Phase 3 implementation. |

---

## BACKLOG-006 — Slim shipment `mapping-candidates` API response (paginate / omit `line_ids`)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-01 |
| **Effort** | Medium (API + web) |
| **Source** | `CONTEXT.md` (Jun 1 steward perf: “Unchanged: … mapping-candidates payload shape”); `apps/api/app/api/v1/endpoints/shipment_evidence.py` (`list_shipment_import_job_mapping_candidates` returns full `context` per row); contrast `apps/api/app/schemas/dsi_mapping_candidates.py` (paginated DSI list) |
| **Idea** | Reduce steward panel load time (~3–5s GET for large jobs) by paginating candidates and/or omitting `context.line_ids` from list payload while keeping `row_count` (and fetch line scope only on steward apply server-side). |
| **Why / deferrable** | Explicitly left unchanged during steward perf work to limit risk; batching addressed apply path first. |
| **What the work is** | New query params or list DTO; optional `GET .../candidates/{id}/context`; update `ShipmentEntityStewardPanel` / future workspace adapter queries. |
| **Regression traps** | Steward ops still require `line_ids` server-side (`shipment_evidence_steward_ops._line_ids_from_context`); client must not break bulk selection scope. |
| **Behavior to retain** | Steward apply semantics and job-bound line verification. |
| **Out of scope** | Changing enrichment/scoring. |
| **TRIGGER** | Post-merge steward perf smoke shows `mapping-candidates` GET still dominant in browser waterfall for jobs with 100+ candidates. |

---

## BACKLOG-008 — DSI region evidence: read-only hints from shipment evidence

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (plan doc) |
| **Effort** | Medium |
| **Source** | `docs/DSI_REGION_EVIDENCE_AND_FALLBACK_PLAN.md` (architecture diagram line 47: “(Later) shipment / other modules — read-only hints”) |
| **Idea** | Add shipment-derived region hints into DSI customer region evidence rank (read-only; steward confirm still required for `region_id` from channel). |
| **Why / deferrable** | Phase A–B DSI-only region engine first; shipment module is separate consumer. |
| **What the work is** | Extend `dsi_customer_region_evidence` (or batch builder) with shipment evidence source; unit tests; no auto-write `region_id` from channel/shipment without steward. |
| **Regression traps** | Channel token geographic hint rules; do not conflate with product shipment tie-break (`dsi_product_shipment_tiebreak.py`). |
| **Behavior to retain** | DSI resolution order; corroboration tier order. |
| **Out of scope** | Shipment import changes. |
| **TRIGGER** | Region evidence Phases A–B shipped and steward UX stable; user requests cross-module hints. |

---

## BACKLOG-009 — PIM: typed-attribute promotion from `specs_json` (longer-term)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Very large |
| **Source** | `docs/PRODUCT_MASTER_PIM_DESIGN_BRIEF.md` (§5 proposed architecture “for debate”; §7 safety: additive, feature-flagged; “not built”); `CONTEXT.md` (May 31 “full PIM/category-template model” in Not done) |
| **Idea** | Category templates + typed storage (typed EAV or hybrid JSONB) promoted from today’s canonical `dim_product.specs_json` read store. |
| **Why / deferrable** | Design brief only; `specs_json` is already canonical for reads; PIM is lower risk as additive path. |
| **What the work is** | Schema/templates, steward-approved attribute definition creation, feature flag, real-DB scale validation per SQL rule. |
| **Regression traps** | Hot `product_import_sync` path; 2M-row scale. |
| **Behavior to retain** | `specs_json` as current read store until flag flip; no silent schema creation. |
| **Out of scope** | Dropping legacy PAV (separate entry). |
| **TRIGGER** | Explicit product decision to fund PIM phase + migration plan approved. |

---

## BACKLOG-010 — Drop legacy `product_attribute_value` rows (~2M, destructive)

| Field | Detail |
|-------|--------|
| **Status** | **N/A for this branch · 2026-06-06** — destructive ops require explicit Warren approval + local `pg_dump` backup (or PITR if remote ever returns); no code change. Remains a future ops task when PM `specs_json` path is production-proven. |
| **Effort** | Medium (ops) + approval |
| **Source** | `CONTEXT.md` (May 31 PM EAV: “left in place (dropping … needs explicit approval)”; import audit “still pending: drop existing 2M PAV rows”) |
| **Idea** | Remove dead write-only PAV data after `specs_json` commit path is proven in production. |
| **Why / deferrable** | Destructive; reversible only via DB backup/PITR. |
| **What the work is** | Approved migration or one-off script; verify zero readers; backup before run. |
| **Regression traps** | Any hidden reader; `PM_WRITE_LEGACY_EAV` escape hatch users. |
| **Behavior to retain** | `specs_json` commit path. |
| **Out of scope** | Re-enabling EAV writes by default. |
| **TRIGGER** | Explicit Warren approval + database restore point taken. |

---

## BACKLOG-011 — `catalog_product` commit path: per-row `flush()` → bulk `INSERT…ON CONFLICT`

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Medium |
| **Source** | `CONTEXT.md` (May 31 “Not done: catalog_product per-row flush → bulk”) |
| **Idea** | Batch catalog upsert on PM commit like product bulk upsert. |
| **Why / deferrable** | PM commit already fast after EAV write removal; diminishing returns until large catalogs return. |
| **TRIGGER** | PM commit profiling shows catalog flush as dominant cost again. |

---

## BACKLOG-013 — `customer_sell_through` own import surface (D1)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-31 |
| **Effort** | Large |
| **Source** | `docs/IMPORT_FLOW_CAPABILITY_CONTRACT.md` (§9 D1, §5 row, §10; `hidden_from_generic_ui`, deferred `mapping_ui` / `steward_surface`); `apps/api/app/services/imports/customer_sell_through.py` (line 96: parser not implemented for some structure types) |
| **Idea** | Dedicated UI + parsers for customer sell-through (not generic wizard). |
| **TRIGGER** | Sell-through importer prioritized in roadmap. |

---

## BACKLOG-014 — Customer classification mapping import (template deferred)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (template seed) |
| **Effort** | Medium |
| **Source** | `apps/api/app/services/imports/template_definitions.py` (line 298: “intentionally deferred; not wired for apply yet”) |
| **TRIGGER** | Business requests customer classification import apply path. |

---

## BACKLOG-016 — DSI steward finalize: scoped later items

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (plan) |
| **Effort** | Large (multiple features) |
| **Source** | `docs/DSI_STEWARD_FINALIZE_PLAN.md` (§ Deferred); `docs/SESSION_HANDOVER_2026_05_23.md` (§6 Scoped for later) |
| **Idea** | Duplicate Phase 2 clusters; distributor hub/branch SOH; web/registry enrichment for duplicate decisions; open peer cross-page lookup; `shipment_evidence_line.distributor_id` index (`CREATE INDEX CONCURRENTLY`); DSI upload Celery infer backgrounding. |
| **TRIGGER** | Explicit approval per row in SESSION_HANDOVER §6 (do not bundle). |

---

## BACKLOG-017 — DSI embedding-based duplicate detection

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (doc) |
| **Effort** | Large |
| **Source** | `docs/DSI_RESOLUTION_PERFORMANCE.md` (lines 3–7: “not implemented … stopped before implementation”) |
| **Idea** | True embedding similarity vs current `difflib` pairwise job-local scoring. |
| **TRIGGER** | Steward false-positive/negative rate still unacceptable after cascade tuning. |

---

## BACKLOG-018 — DSI geo token indexes (recommended, not applied)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (doc) |
| **Effort** | Small (migration, needs approval) |
| **Source** | `docs/DSI_RESOLUTION_PERFORMANCE.md` (§ `dsi-unresolved-geo-tokens`: “Recommended indexes … not applied”) |
| **TRIGGER** | `EXPLAIN` on geo collection still slow after cache fix. |

---

## BACKLOG-019 — Historical lineup: deferred import Phase items

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-04-26 checkpoint |
| **Effort** | Large (bundle) |
| **Source** | `docs/memory/derived/platform_import_system_truth.md` (§ “Deferred items (as of f47bcea)”) |
| **Idea** | EntityMappingQueue customer token resolution; loaded lineup inspect UI; post-apply navigation; jobs list pagination; duplicate-apply guard; multi-sheet mapping; `match_strategy` JSONB framework; etc. |
| **TRIGGER** | Historical lineup module prioritized; pick **one** slice per `platform_import_system_truth.md` “Phase 2B” guidance. |

---

## BACKLOG-020 — Product Master: full job revisit in wizard

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · (UI) |
| **Effort** | Medium |
| **Source** | `apps/web/src/app/(app)/admin/imports/page.tsx` (line 2024: “Full PM revisit is not yet supported”); `page.test.tsx` (“deferred template visibility”) |
| **TRIGGER** | PM ops need edit mapping / re-validate on committed or validated PM jobs from `?job=`. |

---

## BACKLOG-021 — Commercial Planner: RBAC, durable recommendation store, router extraction

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-05-30 |
| **Effort** | Large |
| **Source** | `docs/COMMERCIAL_PLANNER_GAP_ANALYSIS.md` (executive summary lines 11–12, security row) |
| **TRIGGER** | Commercial Planner production hardening phase approved. |

---

## BACKLOG-025 — Generic-pipeline apply → async (masters / historical / sell-through)

| Field | Detail |
|-------|--------|
| **Status** | **Done (part A) · 2026-06-05** — `/process` endpoint async, returns `{async, task_id, job_id}`. CST is the initial beneficiary. Masters/historical still use the same endpoint and get the async path for free. |
| **Effort** | Medium |
| **Source** | This branch's audit; `apps/api/app/api/v1/endpoints/imports.py::process_job` runs `process_import_job_sync` inline |
| **Idea** | Move the generic `POST /jobs/{id}/process` (apply path for `distributor_master`, `customer_master`, `historical_lineup`, `customer_sell_through`) onto the async-dispatch pattern (broker→dev-thread→sync-fallback) with progress, like DSI/shipment apply. |
| **Shipped** | `POST /jobs/{job_id}/process` now calls `_enqueue_import_pipeline_job` (reuses `imports.process_job` Celery task) and returns `{"async": bool, "task_id": str\|None, "job_id": int}`. No frontend caller existed so no breaking change. Progress polling via existing `imports.process_job` task slot is available but not yet wired to a frontend panel. |
| **Remaining** | Frontend progress panel for CST apply (Unit C); slot registration for CST apply; masters/historical may need their own panels if they become async-heavy. |

---

## BACKLOG-026 — Product Master: consolidate the two apply pipelines

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-04 (out-of-scope this pass) |
| **Effort** | Medium–large |
| **Source** | This branch's audit; dedicated `product_master_workflow.py` (`pm_validate`/`pm_commit`, bespoke mapping, AI desc-remap) vs generic `pipeline.py::_process_product_master` (inline, channel-only AI) |
| **Idea** | One product_master apply path. Today two code paths exist for one slug with divergent AI + mapping behavior and double maintenance. |
| **Why / deferrable** | Drift risk + duplicate maintenance; deferrable because both currently work and PM is not on this pass's critical path. |
| **What the work is** | Pick the workflow path as canonical; route the generic handler to it (or delete the generic branch); reconcile AI (description remap vs channel-only) and mapping (bespoke `pmMappingHelpers` vs panel). |
| **Regression traps** | `specs_json` canonical; two-phase validate→commit semantics; existing PM tests. |
| **TRIGGER** | A PM consolidation task is approved (pairs naturally with BACKLOG-027). |

---

## BACKLOG-027 — PM + historical mapping UI → shared `CanonicalColumnMappingPanel`

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-04 (out-of-scope this pass) |
| **Effort** | Medium (web) |
| **Source** | This branch's audit; PM bespoke `pmMappingHelpers`/`pmMappingTargetOptions`; historical override mapping; vs shared panel used by DSI/shipment |
| **Idea** | Replace the PM and historical-lineup bespoke mapping tables with the shared `CanonicalColumnMappingPanel` (parity rule §4). |
| **Why / deferrable** | Removes a third/fourth mapping-UI shape; deferrable, cosmetic-ish, no correctness gap. |
| **What the work is** | Mount the panel with PM/historical target options + samples; keep server validation; delete bespoke helpers once parity verified in-browser. |
| **Regression traps** | PM `pm_mapping_saved` stage flow; historical override semantics. |
| **TRIGGER** | A mapping-UI unification task is approved (pairs with BACKLOG-026). |

---

## BACKLOG-029 — Unit 3 sell-through surface + `ImportFileUploadZone` extraction decision

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-05 (updated; part (a) already done) |
| **Effort** | Medium (sell-through surface) + Small (upload-zone decision) |
| **Source** | This branch: DSI apply async backend committed `c079cc6`; **`dsiApplyAsync` frontend poll committed `153c93c`** (7 occurrences in `page.tsx` — `setDsiApplyAsync`, `dsiApplyPollJob`, `dsiApplyAsync || dsiApplyPollJob`, poll `useEffect`, `onSuccess` handler; terminal on `loaded`/`failed`, not `validated`). `ImportFileUploadZone` component committed in `153c93c` but **never rendered as JSX** — the import at line 64 of `page.tsx` is unused; the 3 inline upload zones still exist. customer_sell_through backend committed `09d21ef` (no web surface yet). |
| **Part (a) — DONE** | `dsiApplyAsync` poll wiring committed in `153c93c`. Not a pending task. |
| **Part (b) — CST surface** | Build the minimal drivable `customer_sell_through` surface by composing the shared `CanonicalColumnMappingPanel` + `ImportStewardCandidateWorkspace` + async apply (do not build bespoke UI). Requires running browser for verification. |
| **Part (c) — DONE** | `ImportFileUploadZone` extraction committed in `d0a8923` — component rendered at 3 sites in `imports/page.tsx`. Browser upload/drag smoke still recommended when touching that page. |
| **Regression traps** | Apply poll: transits through `validated` before `loaded` — terminal condition must stay `loaded`/`failed` only (already correct). Upload zones: preserve drag-and-drop, `canUpload` gating, `pending` progress bar; do not break the DSI / shipment / generic upload flows. |
| **Governance** | Provisional creation stays steward-initiated; no auto-create. |
| **TRIGGER** | (b) sell-through: surface prioritized in roadmap + running browser available. (c) upload-zone: a browser-verified frontend task is approved for this branch, or the unused import is flagged by linter in CI. |

---

## BACKLOG-031 — Admin data health dashboard (table counts + import evidence viewer)

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-06 |
| **Effort** | Medium (API read models + web admin page) |
| **Source** | Jun 6 session: Supabase has ~222k DSI staging lines but Channel Operations sell-out shows 0 until apply; operator needs visibility without raw pgAdmin/SQL. |
| **Idea** | Read-only admin page: per-table row counts + approximate sizes (facts vs staging vs masters), import job summary (validate vs apply, staging vs fact counts per job), link to existing import bulk-delete. Not a full pgAdmin — curated CIP views only. |
| **Why / deferrable** | Validates system health and explains validate≠apply confusion; deferrable until post–Unit 1–5 delivery and steward/apply next steps are chosen. |
| **What the work is** | API: `GET /admin/data-health` (async, `data_unavailable` graceful); web: `/admin/data-health` with ModuleDataSection cards + job drill-down. Optional: Supabase dashboard link for deep DBA work. |
| **Regression traps** | Read-only; no destructive actions on this page; do not expose connection strings or raw SQL console by default. |
| **Behavior to retain** | Import job cancel/bulk-delete stays on imports page; governance unchanged. |
| **Out of scope** | Embedded pgAdmin; schema migrations; auto-apply. |
| **TRIGGER** | Operator asks for DB health visibility again, or before next large Supabase soak (apply on job #43). |

---

## BACKLOG-032 — Post import bulk-delete: targeted VACUUM / disk reclamation runbook

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-06 |
| **Effort** | Small (ops script + docs) · Medium if automated after delete |
| **Source** | Postgres dev: bulk delete of import jobs (except active job #43); repeated `VACUUM` in SQL editor; `VACUUM FULL` times out; dashboard disk size unchanged. |
| **Idea** | (local-cip relevant)  Document and optionally script **targeted** post-delete maintenance: `VACUUM (ANALYZE)` on evidence/staging tables affected by import job bulk delete; `VACUUM FULL` only as a manual, maintenance-window ops step when dead-tuple bloat is confirmed — not from the app or SQL editor transaction wrapper. |
| **Why / deferrable** | Regular `VACUUM` does not return disk to the OS; `VACUUM FULL` requires exclusive locks + long runtime (timeouts on Postgres dashboard / pooler). Autovacuum handles most dead tuples; ops step needed only after large evidence deletes when dashboard disk stays high. |
| **What the work is** | (1) Ops doc: connect via **session** `:5432` psql, `SET statement_timeout = 0`, stop API/worker, one table at a time. (2) Read-only bloat query (`pg_stat_user_tables`, `pg_total_relation_size`) before choosing FULL vs ANALYZE. (3) Optional `apps/api/scripts/vacuum_import_evidence_tables.py` (explicit table list, dry-run, confirms `current_database()`). (4) Do **not** hook into app delete path automatically — governance + lock risk. |
| **Regression traps** | `VACUUM FULL` on `import_distributor_si_staging_line` while job #43 is active blocks steward/validate; never run inside a transaction; avoid `:6543` pooler for long maintenance; credentials never in repo. |
| **Behavior to retain** | Import bulk delete remains the supported cleanup path; vacuum is follow-up ops only. |
| **Out of scope** | Embedded pgAdmin; app-triggered `VACUUM FULL` on every delete; `VACUUM FULL` on all public tables. |
| **TRIGGER** | After large import evidence bulk delete AND (`n_dead_tup` still high 24h later OR Postgres disk quota pressure) AND Warren approves maintenance window. |

---

## BACKLOG-057-D4 — Plan D D4: stop duplicating observation payload on legacy evidence lines

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-07-02 |
| **Source** | `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` D4; Plan D cutover complete |
| **Idea** | Dual-write still populates `shipment_evidence_line` for steward job scope; stop persisting columns that mirror observation payload once all write paths read observations for history. |
| **TRIGGER** | 30-day soak after Plan D cutover with zero steward regressions; Warren approves D4 start. |

---

## BACKLOG-058-D5 — Plan D D5: drop redundant shipment_evidence_line columns

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-07-02 |
| **Source** | `docs/SHIPMENT_BITEMPORAL_PLAN_D.md` D5 |
| **TRIGGER** | BACKLOG-057 complete + Alembic migration reviewed; no consumer reads raw legacy columns. |

---

## BACKLOG-062 — Open→shipped fact double-count remediation

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-07-02 · **re-measured 2026-07-27** (shipping KPI Phase 0) |
| **Source** | Plan D phase 1 diagnostic (`open_order_shipped_fact_double_count_diagnostic`); Phase 0 `apps/api/.tmp/shipping_kpi_phase0_diag.json` |
| **Idea** | When order grain graduates to shipped, retire or supersede open-order fact rows — separate from evidence cutover. |
| **Evidence (cip)** | Plan D: **104** pairs. Phase 0 (looser order_no+product join): **312** pairs, open qty **24,839**, shipped qty **26,750**, open amount **~$18.2M**. Also **109** `status=scheduled` + `line_state=shipped` rows ($5.7M) sit in the scheduled book. |
| **TRIGGER** | Warren approves fact-layer remediation policy after reviewing diagnostic; **or** after shipping KPI rewrite lands and operators still see open+shipped twins in current-incoming. |

---

## BACKLOG-076 — Inbound fact amount / unit-price scale corruption (unship junk)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Mitigated 2026-08-08** — KPI-level exclusion shipped; root-cause mapping audit / corrective re-import still open (kept parked below the line). |
| **Effort** | Medium (import mapping audit + optional purge of junk job facts) |
| **Source** | Shipping KPI Phase 0 (`docs/SHIPPING_COMMERCIAL_KPI_CONTRACT.md` §Phase 0; `.tmp/shipping_kpi_phase0_diag.json`). Old “Pipeline value” = **$288M**; **$214M** of that is on **267** scheduled lines with **null ETA and null promise**. Top rows show qty **36** with amount **~$36M** each (`~1e6` unit price) from `acza_workbook_unship` source keys. |
| **Idea** | Diagnose whether OEM amount/unit_price columns were mapped with wrong scale or currency; quarantine or re-import affected jobs. Do **not** silently rewrite amounts from the `/shipping` UI. |
| **Mitigation shipped 2026-08-08** | `apps/api/app/services/shipping/amount_scale.py` — `is_unit_price_scale_suspect(amount, quantity)` / SQL clauses flag rows where `abs(amount)/quantity > 100_000`. Wired into `/shipping` pipeline-in-transit KPI (`apps/api/app/api/v1/endpoints/shipping.py`): current-incoming amount aggregation now excludes suspect rows (FLAG ≠ BLOCK — rows untouched, only excluded from this KPI's valuation) and reports `pipeline_in_transit.amount_scale_suspect_excluded`. **Verified against `cip`:** 17 suspect rows (all `acza_workbook_unship` source keys, qty 36–38 at ~$1M implied unit price, matching the Phase 0 sample exactly) out of 14,366 scheduled shipment facts; all-scheduled amount $464.2M → $68.2M excluding suspect rows (separate axis from the existing ETA-window current-incoming gate). |
| **Why deferrable (remaining root-cause work)** | KPI exclusion removes the commercial distortion from the card. Root-cause mapping audit / corrective re-import / possible purge is still deferrable — no user-facing harm while the 17 rows are excluded from valuation. |
| **What the work is (remaining)** | (1) Reproduce top-20 amount rows vs raw workbook. (2) Confirm mapping/unit semantics. (3) Job-scoped purge or corrective re-import (pairs with BACKLOG-073). |
| **Regression traps** | Do not change DAP vs PM cost concepts; do not mass-UPDATE fact amounts without audit trail; preserve `source_key` upsert semantics. |
| **Out of scope** | Changing commercial KPI predicates again; MasterDataGridShell rewrite. |
| **TRIGGER** | Warren prioritizes cleaning ACZA unship amount inflation at the source (mapping fix / re-import) — the KPI-level symptom is now mitigated. |

---

## BACKLOG-063 — Shipment change events v2: cancelled-candidate via report-coverage

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-07-02 |
| **Source** | Plan D phase 4 scope note; `shipment_change_events.py` v1 |
| **TRIGGER** | Steward/report-coverage semantics for cancelled lines defined; ETA or channel-ops UI needs cancelled signal. |

---

## BACKLOG-064 — Shipment change-event UI surfacing

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-07-02 |
| **Source** | Plan D phase 4 (API/CLI only) |
| **TRIGGER** | Shipping admin or commercial planner needs in-app event timeline; API contract stable after soak. |

---

## BACKLOG-065 — Monthly-phased 1H allocation tier (phased → uniform_half fallback)

| Field | Detail |
|-------|--------|
| **Status / parked** | **Parked** · 2026-07-03 |
| **Effort** | Medium–large (parser parity + allocation tier stack + sanity gate + steward flags; re-derivation hook already exists for `uniform_half`) |
| **Source** | Steward session 2026-07-03: 1H split + `uniform_half` shipped (`1893309`, `lineup_half_year_quantity.py`); read-only diagnosis on `cip` — 2026 NB 1H files lack Apr/May/Jun-style phasing in stored payloads; 2025-era corpus retains phasing in source workbooks. `historical_lineup.py` already captures `_month_split` → `month_split_json` on **historical** import lines; **`lineup_case_parser.py` (CommercialLineupCase / bulk backfill path) does not** — stores `raw_row_payload.uploaded` (all header cells) but never populates `CommercialLineupLine.month_split_json` or a `_month_split` sentinel. |
| **Idea** | **Allocation tier stack** for 1H half-year splits: **`monthly_phased`** when source carries month phasing columns (Apr/May/Jun-style) that pass a **sum-to-total sanity gate** (monthly values sum to line `quantity_units`, no TBC/blank poisoning) → else **`uniform_half`** fallback (today’s rule). Per-line flag records the tier used (e.g. `allocation=monthly_phased` vs `allocation=uniform_half`). Q1/Q2 case split from phasing: allocate months to calendar quarters from column headers, not blind 50/50. |
| **Why it matters / deferrable** | **Value concentrates in 2025-era corpus** — 2026 lineup format dropped monthly phasing columns, so `uniform_half` is the correct default for current imports. Phased allocation unlocks **intra-quarter phasing intelligence** (plan shape, steward review, later plan-vs-shipped at month grain) — separate follow-on, not required for 1H Q1/Q2 case split today. Safe to defer while steward re-derivation runs on `uniform_half` flags. |
| **What the work is** | (1) **Prerequisite audit** — verify whether `lineup_case_parser` / bulk backfill preserves enough raw row evidence for phasing (gap vs preserve-raw principle); port or share month-column detection from `historical_lineup.py` into the CommercialLineupCase parse path; persist `month_split_json` on `commercial_lineup_line`. (2) **Sanity gate** — month columns sum to `quantity_units` within tolerance; reject TBC/empty/non-numeric for phased tier. (3) **Tier resolver** in `lineup_half_year_quantity` (or sibling): `monthly_phased` → Q1/Q2 from month→quarter map; fallback `uniform_half`. (4) **Preview/apply** — show tier per file/line in bulk panel + re-derivation; steward override surface for tier (extends existing allocation flag pattern). (5) **Tests** — 2025 fixture with Apr–Jun columns (phased), 2026 fixture (uniform_half only), sum-invariance for both tiers. |
| **Regression traps** | Do not replace `uniform_half` as default when phasing absent; sum invariance must hold per tier; do not auto-pick supersession; `allocation=uniform_half` flags remain the **re-derivation hook** for already-imported 1H cases until steward re-runs with phased tier; historical vs weekly / DSI paths unchanged. |
| **Behavior to retain** | Settled 1H rules: always split Q1+Q2; soft supersession; collisions to steward; flag ≠ block; `period_scope=1h_split` from any 1H signal tier (`1893309`). |
| **Out of scope** | Intra-quarter phasing **reporting** UI and month-grain plan-vs-shipped chips (separate later item); inventing phasing from thin air when columns missing; changing 1H split trigger logic. |
| **TRIGGER** | **Re-deriving any 2025 1H file** during bulk backfill stewarding (phasing columns present in source), **or** when **month-grain plan-vs-shipped** becomes a reporting target. |

---

## BACKLOG-034 — Product Master launch/retire date integrity

| Field | Detail |
|-------|--------|
| **Status / parked** | Parked · 2026-06-14 |
| **Effort** | Large (audit + governed steward corrections + re-validation plan) |
| **Source** | Session audit: job #40 unique-SKU `inactive_only` anchor analysis (1,965 lines); `apps/api/app/services/imports/distributor_sales_inventory.py` (`_product_eligible_for_dsi_auto`, launch/retire window); `apps/api/app/models/dimensions.py` (`DimProduct.launch_date`, `retired_date`, `lifecycle_status`); shipment SKU-anchor override commit `6c865ea` (identity routed around bad dates) |
| **Idea** | Audit and correct `dim_product.launch_date` / `retired_date`. Multiple confirmed corruption classes. |
| **Why it matters / deferrable** | These dates gate product eligibility in DSI resolution (relaxed/strict) and would gate shipment-evidence, sell-through, and current-assortment views. Bad dates silently mis-classify products. **Confirmed on job-40 unique-SKU inactive_only anchors (1,965 lines):** 319 rows have `retired_date < launch_date` (inverted/impossible); 758 lines ship before `launch_date` (implausible at scale → likely late/wrong launch dates); 268 ship after `retired_date`. Plus: `B1403CVA-S61905W` retired 2025-12-22 before launch 2026-01-19; rows with `is_active=true` AND `lifecycle_status` in (Discarded/Disabled). This is the root cause routed around with the SKU-anchor identity rule. The override is correct for **identity**, but dates stay wrong for every other consumer. Deferrable until commercial outputs depend on lifecycle windows — but **before** SKU-anchor override is reconsidered or assortment/sell-through windows go live. |
| **What the work is** | (1) Start with the **319 inverted-window** rows — unambiguously wrong, no domain judgment. (2) Resolve `is_active` vs `lifecycle_status` inconsistency: pick the canonical eligibility driver. (3) **before_launch** cases need Warren's domain call: real pre-launch channel-fill vs late launch dates. (4) Correct via governed update; never guess values — derive from OEM/trusted source or steward review. (5) Re-validate affected DSI/shipment jobs after corrections. |
| **Regression traps** | Fixing dates changes DSI eligibility outcomes → re-validate affected jobs after. Do **not** widen windows blindly; that defeats eligibility purpose. |
| **Behavior to retain** | SKU-exact shipment identity anchor (identity ≠ sellability); DSI historical vs weekly mode semantics; steward governance on master edits. |
| **Out of scope** | Auto-correcting dates from import evidence without steward approval; reversing SKU-anchor identity rule. |
| **TRIGGER** | Before relying on lifecycle/eligibility for any commercial output (assortment, sell-through windows), and before the SKU-anchor override is reconsidered. **Pairs with** BACKLOG-033 (bitemporal shipment cleanup). |

---

## Unsourced — confirm with Warren

These were on a verification checklist but **no deferral/pending wording** was found in repo docs, comments, or planning files:

| Topic | Notes |
|-------|--------|
| **`customer_po` shipment column** | Not present in `SHIPMENT_CANONICAL_TARGETS` (`shipment_field_mapping.py`) or docs grep. |
| **Shipment async steward endpoints** | DSI documents `dsi-steward-bulk-provisional-customers/apply-async` (`docs/DSI_RESOLUTION_PERFORMANCE.md`); shipment-evidence routes have no parallel async steward apply-async pattern in `shipment_evidence.py`. No explicit “defer shipment async” text — parity gap only. |

If either is intended backlog, add a sourced entry after confirming where the decision is recorded.
