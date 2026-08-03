# FULL STATE AUDIT — 2026-08-02

**Mode:** AUDIT (read-only). No fixes. No migrations.  
**Database:** `cip` — `SELECT current_database()` returned `cip` before first query.  
**Branch:** `main` @ `95a9a87` (in sync with `origin/main` at audit start).  
**Supabase clone:** not queried (frozen pre-2026-06-22; empty lineup tables there already ruled out migration loss).

**Known root cause carried forward:** lineup corpus was **applied then removed** (Section 1). Later sections treat that as given — they do not re-diagnose it.

---

## SECTION 1 — Lineup corpus forensics

### 1.1 Job history

Slugs matching `%lineup%` / `unified%` / `bulk_lineup%`: only `unified_lineup` (9) and `bulk_lineup_backfill` (39).  
`import_job` has no dedicated row-count columns; row outcomes live in `staged_metadata` and case/line tables.

| id | slug | status | import_mode | stage | file_name | created_at | updated_at | error_summary |
|---|---|---|---|---|---|---|---|---|
| 214 | unified_lineup | completed | apply | loaded | 2. ACZA Q2 2026 Consumer Lineup - Sales.xlsx | 2026-06-28 18:38:41 | 2026-06-28 18:38:45 | null |
| 215 | unified_lineup | completed | apply | loaded | Q2 Gaming NR Lineup - Sales Team.xlsx | 2026-06-28 18:38:41 | 2026-06-28 18:38:52 | null |
| 216 | unified_lineup | completed | apply | loaded | 2. ACZA Q1 2026 NV Ally Lineup - Sales Team Copy.xlsx | 2026-06-28 18:38:41 | 2026-06-28 18:38:55 | null |
| 217 | unified_lineup | failed | apply | uploaded | Copy of ACZA 1H 2025 Consumer Lineup - Gaming Desktop PD 13 Feb 2025.xlsx | 2026-06-28 18:38:42 | 2026-06-28 18:38:59 | NumericValueOutOfRange on `commercial_lineup_line` (precision 8,scale 4) |
| 220 | unified_lineup | completed | apply | loaded | 2. ACZA Q1 2026 NV Ally Lineup - Sales Team Copy.xlsx | 2026-06-28 21:20:26 | 2026-06-28 21:20:31 | null |
| 221 | unified_lineup | completed | apply | loaded | Q2 Gaming NR Lineup - Sales Team.xlsx | 2026-06-28 21:20:27 | 2026-06-28 21:20:34 | null |
| 222 | unified_lineup | completed | apply | loaded | 1. ACZA Q2 2026 Consumer Lineup - Sales.xlsx | 2026-06-28 21:20:27 | 2026-06-28 21:20:40 | null |
| 248–254 | bulk_lineup_backfill | validated | preview | validated | bulk_lineup_preview_* | 2026-07-01…07-02 | same | null (preview payloads only; staged_metadata multi-MB) |
| 255 | bulk_lineup_backfill | running | apply | pipeline_queued | bulk_lineup_preview_959ca2c4-… | 2026-07-02 10:10:58 | 2026-07-02 10:14:40 | null; `applied=32`, case_ids claimed 10–41 |
| 256 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/XB/2025/Q4/1. Q4 Accessories - Sales Lineup.xlsx | 2026-07-02 10:14:25 | 2026-07-02 10:14:31 | null |
| 257 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/XB/2025/Q3/1. Q3 Accessories - Sales Lineup.xlsx | 2026-07-02 10:14:26 | 2026-07-02 10:14:40 | null |
| 258 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/XB/2025/Q2/1. ACZA Q2 2025 Sales ACCY Lineup.xlsx | 2026-07-02 10:14:26 | 2026-07-02 10:14:40 | null |
| 259 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/XB/2025/Q2/2. ACZA Q2 2025 Sales ACCY Lineup.xlsx | 2026-07-02 10:14:27 | 2026-07-02 10:14:40 | null |
| 260 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/PF/Q4/1. Q4 Gaming Desktop - Sales Lineup.xlsx | 2026-07-02 10:14:27 | 2026-07-02 10:14:49 | null |
| 261 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/PF/Q3/1. Q3 Gaming Desktop - Sales Lineup.xlsx | 2026-07-02 10:14:27 | 2026-07-02 10:14:56 | null |
| 262 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/PF/Q2/Copy of ACZA 1H 2025 Consumer Lineup - Gaming Desktop PD 13 Feb 2025.xlsx | 2026-07-02 10:14:27 | 2026-07-02 10:14:56 | null |
| 263 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NV/Q4/2. ACZA Q4 2025 NV lineup.xlsx | 2026-07-02 10:14:27 | 2026-07-02 10:15:04 | null |
| 264 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NV/Q3/1. Q3 ROG Ally RC73 Lineup - Sales Lineup.xlsx | 2026-07-02 10:14:27 | 2026-07-02 10:15:11 | null |
| 265 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NV/2026/2. ACZA Q1 2026 NV Ally Lineup - Sales Team Copy.xlsx | 2026-07-02 10:14:31 | 2026-07-02 10:15:11 | null |
| 266 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NV/2026/Q2 Ally NV Lineup - Sales Team.xlsx | 2026-07-02 10:14:31 | 2026-07-02 10:15:18 | null |
| 267–270 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NR/2026/26Q3/1. ACZA Q3 2026 Consumer Gaming NR Lineup - Sales Team.xlsx (×4 sheet/BU variants) | 2026-07-02 10:14:31+ | 2026-07-02 10:22:01 | null |
| 271–272 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NR/2026/26Q2/Q2 Gaming NR Lineup - Sales Team.xlsx (×2) | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 273 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NR/2026/26Q1/Q1 2026 NR Gaming Lineup Updated.xlsx | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 274 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NR/2025/Q4/1. Q4 Gaming Notebook - Sales Lineup.xlsx | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 275 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NR/2025/Q3/1. ACZA Q3 NR Gaming Lineup - Sales Team.xlsx | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 276 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NR/2025/Q2/2. ACZA Q2 2025 Gaming Lineup latest version please use.xlsx | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 277 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NB/2026/26Q3/1. ACZA Q3 2026 Consumer NB Lineup - Sales.xlsx | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 278–279 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NB/2026/26Q2/… Consumer Lineup - Sales.xlsx (×2) | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 280–281 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NB/2026/26Q1/… 1H 2026 Consumer Lineup - Sales.xlsx (×2) | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 282 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NB/2025/Q3/1. ACZA Q3 2025 Consumer Lineup - Sales.xlsx | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 283 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NB/2025/Q2/1. ACZA Q2 2025 Consumer Lineup - Sales.xlsx | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 284–286 | bulk_lineup_backfill | completed | apply | loaded | Product Lineup/NB/2025/Q1/1. ACZA Q1 2025 Consumer Lineup - Sales.xlsx (×3 sheet/BU) | 2026-07-02 | 2026-07-02 10:22:01 | null |
| 298 | unified_lineup | completed | apply | loaded | 2. ACZA Q1 2026 NR Gaming Lineup.xlsx - Sales Team Copy.xlsx | 2026-07-03 10:44:38 | 2026-07-03 10:51:49 | null |
| 299 | unified_lineup | completed | apply | loaded | 2. ACZA Q1 2026 NR Gaming Lineup.xlsx - Sales Team Copy.xlsx | 2026-07-03 15:46:17 | 2026-07-03 15:46:35 | null |

Status rollup: bulk completed apply=31; bulk running=1; bulk preview validated=7; unified completed=8; unified failed=1.

### 1.2 Where applied output went

| Path | Code | Writes |
|---|---|---|
| `unified_lineup` | `apps/api/app/services/commercial_planner/unified_lineup_import.py` | `commercial_lineup_case` (`source_context=unified_lineup_import`) + `commercial_lineup_line` |
| `bulk_lineup_backfill` | `lineup_bulk_backfill_apply.py` → parse enqueue | same case/line tables; PO links via `commercial_lineup_case_po` |

Live counts:

| table | count |
|---|---|
| commercial_lineup_case | 3 (ids 7, 9, 90) |
| commercial_lineup_line | 285 |
| commercial_lineup_case_po | 52 |
| commercial_lineup_po_auto_link_dismiss | 1 |
| fact_lineup_plan_item | 0 |
| historical_lineup_import_header | 0 |
| historical_lineup_import_line | 0 |
| lineup_gap_analysis | 0 |
| lineup_plan_item_event | 0 |

Surviving cases all `unified_lineup_import` / `po_issued`:

| case_id | import_job_id | BU | period | lines | po links |
|---|---|---|---|---|---|
| 7 | 220 | NV | 2026 Q2 | 22 | 1 |
| 9 | 222 | NB | 2026 Q2 | 159 | 28 |
| 90 | 299 | NR | 26Q1 | 104 | 23 |

All 31 completed bulk jobs (256–286): **zero** surviving cases with `import_job_id` matching. Job 255 claimed case_ids 10–41: **none exist**.

`fact_lineup_plan_item` / gap / event: never written (`n_tup_ins=0`). Historical lineup: written then deleted (`n_tup_ins=4`, `n_tup_del=4`, seq `last_value=16`).

### 1.3 Never-written vs written-then-removed

**(b) Applied then removed.**

| evidence | value |
|---|---|
| `commercial_lineup_case_id_seq.last_value` | 113 vs live count 3 / max_id 90 |
| `commercial_lineup_line_id_seq.last_value` | 4298 vs live 285 / max_id 4093 |
| `commercial_lineup_case_po_id_seq.last_value` | 514 vs live 52 |
| `pg_stat` case | `n_tup_del=36`, `n_live_tup=3` |
| `pg_stat` line | `n_tup_del=2000`, `n_live_tup=285` |
| `pg_stat` case_po | `n_tup_del=403`, `n_live_tup=52` |

`pg_stat.n_tup_ins` under-counts vs sequences (stats reset before 2026-07-27 autoanalyze). Sequences are decisive. Soft supersession (`superseded_by_case_id`) would leave rows — these are hard deletes. `lineup_plan_item_event` empty (never used as audit trail).

### 1.4 Cause candidates

| Candidate | Capable? | At scene? |
|---|---|---|
| `POST /dev/database-wipe` → `wipe_all_application_tables` | Yes — all mapped tables | **No.** Lineup `import_job` rows still present. `allow_db_wipe=False` now. |
| `import_job_bulk_delete` | Nulls case `import_job_id`; deletes jobs; does **not** delete cases | **No.** Jobs 256–286 still exist. |
| API `DELETE /lineup-cases/{id}` | Yes — only if `commercial_status='draft_imported'` | Possible for drafts. Surviving cases are `po_issued` (API refuses). No steward_audit delete trail (3 audit rows, none lineup). |
| `lineup_duplicate_partition_repair` | Soft-supersede lines only | Does not hard-delete cases. |
| Alembic DELETE/TRUNCATE on lineup | Grep: none in current versions | Ruled out. |
| `cleanup_test_fixture_customers.py` | Fixture customers only; lineup customer FK `NO ACTION` | No cascade to cases. |
| `_clear_bulk_backfill_cases` in `test_lineup_bulk_backfill_apply_integration.py` | Yes — `DELETE … WHERE source_context='bulk_lineup_backfill'` | **Capable; pattern-matches bulk loss.** Fixture redirects to `cip_bulk_smoke` + `_assert_not_cip` — should not hit `cip` when fixture runs correctly. Does **not** explain missing unified cases 214/215/216/221/298. |
| `test_lineup_case_supersession_delete.py` | Yes — creates/deletes draft cases **on cip by design** (`_require_cip`) | Creates `source_context='test'` only; teardown deletes its own ids. Does not match bulk corpus pattern. Advances case sequence. |
| `test_data_integrity_audit.py` patterned DELETE | Yes | Pattern-limited (`file_name LIKE` / `import_intent='audit'`). |

**Not proven as single actor.** Bulk half matches unguarded bulk teardown pattern; unified losses need a second mechanism.

### 1.5 Blast radius

| Surface | Fact |
|---|---|
| PvE period selector | `enumerate_available_periods` ← PO coverage → **27** periods |
| Lineup-linked quarters | Only **(2026,1)** and **(2026,2)** |
| 2025 Q4 PvE | `planned_units=0`, empty drill |
| A1-07 volume bias | 26Q2: NB/NV only; 26Q1: NR only — not multi-year |
| A1-08 ship-quarter slip | Same two-quarter band |
| PO coverage | `purchase_order`=2327; linked distinct=52; unlinked=2275 |

**Misleading numbers currently rendering: yes.** Multi-year period list from PO coverage while plan-side data is 2 quarters / 3 cases. Bias/slip return numeric means without declaring corpus thinness. A1 multi-year exit criteria are not met on this DB.

---

## SECTION 1 ADDENDUM — Teardown guard audit + deletion dating

### Teardown guard audit

`apps/api/tests/conftest.py` `pytest_runtest_setup` refuses **only** these modules when DB name is `cip` and `ALLOW_TESTS_ON_DEV_DB` unset:

- `test_distributor_sales_inventory_import.py`
- `test_dsi_batch.py`
- `test_dsi_validate_bulk_staging.py`
- `test_historical_lineup_import.py`
- `test_historical_lineup_resolution.py`

**Not in that frozenset:**

| Module | Risk |
|---|---|
| `test_lineup_bulk_backfill_apply_integration.py` | `_clear_bulk_backfill_cases` hard-deletes all `source_context='bulk_lineup_backfill'`. Module uses `bulk_smoke_env` → `cip_bulk_smoke` + `_assert_not_cip`. Guard is **fixture-local**, not conftest-global. If env/settings reload fails or someone calls `_clear_*` without the fixture, **cip is unprotected**. |
| `test_lineup_case_supersession_delete.py` | **Requires cip** (`_require_cip`). Creates/deletes draft cases on the shared DB. |
| `test_data_integrity_audit.py` | Patterned `DELETE FROM commercial_lineup_case`. |
| Other lineup/PO tests using `SessionLocal` / `AsyncSessionLocal` | Mix of skip-if-missing-fixture vs write-to-default-URL; not all gated by conftest. |

**Finding:** teardown guard is import-pipeline-narrow. Lineup commercial corpus is not covered by the same refuse-on-cip rule that protects DSI/historical-lineup import tests.

### Deletion-dating evidence hunt

| Bound | Evidence |
|---|---|
| Bulk applied | Jobs 255–286 completed 2026-07-02 ~10:14–10:16; claimed cases 10–41 |
| Case 90 + lines 3990–4093 created | 2026-07-03 15:46:17 / 15:46:19 |
| Case seq advanced past 90 | `last_value=113` → cases **91–113 created after case 90**, then deleted |
| Line seq past case-90 block | `last_value=4298` vs max live 4093 → further inserts after 2026-07-03 15:46 then deleted |
| Surviving case_po `created_at` max | 2026-07-05 20:25:22 (links only to live cases 7/9/90) |
| Dead line tuples vacuumed | `last_autovacuum` on `commercial_lineup_line` = **2026-07-27 11:00:57**; `n_dead_tup=0` now |
| Case table still has dead tuples | `n_dead_tup=45` on `commercial_lineup_case` (no autovacuum yet) |

**Window:** hard deletes of the missing corpus occurred **after 2026-07-03 15:46** (post case 90 / post further case ids 91–113) and **before 2026-07-27 11:00** (line autovacuum). Bulk cases from 2026-07-02 were removed inside that same window (or earlier for bulk-only if a separate pass — evidence cannot split bulk vs unified delete timestamps further without WAL/logs).

No steward_audit rows record the deletes. No orphan `commercial_lineup_case_po` rows (CASCADE cleaned links when cases deleted).

### Draft-delete question (unified missing cases)

**Answer:** API draft-delete is **capable only while status=`draft_imported`**. It cannot delete the three surviving `po_issued` cases. It **could** have deleted earlier unified cases **if** they never left `draft_imported`.

Evidence that does **not** prove draft-API was the actor:

- Jobs 214, 215, 216, 221, 298 completed with no live case; no audit log of DELETE.
- Job 298 (same NR file, morning 2026-07-03) has no case; job 299 (afternoon) owns case 90 — consistent with re-import, supersession+delete, or hard delete of the morning case; not distinguishable from DB state alone.
- Soft supersession leaves rows; missing rows are hard deletes.
- `delete_lineup_case_restoring_children` (used by cip integration test) also hard-deletes draft winners.

**INFERRED:** unified losses are hard deletes of non-surviving cases; draft-API is one capable path for cases that stayed `draft_imported`, not proven. Bulk losses match `_clear_bulk_backfill_cases` semantics more closely than draft-API.

---

## SECTION 2 — Empty-route triage

Corpus loss (Section 1) is a known root cause for thin commercial-planner / PvE plan-side data. It does not by itself empty scaffold fact tables below.

| Route | Backing | Count | Bucket | Notes |
|---|---|---|---|---|
| `/lineup` | `fact_lineup_plan_item` | 0 | **C** | Real lineup lives in `commercial_lineup_*` (3/285). Page empty-state cites `fact_lineup_plan_item` (`apps/web/.../lineup/page.tsx`). Agreed home is commercial-planner. **Action:** fold/repoint or remove as primary lineup surface. |
| `/commercial-planner` | `commercial_plan` / `commercial_plan_line` | 0 / 0 | **A** | Create-plan UI exists; no plans authored. Lineup cases reachable via planner lineup flows, not via empty plan grid. |
| `/promotions` | `fact_promotion_plan` / API parked | 0; GET always `[]` | **C** | `apps/api/.../promotions.py:25-36` returns `[]` parked. B4 `GET …/promo-plan-draft` composes only, never writes (`promo_plan_builder.py`). **Action:** keep as draft compose host or remove plans tab; do not expect `fact_promotion_plan` to fill. |
| `/budgets` | `fact_budget_allocation` | 0 | **C** | Domain `COMMERCIAL_DOMAIN_RULES` §1.1: budget **derived**, not stored pot. Page built against allocation model that will not populate under current domain. **Action:** remove or repoint to derived reservation from lineup/CPOR. |
| `/budget-requests` | `fact_budget_request` | 0 | **A**/**B** | Table empty; submit UI incomplete (page copy). No producer that will fill under §1.1 without a new workflow. |
| `/pricing` | `fact_pricing` / `pricing_recommendation` | 0 / 0 | Facts **A**; recs **B** | Paste/import for facts; recommendations need planning service run. |
| `/competition` | `fact_competitor_mapping` / `fact_competitor_price` | 0 / 0 | **A** | Awaits competitor feeds. |
| `/roadmap` | `fact_product_roadmap` | 0 | **A** | Awaits strategy ingestion. |
| `/buy-plans` | `fact_buy_plan` | 0 | **B** | Producer = buy/planning engine when upstream facts exist (`page` empty copy). |
| `/inventory` | `fact_inventory_customer` | 0 | **A** (grain note) | DSI SOH lives in `fact_inventory_distributor`=47424; this page reads customer inventory grain. Channel Ops is the live stock surface. |
| `/listing-capture` | `customer_listing` / `listing_observation` | 0 / 0 | **A** | P5 not loaded. |
| `/exceptions` | `exception_inbox_item` | 0 | **B** | Producer = planning/validation systems that write inbox items. |
| `/market` | none (static stub) | — | **C** | `GET /api/v1/market/placeholders` static JSON. **Action:** remove or replace when feeds exist. |
| `/channel-intelligence` | `fact_customer_sellthrough` | 0 | **A** | CST not applied; wiring OK (compute-on-read). |

For every **C**:

| Route | Correct source | Disposition |
|---|---|---|
| `/lineup` | `commercial_lineup_case` / `_line` | Fold into commercial-planner or repoint; do not treat `fact_lineup_plan_item` as SoT |
| `/promotions` | CPOR cases + B4 draft compose | Keep draft panel; retire parked plans/readiness or leave parked with redirect |
| `/budgets` | Derived reservation (lineup profit / CPOR) | Remove allocated-pot UI or rebuild against derived model |
| `/market` | none today | Remove or leave stub labelled non-production |

For every **B** — producer:

| Route | Producer |
|---|---|
| `/pricing` recs | pricing recommendation job/service (not run) |
| `/buy-plans` | buy-plan engine write to `fact_buy_plan` |
| `/exceptions` | exception writers from planning/validation |
| `/budget-requests` | request submit path (incomplete) |

---

## SECTION 3 — Gap to v1

### 3.1 Blocking chains

1. **`commercial_sku_assumption` = 0 → A1-09 support bias + B2 profit/reservation**  
   Pricing resolution reads PM bottom / VAT / FX from `commercial_sku_assumption` (`lineup_pricing_resolution.py`). Count=0 → economics trust flags `missing_sku_assumption`; planned support-bias surface and profit/reservation quality stay blocked/placeholder until steward seed.

2. **Lineup corpus (Section 1) → PvE multi-year + PM bias across years**  
   Known: applied then removed. Live = 2 quarters / 3 cases. PvE offers 27 periods. Multi-year bias/slip not computable. Recovery = re-apply bulk backfill (+ protect from teardown), not code changes to PvE math.

3. **`fact_inventory_customer` = 0 and CST not run → `/inventory`, `/channel-intelligence`**  
   `fact_customer_sellthrough`=0; `customer_sell_through` import_job count=1 historically but fact empty. Channel Ops uses distributor inventory (`fact_inventory_distributor`=47424) — live. Customer-grain pages stay empty until CST apply.

4. **B4 draft not writing a CPOR case → promo builder incomplete**  
   `GET /cpor/intelligence/promo-plan-draft` returns compose dict; `next_step` = create via existing `/cpor/cases`. No POST writer. Exit “new CPOR case authored from history” requires operator to create case manually from draft, or a write path not built.

### 3.2 Reachability (not in `navConfig`)

Confirmed not in `apps/web/src/features/shell/navConfig.ts`:

`/promotions` · `/budgets` · `/budget-requests` · `/pricing` · `/competition` · `/roadmap` · `/buy-plans` · `/inventory` · `/exceptions` · `/market` · `/getting-started` · `/admin/mappings` · `/admin/customer-commercial-terms`

In nav but empty/thin: `/lineup`, `/commercial-planner` (no plans), `/channel-intelligence`, `/listing-capture`.

### 3.3 Demo-surface data quality

| Item | Evidence |
|---|---|
| TMP-CUST on CPOR Cases | `dim_customer` TMP-CUST*=4999/5108; CPOR cases with TMP customer = **296/297** |
| “Deal-stock landing” label | PvE tile label is **“Over-plan intake”** (`PlanVsExecutedView.tsx:684`); category “Over-ships / over-plan intake”. API field `deal_stock_units` remains as alias — visible label renamed. |
| Placeholder / lorem | No lorem found on manager surfaces in this pass. `/market` is an explicit static stub. |
| n/a where number expected | PvE periods without lineup return `planned_units=0` / empty bias — reads as zero-plan, not n/a. Misleading relative to multi-year expectation (Section 1.5). |

### 3.4 Genuinely absent for v1

| Item | Evidence |
|---|---|
| Password reset | No `password reset` / `forgot password` routes in `apps/` |
| Backup/restore UI | Ops page points to `docs/BACKUP_AND_DR.md` only — no in-app restore |
| Unattended report beat | Branch `feat/report-schedules-beat` (PR #17) **not** ancestor of `origin/main` (`merge-base --is-ancestor` exit 1). Main has run-now + inbox schema; beat = BACKLOG-098 |
| Second-user day-one | Session auth exists; no self-serve password reset; TMP-CUST dominates CPOR display codes; hosting Q-003 open |

---

## SECTION 4 — Roadmap correction list

Do **not** edit `docs/ROADMAP.md` in this pass. Claims vs tree; proposed replacement only.

| # | ROADMAP claim | Tree | Proposed replacement |
|---|---|---|---|
| 1 | Header “Status: proposed — commit after review” (L3) | CONTEXT: ROADMAP v3.1 on main (`542d31d`) | `Status: committed on main · CURRENT wins on what’s next.` |
| 2 | P0 “no branch outside main” (L98–99) | Many local/remote feature branches remain | Prefer same-day merge; **not** a repo fact that only `main` exists. |
| 3 | “A1 / A2 / A3 are open” (L391–392) | CURRENT: A1-01…08, A2-01/02/04/05/06, A3-01…04 IMPLEMENTED; A1-09 SPEC ONLY | A-lane core shipped; remaining A1-09; A2-03/A2-X do-not-build. |
| 4 | A1 window “all quarters with lineup coverage; credible core 26Q1→current” + exit shipped (L143–144) | Live corpus **2 quarters / 3 cases** after applied-then-removed (Section 1) | Surfaces shipped on thin band; **multi-year / full-core credibility not met** until corpus restored. |
| 5 | Support bias “blocked on Q-002” (L141–142) while Q-002 resolved (L144/L509) | Q-002 resolved; A1-09 surface not built | Planned side unblocked; surface SPEC ONLY. |
| 6 | P3-1 metric registry lists claim rate (L203–206) vs A2 out-of-scope non-computable (L154–156) | `claim_rate` `do_not_build` / refuse_all | Drop claim_rate from build list; point to non-computable register. |
| 7 | A2 blocks “B3, B4”; graph still has B3 (L82, L341–342) after B2+B3 merge (L7–8) | No separate B3 phase | A2 blocks B4 only; drop B3 node. |
| 8 | B1/B2/B4 written as future (L244–284) | CONTEXT: B1–B4 scaffold on main | Mark scaffold IMPLEMENTED; remaining VERIFY/seed/polish. |
| 9 | P2 exit “Deployed…” (L84) vs body deployment deferred (L174–176) | Local multi-user; Q-003 hosting open | Exit = local multi-user readiness; remote deploy deferred. |
| 10 | P3 exit includes scheduled delivery (L85, L196–238) | P3-1…6 on main; beat on PR #17 only | P3 v1 = builder + inbox + run-now; unattended beat = BACKLOG-098 / PR #17. |
| 11 | Lane X “Unit E … never verified” (L325–326) | PR #12 VERIFY PASS | Mark PASS; remove from open punch-list. |
| 12 | CI “is a gate” / tip hygiene (L79–80) | CI tip pin still `20260801_0008` vs head `20260802_0009`; BACKLOG-087 required-check deferred | Tip must track `20260802_0009`; note required-check debt. |
| 13 | *(align)* Hosting open #3 | Q-003 open — OK | Keep; fix overview via #9. |
| 14 | B2 budget-position as to-build; silence on hard reapproval | `HARD_ENFORCE_BUDGET` + BACKLOG-095 on main | Mark money ceiling / reapproval IMPLEMENTED. |
| 15 | A3 “01/02/03 shipped” (L164) | CURRENT A3-01…**04** | Include YoY coverage (04). |
| 16 | Same-day merge absolute (L401, L413) | Long-lived PR #17 + stale branches | Target for new units; do not claim hygiene complete. |

No prior “12 known” list found under `.tmp/` or `docs/`; this audit enumerates 16.

---

## Findings requiring Warren's decision

1. **Restore lineup corpus?**  
   Finding: applied then removed; jobs + files metadata intact; cases/lines gone.  
   Options: (a) re-run bulk backfill apply from stored previews/files; (b) leave thin 3-case corpus and downgrade A1 claims; (c) restore from backup if one exists outside cip.  
   **Recommend (a)** after teardown guards land — otherwise the same delete path can wipe it again.

2. **Teardown guard expansion?**  
   Finding: conftest only guards 5 import modules; lineup bulk clear is fixture-local; one test **requires** cip for case delete.  
   Options: (a) add lineup modules to refuse-on-cip frozenset; (b) move supersession-delete test off cip; (c) both.  
   **Recommend (c).**

3. **`/lineup` vs commercial-planner?**  
   Finding: `/lineup` is C against `fact_lineup_plan_item=0`.  
   Options: remove from nav; repoint to commercial lineup cases; leave as B2 net-requirement panel only.  
   **Recommend:** nav primary = commercial-planner; demote `/lineup` to net-requirement/B2 tools or remove.

4. **`/budgets` + `/budget-requests` scaffolds?**  
   Finding: conflict with DOMAIN §1.1 derived budget.  
   Options: delete routes; park with redirect to CPOR/lineup reservation; rebuild later under B2.  
   **Recommend:** park/remove from reachability until B2 derived UI is the owner.

5. **A1 exit / ROADMAP honesty?**  
   Finding: A1 surfaces exist but corpus is 2 quarters; ROADMAP implies credible core.  
   Options: rewrite A1 exit language now; restore corpus first then keep language.  
   **Recommend:** rewrite language immediately (docs-only); restore corpus as separate delivery.

6. **TMP-CUST on CPOR (296/297)?**  
   Finding: manager-visible codes are provisional.  
   Options: promote campaign before demos; accept with steward queue; hide codes show names only.  
   **Recommend:** show display name primary; queue promote for strategic customers before external demo.

7. **PR #17 report schedules?**  
   Finding: not on main; P3 exit overstated.  
   Options: merge PR #17; keep BACKLOG-098 and fix ROADMAP; drop schedules from v1.  
   **Recommend:** fix ROADMAP now; merge #17 when beat is ready — do not claim scheduled delivery on main.

8. **B4 write path?**  
   Finding: draft compose only.  
   Options: build create-from-draft POST; keep manual create; defer B4 exit.  
   **Recommend:** defer exit claim; optional thin “create case from draft” wiring when B-lane resumes.

9. **CI Alembic tip pin `0008` vs head `0009`?**  
   Finding: fresh-upgrade assert will fail against current head.  
   Options: bump pin in CI; leave and accept red.  
   **Recommend:** bump pin to `20260802_0009` as a small CI fix (separate from this audit commit).

---

## SECTION 5 — PRE-RESTORE FORENSICS

**Mode:** read-only. `SELECT current_database()` = `cip` before queries. No DML/DDL/VACUUM. No pytest. No migrations. No import/apply.

Established (not re-diagnosed): corpus applied then hard-deleted; window after 2026-07-03 15:46 and before 2026-07-27 11:00.

### Q1 — Who deleted it (out-of-DB artifacts)

| # | Source | Result | Evidence |
|---|---|---|---|
| 1 | PostgreSQL logs (`postgresql-x64-18`) | **FOUND** log dir; **ABSENT** statement-level DELETE trail | Conf: `C:\Program Files\PostgreSQL\18\data\postgresql.conf` — `logging_collector=on`, `#log_statement = 'none'` (effective `log_statement=none` via `pg_settings`), `log_min_duration_statement=-1`. Log dir `…\data\log` has 124 files including full July window. Grep of window logs for `DELETE FROM` / `TRUNCATE` / `commercial_lineup` found only **SELECT** fragments and one missing-relation error on `commercial_lineup_po_link` (2026-07-03 16:53) — **no DELETE statements**. Statement logging was off; this line cannot identify the actor. |
| 2 | `.specstory/` | **ABSENT** in window | 3 files total; `files_in_window=0` for mtime in 2026-07-03 15:46–2026-07-27 11:00. Content hits for `ALLOW_TESTS_ON_DEV_DB` / `commercial_lineup_case` only in `2026-04-12_…project-recovery.md` (outside window). No `_clear_bulk` / `DELETE FROM commercial_lineup` hits. |
| 3 | PSReadLine `ConsoleHost_history.txt` | **ABSENT** for lineup-delete terms | Path exists; mtime 2026-08-02 (file is undated per-line). `lineup`=0, `ALLOW_TESTS_ON_DEV_DB`=0, `commercial_lineup`=0, `bulk_backfill`=0. `pytest` hits are commercial_planner / DSI / health modules — not `test_lineup_bulk_backfill*` / `test_lineup_case_supersession_delete`. `DELETE` hits are redis flush / wipe-pattern *searches*, not SQL against lineup tables. |
| 4 | `apps/api/.pytest_cache/` | **FOUND** cache; **ABSENT** bulk-clear module nodeids as proof of window run | Dir mtime 2026-04-16; `lastfailed` mtime **2026-08-02 10:54**, `nodeids` mtime **2026-08-02 13:32** (after delete window). Cache lists `test_historical_lineup_*`, `test_lineup_po_auto_link_*`, commercial_planner lineup API tests — **not** `test_lineup_bulk_backfill_apply_integration` / `test_lineup_case_supersession_delete`. Does not timestamp a window execution. |
| 5 | `git log` 2026-07-03…07-27 on teardown files | **FOUND** code changes in window; **ABSENT** execution proof | `test_lineup_bulk_backfill_apply_integration.py`: `6b84187` **2026-07-03 22:43** (inside window). `_clear_bulk_backfill_cases` / `_assert_not_cip` introduced earlier `c7f45eb` **2026-07-01** (before corpus apply). `conftest.py`: `4f3a434` 2026-07-16 (DSI gates only — lineup modules still not in refuse frozenset). `test_lineup_case_supersession_delete.py`: **no commits in window**. |
| 6 | `git reflog` + untracked delete scripts | **ABSENT** window delete actor | Reflog entries examined are 2026-08-01/02 merges (after window). Untracked `*.py` under status: `apps/api/scripts/ops/browser_db_parity_audit.py` only (read/audit, not lineup delete). |
| 7 | Repo-wide grep delete of `commercial_lineup_*` | **FOUND** capable code only (already in §1.4) | Tracked: `test_lineup_bulk_backfill_apply_integration.py` `_clear_bulk_backfill_cases`; `test_data_integrity_audit.py` patterned DELETE; `test_shipment_null_distributor_sibling_po_merge.py` DELETE case_po; `lineup_po_auto_link_actions.py` delete dismiss rows. No new untracked `.tmp` script that mass-deletes commercial lineup cases. |

**Cursor agent-transcripts (extra):** 66 `.jsonl` files with mtime in window. Content search for `_clear_bulk` / `DELETE FROM commercial_lineup` / supersession-delete test: **1** match — transcript `ed653a07-…` **2026-07-05** editing/running bulk/BU lineup tests against **`cip_alembic_smoke` / disposable URLs** (commands set `DATABASE_URL_SYNC=…/cip_alembic_smoke`). Not proof of cip corpus wipe.

#### Q1 verdict: **UNRECOVERABLE**

No timestamped artifact names an actor that executed DELETE against `commercial_lineup_*` on `cip` inside the window. Postgres statement logging was off. Chat/PS/pytest caches do not record a cip-targeted clear. Capable code paths remain those in §1.4; out-of-DB search does not promote any to PROVEN or PROBABLE.

---

### Q2 — Job 217 Numeric(8,4) overflow — restore recurrence

**Columns with Numeric(8,4)** on `commercial_lineup_line` (`information_schema` + `apps/api/app/models/commercial_lineup.py:72-74`):

| column | type | meaning |
|---|---|---|
| `rebate_pct_evidence` | numeric(8,4) | file rebate **percentage** evidence |
| `distributor_margin_pct_evidence` | numeric(8,4) | file distributor margin **percentage** evidence |
| `vat_pct_evidence` | numeric(8,4) | file VAT **percentage** evidence |

Overflow rule: absolute value must be `< 10^4` (= 10000). Job 217 `error_summary` INSERT parameters include values **`72860.10…`** and **`67585.03…`** in the pct-evidence positions, with diagnostics `invalid_dealer_margin`, `invalid_rebate`, `invalid_distributor_margin`. Raw payload shows `"Dealer margin": "74347…"` / money-scale cells mapped into margin/rebate fields. **Class: parse/mapping error** (currency amounts into pct columns), not a legitimate ≥10000% rate.

**Writer path (shared parser used by unified + bulk):**

```377:412:apps/api/app/services/commercial_planner/lineup_case_parser.py
        msrp_local = _safe_float(raw.get("msrp_local"))
        pct_evidence: dict[str, float | None] = {}
        for field in _PCT_EVIDENCE_FIELDS:
            raw_pct = _safe_float(raw.get(field))
            clean_pct = sanitize_pct_evidence(raw_pct, reference_price=msrp_local)
            ...
            pct_evidence[field] = clean_pct
        ...
                "rebate_pct_evidence": pct_evidence["rebate_pct_evidence"],
                "distributor_margin_pct_evidence": pct_evidence["distributor_margin_pct_evidence"],
                "vat_pct_evidence": pct_evidence["vat_pct_evidence"],
```

```52:73:apps/api/app/services/commercial_planner/lineup_pricing_resolution.py
def sanitize_pct_evidence(...):
    """Reject file values that cannot plausibly be a margin/rebate/VAT percentage.
    ...
    """
    ...
    if av <= _MAX_WHOLE_NUMBER_PCT_EVIDENCE:  # 100.0
        return v
    if reference_price is not None and reference_price > 0 and av <= reference_price:
        return None
    return None
```

**Timeline:** Job 217 failed **2026-06-28 18:38**. Guard commit `b26ef24` **2026-06-28 19:27** (“pct overflow guard”) introduced `sanitize_pct_evidence`. Same file later completed as bulk job **262** on **2026-07-02** (after the guard).

**On re-run today:** does **not** fail with NumericValueOutOfRange. Money-scale “Rebate”/“Dealer margin” cells are **nulled** on `*_pct_evidence` (kept in `raw_row_payload`); insert proceeds. Does **not** silently write the overflow into pct columns. Pricing chain still flags invalid margins when calculator inputs are bad — evidence columns stay null for those fields.

---

### Q3 — 1H period split on bulk vs unified

#### Bulk path precedence (implemented)

`lineup_bulk_period_inference.py` module docstring + `resolve_layered_period`:

> Priority: folder path → title band (F1) → filename → manual steward entry.  
> `1H` always expands to Q1 + Q2.

```238:278:apps/api/app/services/commercial_planner/lineup_bulk_period_inference.py
    # 1H from ANY tier triggers Q1+Q2 split; folder anchors year (and quarter when present).
    if half_sig is not None:
        ...
        assignments = [
            LayeredPeriodAssignment(..., flags=... + ["period_half_split_q1"]),
            LayeredPeriodAssignment(..., flags=... + ["period_half_split_q2"]),
        ]
```

Apply wires allocation half into parse options:

```221:259:apps/api/app/services/commercial_planner/lineup_bulk_backfill_apply.py
    if "period_half_split_q1" in period_flags:
        half_alloc = "q1"
    elif "period_half_split_q2" in period_flags:
        half_alloc = "q2"
    ...
            "half_year_allocation_half": half_alloc,
```

Parser applies `apply_half_year_allocation_to_row_dict` when `half_year_allocation_half` is set (`lineup_case_parser.py:584-587`). That uses `allocate_uniform_half` (`lineup_half_year_quantity.py`); month-derived tier exists in `lineup_month_derived_allocation.py` (post-2026-07-04) as upgrade over pure uniform_half.

**Dry-run (CURRENT code, no DB write)** for job-262 shape `folder_path=PF\Q2` + filename containing `1H 2025`:

- assignments: **2025 Q1** + **2025 Q2** with `period_scope=1h_split` / `period_half_split_q1|q2`
- report: `half_trigger_tier=filename`, `winning_tier=folder`, `half_split=True`

**Historical job 255/262:** apply result for that file = **one** case_id 16, `supersession_group_key=2025-01-01|47|PF` only. Job 262 `staged_metadata.lineup_parse_options` has `folder_path=PF\Q2` / sheet / BU — **no** `half_year_allocation_half`. So the **historical** load of that 1H file was a **single** case (Q1 start) **without** half allocation in parse options — not the current dual-case split.

#### Unified path precedence

`unified_lineup_import.py` creates one case per file; optional request `period_label` only — **no** folder layered stack:

```57:65:apps/api/app/services/commercial_planner/unified_lineup_import.py
            case = CommercialLineupCase(
                ...
                period_label=period_label,
                ...
                source_context="unified_lineup_import",
            )
```

Period start inferred in shared parser via `infer_period_start(case.period_label, header_cols)` (`lineup_period_inference.py`: label year + month columns / label quarter; **no** 1H→Q1+Q2 fan-out).

**Surviving unified cases:**

| id | period_label | inferred_period_start | signal notes |
|---|---|---|---|
| 7 | 2026 Q2 | 2026-04-01 | Filename contains “Q1 2026”; stored period is Q2 — label/inference won over filename token |
| 9 | 2026 Q2 | 2026-04-01 | Matches Q2 filename |
| 90 | 26Q1 | 2026-01-01 | Matches Q1 filename / label |

#### Q3 answer

- **Bulk path (CURRENT):** **yes** — implements 1H → Q1+Q2 with half allocation flags; re-run of a 1H file under `PF\Q2` dry-runs to **both** quarters.  
- **Bulk path (historical job 262):** **did not** persist dual-half parse options; single Q1-dated case.  
- **Unified path:** **no** 1H split fan-out — one case per file; 1H files need bulk (or steward re-derivation) for Q1+Q2.

---

### Self-check

- Wrote to any database? **No** (SELECT-only + pure-Python period dry-run).  
- Ran any test/pytest? **No**.  
- Modified files other than this audit doc? **No** (append only).  
- Claims without printed/quoted evidence labelled INFERRED where used.

---

## SECTION 6 — CORPUS VERIFICATION

**Mode:** AUDIT / READ-ONLY. `SELECT current_database()` = `cip` before queries. No DML. No re-apply of session 752. No pytest. No migration. No code changes.

**Established (not re-diagnosed):** folder-tier period derivation is intended; 1H must fan to Q1+Q2; survivors 7/9/90 are correct; corpus-loss attribution closed.

**Archive root used:** `.tmp/ProductLineupArchive` (28 xlsx). Preview session `import_job` **752**.

### Q1 — What is actually missing

`current_database()` printed: **cip**.

#### Archive file → case(s)

| Archive file | Case(s) in cip |
|---|---|
| `NB\2025\Q1\1. ACZA Q1 2025 Consumer Lineup - Sales.xlsx` | 114 NB 2025 Q1 lines=197; 115 NV 2025 Q1 lines=2; 116 NV 2025 Q2 lines=2; 141 NB 2025 Q2 lines=0 **superseded→117** |
| `NB\2025\Q2\1. ACZA Q2 2025 Consumer Lineup - Sales.xlsx` | 117 NB 2025 Q2 lines=190 |
| `NB\2025\Q3\1. ACZA Q3 2025 Consumer Lineup - Sales.xlsx` | 118 NB 2025 Q3 lines=204 |
| `NB\2025\Q4\1. ACZA Q4 2025 Consumer Lineup - Sales.xlsx` | **NOT PRESENT** |
| `NB\2026\26Q1\1. ACZA 1H 2026 Consumer Lineup - Sales.xlsx` | 119 NB 2026 Q1 lines=289 |
| `NB\2026\26Q1\2. ACZA 1H 2026 Consumer Lineup - Sales.xlsx` | 120 NB 2026 Q1 lines=**0**; 121 NB 2026 Q2 lines=**0** |
| `NB\2026\26Q2\1. ACZA Q2 2026 Consumer Lineup - Sales.xlsx` | **9** NB 2026 Q2 lines=159 `po_issued` (survivor) |
| `NB\2026\26Q2\2. ACZA Q2 2026 Consumer Lineup - Sales.xlsx` | 122 NB 2026 Q2 lines=168 |
| `NB\2026\26Q3\1. ACZA Q3 2026 Consumer NB Lineup - Sales.xlsx` | 123 NB 2026 Q3 lines=221 |
| `NR\2025\Q2\2. ACZA Q2 2025 Gaming Lineup latest version please use.xlsx` | 124 NR 2025 Q2 lines=131 |
| `NR\2025\Q2\Do not use, previous Q2 lineup, kept as reference .xlsx` | **NOT PRESENT** (excluded `f10`) |
| `NR\2025\Q3\1. ACZA Q3 NR Gaming Lineup - Sales Team.xlsx` | 125 NR 2025 Q3 lines=133 |
| `NR\2025\Q4\1. Q4 Gaming Notebook - Sales Lineup.xlsx` | 126 NR 2025 Q4 lines=141 |
| `NR\2026\26Q1\2. ACZA Q1 2026 NR Gaming Lineup.xlsx - Sales Team Copy.xlsx` | **90** NR 26Q1 lines=104 `po_issued` |
| `NR\2026\26Q1\Q1 2026 NR Gaming Lineup Updated.xlsx` | 127 NR 2026 Q1 lines=117 |
| `NR\2026\26Q2\Q2 Gaming NR Lineup - Sales Team.xlsx` | 128 NB 2026 Q2 lines=6 |
| `NR\2026\26Q3\1. ACZA Q3 2026 Consumer Gaming NR Lineup - Sales Team.xlsx` | 129 NB / 130 NR / 131 NB — 2026 Q3 — lines 6/14/1 |
| `NV\2026\2. ACZA Q1 2026 NV Ally Lineup - Sales Team Copy.xlsx` | **7** NV 2026 Q2 lines=22 `po_issued` |
| `NV\2026\Q2 Ally NV Lineup - Sales Team.xlsx` | 132 NV 2026 Q1 lines=9 |
| `NV\Q3\1. Q3 ROG Ally RC73 Lineup - Sales Lineup.xlsx` | 142 superseded→133; lines=0 |
| `NV\Q4\2. ACZA Q4 2025 NV lineup.xlsx` | 133 NV `NV\Q4` / period_start NULL lines=40 |
| `PF\Q2\Copy of ACZA 1H 2025 Consumer Lineup - Gaming Desktop PD 13 Feb 2025.xlsx` | 134 PF 2025 Q1 lines=63; 135 PF 2025 Q2 lines=63 |
| `PF\Q3\1. Q3 Gaming Desktop - Sales Lineup.xlsx` | 143 superseded→136; lines=0 |
| `PF\Q4\1. Q4 Gaming Desktop - Sales Lineup.xlsx` | 136 PF `PF\Q4` / period_start NULL lines=11 |
| `XB\2025\Q2\1. ACZA Q2 2025 Sales ACCY Lineup.xlsx` | 137 XB 2025 Q2 lines=65 |
| `XB\2025\Q2\2. ACZA Q2 2025 Sales ACCY Lineup.xlsx` | 138 XB 2025 Q2 lines=27 |
| `XB\2025\Q3\1. Q3 Accessories - Sales Lineup.xlsx` | 139 XB 2025 Q3 lines=30 |
| `XB\2025\Q4\1. Q4 Accessories - Sales Lineup.xlsx` | 140 XB 2025 Q4 lines=35 |

DB cases with `file_name` not in archive: **none**.

#### Suspected gaps — confirmed

**(a) `1. ACZA 1H 2026 Consumer Lineup - Sales.xlsx` Q2 half — ABSENT.**  
Only case **119** (2026 Q1, 289 lines). No case holds this file’s Q2. Ready proposal `f4:NB:NB:2026 Q2` was in `ready_not_applied` with the exclusion set (skipped with `f6`/`f13`/`f17`/`f10`). Absent: a 2026 Q2 case for this filename with half `q2` / `allocation=uniform_half`.

**(b) Cases 120/121 — CONFIRMED.** Shells for `2. ACZA 1H 2026…`, lines=0; parse jobs 759/760 failed (`Promo R19999`).

**(c) Other gaps:**  
- **`NB\2025\Q4\1. ACZA Q4 2025 Consumer Lineup - Sales.xlsx` — NOT PRESENT.** Preview had it as `f3:NB:NB:unknown` **needs_attention** (`period_signal_conflict`) — never ready, never applied.  
- **`Do not use…xlsx` — NOT PRESENT** by design (excluded `f10`).  
- Zero-line **active** cases: **120, 121 only** (superseded shells 141/142/143 also 0 lines — expected).

#### Completeness statement

Corpus is **not** complete apart from (a)(b). At minimum also missing **NB Q4 2025 Consumer** (needs_attention, never applied). Intentional absences: Do-not-use file; overlap exclusions vs survivors 7/9/90 (`f6`/`f13`/`f17` and side-effect `f4` Q2).

---

### Q2 — Monthly quantity grain

#### Columns (printed from `information_schema` + model)

| Column | Type | Role |
|---|---|---|
| `quantity_units` | `numeric` | Single persisted quantity (quarter/half allocation target) |
| `month_split_json` | `jsonb` | Intended monthly map |

**Both exist in schema.** On restored corpus: `month_split_json` non-null = **0** / null = **2450**.

#### Parser that ran (commercial bulk path = `lineup_case_parser.py`)

Quantity read is **only** the mapped `Qty` header via aliases — not per-month columns:

```22:22:apps/api/app/services/commercial_planner/lineup_header_mapping.py
    "quantity_units": ["qty", "quantity", "units", "forecast_qty"],
```

```398:398:apps/api/app/services/commercial_planner/lineup_case_parser.py
                "quantity_units": _safe_float(raw.get("quantity_units")),
```

`CommercialLineupLine(...)` construction in the same file sets `quantity_units=rd.get("quantity_units")` and **does not set `month_split_json`**. Grep of `lineup_case_parser.py` for `month_split`: **no matches**.

Historical importer **does** collect Jan–Dec abbrev columns into `_month_split` → `month_split_json` (`historical_lineup.py` ~311–352, ~773–796). That path is **not** the restore parse path.

Month cells still appear under `raw_row_payload.uploaded` (full header dump) but are **not** written to `month_split_json`.

#### Sample (5 restored lines, case 114)

| line id | case | uploaded months (evidence) | `quantity_units` | `month_split_json` |
|---|---|---|---|---|
| 4299 | 114 | Feb=72, Apr=36, May=36, Qty=144 | 72.0 | null |
| 4300 | 114 | Feb=114, Apr=76, May=76, Qty=266 | 133.0 | null |
| 4301 | 114 | Feb=5, Qty=5 | 3.0 | null |
| 4302 | 114 | Feb=5, Qty=5 | 3.0 | null |
| 4303 | 114 | Feb=10, Apr=10, May=10, Qty=30 | 15.0 | null |

#### VERDICT Q2

**No** — monthly quantities are **not** parsed into `month_split_json` on the commercial restore path. Grain is lost at `lineup_case_parser` persist (never maps month columns → `month_split_json`). Only a single `quantity_units` (from `Qty`, then often half-split) is stored. Uploaded month cells survive only as opaque JSON in `raw_row_payload.uploaded`.

---

### Q3 — `uniform_half` vs real monthly data

#### Code that sets / applies it

Flag constant and 50/50 math:

```9:31:apps/api/app/services/commercial_planner/lineup_half_year_quantity.py
HALF_YEAR_ALLOCATION_FLAG = "allocation=uniform_half"
...
def allocate_uniform_half(value: float | None, *, half: str) -> float | None:
    """Q1 gets ceil half; Q2 gets floor half — sum equals source exactly."""
    ...
        return float(math.ceil(v / 2.0))
    ...
        return float(math.floor(v / 2.0))
```

Applied on parse when `half_year_allocation_half` is q1/q2:

```584:588:apps/api/app/services/commercial_planner/lineup_case_parser.py
        half_alloc = parse_opts.get("half_year_allocation_half")
        if half_alloc in ("q1", "q2"):
            row_dicts = [
                apply_half_year_allocation_to_row_dict(rd, half=str(half_alloc)) for rd in row_dicts
            ]
```

`apply_half_year_allocation_to_row_dict` **overwrites** `quantity_units` (and listed monetary fields) with `allocate_uniform_half(float(source), half=…)`, snapshotting prior value as `half_year_source_*` in `raw_row_payload`.

#### (i) vs (ii)

**VERDICT: (ii)** — computes a 50/50 estimate and **overwrites** `quantity_units`. It does not leave real monthly values as the stored quantity. Month columns are not inputs to this path (see Q2).

#### Proof — clearer file (case 114 row 1) and PF 134/135

**Case 114 (1H-split NB Q1 2025):** uploaded `Feb=72, Apr=36, May=36, Qty=144`; stored `quantity_units=72`, `half_year_source_quantity_units=144`, diag includes `allocation=uniform_half`. `ceil(144/2)=72` — matches half of **Qty**, **not** a month-derived Q1 sum of real monthly cells.

**PF Gaming Desktop (134/135) vs source file `PD Lineup 13 Feb 25`:**  
Source row 1: `Qty=0.15`, `Total Qty=1`, `May\n(TBC)=1`.  
Case 134 row 1: `half_src=0.15`, `quantity_units=1.0` (`ceil(0.15/2)`).  
Case 135 row 1: `half_src=0.15`, `quantity_units=0.0` (`floor(0.15/2)`).  
`month_split_json` null on both. Stored quantities do **not** match `Total Qty` / `May (TBC)`; they are the uniform half of the mis-mapped `Qty=0.15` cell. (Separate mapping smell: this workbook’s `Qty` column is not unit totals — noted as evidence only, not fixed.)

**Defect class:** (ii) is a **data-correctness** defect relative to real monthly grain when month columns exist. Change nothing in this audit.

---

### Q4 — Why Promo is parsed at all

#### Offending cell

File: `.tmp/ProductLineupArchive/NB/2026/26Q1/2. ACZA 1H 2026 Consumer Lineup - Sales.xlsx`, sheet **`NB`**, header row 3.  
Column header **`Promo Price`** (excel col index 51). Example cell: row 7 = `'Promo R19999'` (56 such `Promo R…` values on the sheet).

Column map (printed): `promo_price_evidence_local <- 'Promo Price'` via explicit alias list (not positional catch-all):

```37:49:apps/api/app/services/commercial_planner/lineup_header_mapping.py
    "promo_price_evidence_local": [
        "promo_price",
        "promo_srp",
        "promo",
        ...
        "promo price",
        ...
    ],
```

Initial parse uses `_safe_float` (returns `None` on `'Promo R19999'` — does **not** crash).

Crash site: `apply_half_year_allocation_to_row_dict` falls back to `raw_row_payload['promo_price_evidence_local']` (string kept by `_safe_str`) and calls bare `float(source)`:

```59:68:apps/api/app/services/commercial_planner/lineup_half_year_quantity.py
        source = out.get(field)
        if source is None and field in raw:
            source = raw.get(field)
        ...
        allocated = allocate_uniform_half(float(source), half=half)
```

Reproduced: `_safe_float('Promo R19999')` → `None`; `apply_half_year_allocation_to_row_dict(... half='q1')` → **`ValueError: could not convert string to float: 'Promo R19999'`**. Cases 120/121 are 1H halves → half alloc always runs → fail.

#### Is the field needed?

`promo_price_evidence_local` is an **optional** commercial evidence field on `CommercialLineupLine` (pricing chain). Promo content is not required for lineup quantity/import completeness; it is incidental evidence, not a quantity key.

#### Existing fixes — reachability

| Helper | Exists? | Reaches this path? |
|---|---|---|
| `_safe_float` in `lineup_case_parser` | Yes | Soft-nulls promo at row build; **does not** protect half-alloc fallback |
| `sanitize_pct_evidence` | Yes | Only pct fields; not money/promo strings |
| Historical `_parse_decimal` | Yes | Soft-fail on historical apply; **not** used by commercial `lineup_case_parser` / half-alloc |
| Currency/label stripper for `Promo R19999` | **No** match found on commercial parse path |

#### VERDICT Q4 — recommended fix (do not implement)

Prefer **(b) sanitize / safe-coerce** at `apply_half_year_allocation_to_row_dict` (never bare `float` on allocatable fields; skip or null non-numeric) **and/or** strip currency labels before coerce.  
**(a)** stop reading Promo entirely is optional product choice (field is optional evidence) but would not alone fix other non-numeric strings in allocatable fields.  
**(c)** also: stop falling back from typed `None` to raw string payload for numeric allocation.

Minimum correct fix for this failure class: make half-alloc resilient like `_safe_float` / `_parse_decimal` so optional promo garbage cannot abort the whole parse.

---

### Self-check (Section 6)

- Wrote to any database? **No**.  
- Changed any code? **No**.  
- Modified files other than this audit doc? **No** (append only).  
- Re-applied 752? **No**.

---

*End of audit (Sections 1–6). Committed artifact: this file only.*
