# VERIFY debt runbook — units 6f, 7, 8, 11, 12, 15B, B4

**Created:** 2026-08-30 · **Authority:** Charter v1.3 amendment 7 · Register:
`docs/BACKLOG.md` § VERIFY-debt register · Detail: `docs/design/IMPLEMENTATION_PLAN.md` § Item 0

This document is **discovery output** for clearing VERIFY debt before promotion to `main`.
It does **not** substitute for Opus CONSULT VERIFY.

---

## Governance (non-negotiable)

| Rule | Source |
|------|--------|
| **Cursor must not self-PASS** | `docs/AUTONOMOUS_BUILD_CHARTER.md` v1.3 quality bar |
| Only **`VERDICT: PASS`** from **Opus CONSULT** (or Warren written waiver in `CURRENT.md`) clears a register row | Charter dual-agent loop |
| Steward/import units: VERIFY walks **S1–S14** in `docs/STEWARD_EXPERIENCE_CONTRACT.md` (v1.6); REQUIRED row PARTIAL/ABSENT without waiver → `VERDICT: STOP` | `.cursor/templates/verify_seed_template.md` |
| **No writes to `cip`** during VERIFY | Charter database policy; `ALLOW_TESTS_ON_DEV_DB` stays **unset** |
| Tests / compute smoke: target **`cip_test`** (override **both** `DATABASE_URL_SYNC` and `DATABASE_URL_SYNC_MIGRATE`) | Charter + `AGENTS.md` |
| Backup/restore soak (Unit 8): target **`cip_alembic_smoke` only** | `docs/UNIT8_DEMO_P2_GATE.md` |
| Browser smoke is mandatory for UI units | `.cursor/rules/smoke-via-browser.mdc` |
| Unit whose evidence no longer exists → close as **`SUPERSEDED`** with reason, **not** PASS | Warren directive 2026-08-30 |

### Evidence recording (on PASS)

1. Consultant output: `.tmp/<unit>_verify_opus_response.md` (never commit).
2. Seed from `.cursor/templates/verify_seed_template.md` when steward S-rows apply.
3. On `VERDICT: PASS`: mark row cleared in `docs/BACKLOG.md` VERIFY register (date + SHA);
   append one line to `CONTEXT.md`; optional pin in `docs/memory/CURRENT.md`.
4. On `VERDICT: STOP`: fix + re-verify; do not clear register row.
5. On **SUPERSEDED**: register row → `SUPERSEDED` + reason + NS unit that replaced the surface.

### Pre-flight (every session)

```powershell
git fetch origin
git rev-parse --short HEAD   # pin in verify seed
# Confirm contract version header in STEWARD_EXPERIENCE_CONTRACT.md matches seed (v1.6)
```

---

## Session plan (cheapest first, ≤3 units each)

| Session | Units | Stack | DB |
|---------|-------|-------|-----|
| **A** | 6f (auto), 7 (auto), 15B (auto) | None | None |
| **B** | 12 (auto), B4 (auto) | None | None |
| **C** | 8 | API + Web | `cip` read-only for A5–A7; **`cip_alembic_smoke`** for B1–B4 restore |
| **D** | 7 (browser), 6f (browser + read) | API + Web | `cip` **read-only** (case 1016 / audit); no Accept if avoiding writes |
| **E** | 11 | API + Web | `cip_test` if apply/progress exercised; else read-only browser |
| **F** | 15B (browser), B4 (browser) | API + Web pointed at **`cip_test`** | **`cip_test`** for compute/create-case |

**Order rationale:** mocked pytest/vitest first (no services); then ops soak; then read-only
browser; then steward parity (largest CONSULT surface); then write-path browser on disposable DB.

---

## Unit 6f — D-040 distributor attribution propose→confirm

**Shipped:** 2026-08-08 · **PR #18** merge `d9857ee` · feature commits `0f70571`, `91d247b`  
**Branch (historical):** `feat/unit6f-distributor-attribution-confirm`  
**Migration:** `20260807_0010_distributor_attribution_status.py` (already on dev DBs — do not re-run without approval)

### Contract / decisions

| ID | Requirement |
|----|-------------|
| **D-040** | `distributor_attribution_status`: `token_proposed` → `shipment_confirmed` / `steward_set` / `conflict`; Accept ship-corroborated; soft-clear; Phase-1 confirmer exact qty; **no auto-clear on conflict** (`docs/STEWARD_ENGINE_DECISIONS.md` § D-040) |
| Amends **D-038** | Dual-write OPEN_CHANNEL + line `distributor_id` on token stamp |

### (a) Automated

```powershell
cd apps/api
.\.venv\Scripts\activate
# No DB — pure logic tests (file is NOT named test_d040_*; register name is stale)
pytest tests/test_lineup_distributor_attribution.py -v
```

**Pass criteria:** all tests green, especially:

- `test_sole_exact_offers_accept_when_null_dist`
- `test_sole_exact_confirms_matching_proposed`
- `test_absent_proposed_sets_conflict_keeps_semantics` (FK kept on conflict)
- `test_multi_dist_leaves_proposed_when_present`

**Evidence:** `apps/api/tests/test_lineup_distributor_attribution.py` exercises
`_evaluate_token_group` from `lineup_distributor_attribution.py`.

### (b) Browser

| Step | Route / action | Observe |
|------|----------------|---------|
| 1 | Login admin → `/admin/po-management` | `DistributorAttributionReviewSection` visible (`PoManagementView.tsx`) |
| 2 | Filter **Proposed** / `token_proposed` | Rows with ship-corroboration offer |
| 3 | Case **#1016** (if present on DB) | Proposed → **Accept** ship-corroborated → status confirmed (`shipment_confirmed` or `steward_set`) |
| 4 | Conflict token (if seeded) | Distributor FK **not** auto-cleared |
| 5 | Soft-clear action | `distributor_id` null, status cleared; OC alias retained |

**Pass criteria:** operator can complete Accept; conflict rows stay reviewable; no silent clear.

**Environment flag:** case **1016** is **dev-data-specific** (`IMPLEMENTATION_PLAN.md` § Item 0).
If absent on target DB, VERIFY uses any live `token_proposed` row with ship offer — record case id
in verify output. Do not treat missing 1016 as PASS without substitute evidence.

**Write note:** Accept/confirm **writes** lineup lines. For strict no-`cip`-write policy, limit
browser to **read-only** review of existing confirmed rows + rely on pytest for transitions;
document limitation in verify seed. Full PASS normally expects one controlled write on **`cip_test`**
clone with disposable case.

### (c) Data (read-only on `cip`)

```sql
SELECT current_database();  -- must be cip for read; never mutate

-- Status distribution
SELECT distributor_attribution_status, count(*)
FROM commercial_lineup_line
WHERE distributor_attribution_status IS NOT NULL
GROUP BY 1;

-- Audit trail for attribution actions
SELECT action, entity_type, created_at, payload_json->>'norm_token' AS token
FROM steward_audit_event
WHERE action LIKE 'lineup_distributor_attribution%'
ORDER BY created_at DESC
LIMIT 20;

-- Case 1016 spot-check (if exists)
SELECT id, distributor_id, distributor_attribution_status, quantity_units
FROM commercial_lineup_line
WHERE case_id = 1016
  AND distributor_attribution_status IS NOT NULL
LIMIT 20;
```

### Superseded?

**No** — PO Management / attribution review not replaced by North Star yet. NS-5 Lineup may
relocate UI; D-040 semantics remain until explicitly superseded.

### Stale register note

`IMPLEMENTATION_PLAN.md` cites `pytest test_d040_*` — **no such files exist**. Canonical tests:
`test_lineup_distributor_attribution.py`.

---

## Unit 7 — BACKLOG-068 Shipping lineup-quarter strip

**Shipped:** 2026-08-12 · **PR #31** merge `8b40820` · commit `4e48acb`  
**Branch (historical):** `feat/backlog-068-landed-quarter`

### Contract / decisions

| ID | Requirement |
|----|-------------|
| **BACKLOG-068** | `landed_this_quarter_units` (pod_date calendar quarter) + `shipped_not_landed_units`; **PvE fill unchanged** (shipped-basis) |
| **SH-01 / SH-02** | Lifecycle / commercial cohorts (`docs/COMMERCIAL_SEMANTICS.md` §4.2) |

### (a) Automated

```powershell
cd apps/api
.\.venv\Scripts\activate
pytest tests/test_inbound_lineup_quarter.py -v
```

**Pass criteria:** `test_accumulate_landed_this_quarter_vs_plan_landed` proves landing-axis vs
plan-axis separation.

### (b) Browser

| Step | Route | Observe |
|------|-------|---------|
| 1 | `/shipping` | `data-testid="lineup-quarter-summary"` strip visible |
| 2 | Select plan quarter with data | Labels: **"Shipped (awaiting POD)"**, **"Landed this quarter"**, **"Landed (plan quarter)"** |
| 3 | Hover titles | Match semantics in `ShippingLineupQuarterSummary.tsx` (awaiting POD = `pod_date` null) |
| 4 | `/plan-vs-executed` | Fill rate % **unchanged** vs pre-068 baseline (shipped-basis only) |

**API spot-check (read-only):**

```http
GET /api/v1/shipping/lineup-quarter-summary?plan_quarter=26Q3
```

Expect JSON keys `landed_this_quarter_units`, `shipped_not_landed_units`, `landed_units`.

### (c) Data (read-only on `cip`)

```sql
SELECT current_database();

-- Sanity: shipped-not-landed vs landed-this-quarter are derivable from facts
SELECT
  count(*) FILTER (WHERE line_state = 'shipped' AND pod_date IS NULL) AS shipped_awaiting_pod,
  count(*) FILTER (WHERE line_state = 'shipped' AND pod_date IS NOT NULL) AS shipped_with_pod
FROM fact_inbound_shipment
LIMIT 1;  -- adjust with tenant/filter as needed
```

Compare magnitudes to API strip for one quarter — not exact row match (read model aggregates).

### Superseded?

**Not yet.** NS-3 Stock Inbound lens must **re-run** Unit 7 strip semantics (`IMPLEMENTATION_PLAN.md`
NS-3 VERIFY). Until NS-3 PASS, verify on `/shipping`.

---

## Unit 8 — Demo / P2 gate

**Shipped:** 2026-08-12 · **PR #36** merge `487bfd2` · commit `a23bb34`  
**Branch (historical):** `feat/unit8-demo-p2-gate`  
**Gate doc:** `docs/UNIT8_DEMO_P2_GATE.md`

### Contract / decisions

| Module | Rows |
|--------|------|
| **P2-3 Auth + RBAC** | Login, sessions, roles, admin-adds-users, default-deny (`docs/AUTONOMOUS_BUILD_CHARTER.md`) |
| **P2-5 Backup/DR** | Tested restore (`docs/BACKUP_AND_DR.md` proof log) |

### (a) Automated

No dedicated Unit 8 pytest file. Optional regression:

```powershell
cd apps/api
.\.venv\Scripts\activate
pytest tests/test_rbac_r1c_admin_gates.py tests/test_auth_password_roles.py -v
```

Not sufficient alone for PASS — browser A1–A8 mandatory.

### (b) Browser — Section A (`docs/UNIT8_DEMO_P2_GATE.md`)

| # | Route / action | Observe |
|---|----------------|---------|
| A1 | Admin → `/admin/users` | Create-user form visible |
| A2 | — | `viewer@local` exists (role viewer) |
| A3 | Reset password | ≥8 chars |
| A4 | Logout | `/login` |
| A5 | Login viewer → `/dashboard` | Welcome + freshness (Control tower) |
| A6 | Viewer → `/shipping` or `/plan-vs-executed` | Data grid loads unaided |
| A7 | Viewer → `/admin/users` | `data-testid="users-forbidden"` — no create form |
| A8 | `/login` | Forgot-password copy points to admin reset |

**Credentials (local dev):** `viewer@local` / `changeme1` per gate doc re-PASS 2026-08-14.

### (b) Ops — Section B (writes **`cip_alembic_smoke` only**)

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/backup_cip.ps1

powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/restore_cip_smoke.ps1 `
  -DumpPath .tmp\backups\<latest>.dump
```

**Pass criteria:** stdout contains `RESTORE_SMOKE_OK`; `alembic_version` printed; live `cip`
row counts unchanged (B4).

### (c) Data

```sql
-- On live cip (read-only) — B4 health check
SELECT current_database(), count(*) FROM dim_product;

-- On cip_alembic_smoke after restore only
SELECT current_database(), version_num FROM alembic_version;
```

### Superseded?

**Partially pending NS-2.** A5 landing on `/dashboard` will change when Brief replaces Control
tower (`IMPLEMENTATION_PLAN.md` NS-2). Until NS-2 VERIFY PASS, re-run gate **as written**.
After NS-2: update A5/A6 routes in gate doc, re-verify — do not SUPERSEDE until NS-2 ships.

---

## Unit 11 — Import parity (BACKLOG-044 / 027 / 026)

**Shipped:** 2026-08-12 · **PR #37** merge `4aa538a`  
**Message:** Unit 11 BACKLOG-026 + Unit 12 P6 export sheets (export belongs to Unit 12 verify)

### Contract / decisions

| Backlog | Scope |
|---------|--------|
| **BACKLOG-026** | Sole PM path: `product_master_workflow`; generic pipeline raises |
| **BACKLOG-027** | PM + `historical_lineup` → `CanonicalColumnMappingPanel` |
| **BACKLOG-044** | Shipment steward parity: `ShipmentImportJobResolutionSection` + shared engine |
| **S1–S14** | `docs/STEWARD_EXPERIENCE_CONTRACT.md` v1.6 — per importer with `needs_steward=yes` |

### Importers in scope (shipped tree)

| slug | Steward? | VERIFY focus |
|------|----------|--------------|
| `product_master` | no | Mapping panel + retired pipeline (026/027) |
| `historical_lineup` | no | `CanonicalColumnMappingPanel` (027) |
| `inbound_shipments` | **yes** | Full S1–S14 vs DSI reference |

Out of scope for Unit 11 debt: `cpor_*` wizards, `customer_sell_through` own surface, DSI (already PASS Unit A–B).

### (a) Automated

```powershell
cd apps/api
.\.venv\Scripts\activate
pytest tests/test_product_master_pipeline_retired.py -v
pytest tests/test_shipment_steward_duplicate_ops.py -v
pytest tests/test_shipment_bulk_steward_async.py -v
pytest tests/test_product_master_workflow.py -v --tb=short -q

cd ../..
$env:ESLINT_USE_FLAT_CONFIG="false"
pnpm --filter @cip/web exec vitest run `
  src/app/(app)/admin/imports/page.test.tsx `
  src/app/(app)/admin/shipment-evidence/ShipmentMappingStewardPanel.test.tsx `
  --reporter=dot
```

**Pass criteria:** retired path raises `BACKLOG-026`; shipment tests green. **Not sufficient for
steward VERIFY** — consultant must grade S-rows.

### (b) Browser (CONSULT enumerates S1–S14)

| Surface | Route | Minimum observations |
|---------|-------|---------------------|
| PM mapping | `/admin/imports` → product_master job | `CanonicalColumnMappingPanel` mounted (not bespoke table) |
| HL mapping | `/admin/imports` → historical_lineup | Same panel, `testIdPrefix` hl |
| Shipment steward | `/admin/imports` → inbound_shipments validate step | `ShipmentImportJobResolutionSection`: tabs, chips, drawer, plan toolbar, async apply + progress poll |

**Thin mount = STOP:** workspace without resolution section, or missing progress poll.

### (c) Data

Read-only unless exercising apply on **`cip_test`** with disposable import job.

### VERIFY procedure

1. Seed Opus from `verify_seed_template.md` with contract version **1.6**.
2. CONSULT pre-enumerates S-rows per importer (Warren waivers if any).
3. Output: S1–S14 table with `path:line` per row → `VERDICT: PASS` or `STOP`.

### Superseded?

**Not yet.** NS-7 Steward container will **re-open** parity (`IMPLEMENTATION_PLAN.md` NS-7).
Unit 11 debt clears on **current** routes; NS-7 is a separate VERIFY after redesign.

---

## Unit 12 — P6 polish (BACKLOG-026 regression + Settings export)

**Shipped:** 2026-08-12 (bundled in PR #37) · **BACKLOG-026** closed · Settings sheet titles

### Contract / decisions

| ID | Requirement |
|----|-------------|
| **BACKLOG-026** | No regression to retired PM pipeline |
| **P6** | Tenant config: lineup export sheet names + column map (`settings/page.tsx`) |

### (a) Automated

```powershell
cd apps/api
.\.venv\Scripts\activate
pytest tests/test_product_master_pipeline_retired.py `
  tests/test_commercial_tenant_profile_p6_persistence.py `
  tests/test_lineup_export_apply.py -v

cd ../..
$env:ESLINT_USE_FLAT_CONFIG="false"
pnpm test:web
```

Unit 12 VERIFY also requires **Unit 11 S-rows still PASS** (no regression).

### (b) Browser

| Step | Route | Observe |
|------|-------|---------|
| 1 | `/settings` → Lineup export section | Net requirement + draft lineup **sheet title** fields persist |
| 2 | Save custom titles | Reload page — titles retained |
| 3 | `/admin/imports` PM job | Still routes through Import Centre workflow (not dead generic pipeline) |

### (c) Data (read-only on `cip`)

```sql
SELECT current_database();
SELECT config_json->'lineup_export_sheets' AS sheets,
       config_json->'lineup_export_columns' AS cols
FROM commercial_tenant_profile
WHERE tenant_id = 'default';
```

### Superseded?

**No** — Settings export config survives North Star; only nav path may change.

---

## Unit 15B — B1 forecast compute-from-history

**Shipped:** 2026-08-14 · commits `62607c2`, `289f0d4` (15A+15B)  
**Not** the same as Unit 15A VERIFY PASS (cover weeks / Alembic `20260814_0016`).

### Contract / decisions

| ID | Requirement |
|----|-------------|
| **B1-07** | Forecast never merged into actuals (`docs/COMMERCIAL_SEMANTICS.md` §4.5) |
| **B1-04** | Compute-from-history CTA; paste/add remain overrides |
| Charter **B1** | `tenant_id` never NULL on forecast rows; velocity + analogue provenance |

### (a) Automated

```powershell
cd apps/api
.\.venv\Scripts\activate
pytest tests/test_demand_forecast_compute.py -v

cd ../..
$env:ESLINT_USE_FLAT_CONFIG="false"
pnpm --filter @cip/web exec vitest run src/app/(app)/forecasts/page.test.tsx
```

### (b) Browser (on **`cip_test`** — compute writes)

Point API at `cip_test` (both sync URLs). Start stack.

| Step | Route | Observe |
|------|-------|---------|
| 1 | `/forecasts` | Primary CTA `data-testid="forecast-compute-from-history"` |
| 2 | Click Compute → confirm | Success snackbar; grid refreshes |
| 3 | — | **Add override** / **Paste override** still present (override-only paths) |

### (c) Data (**`cip_test`** after compute)

```sql
SELECT current_database();  -- must be cip_test

SELECT count(*) AS null_tenant
FROM fact_demand_forecast
WHERE tenant_id IS NULL;

SELECT method, count(*),
       count(*) FILTER (WHERE provenance_json IS NOT NULL) AS with_provenance
FROM fact_demand_forecast
GROUP BY method;
```

**Pass criteria:** `null_tenant = 0`; `method` ∈ `{velocity, analogue, manual}`; compute did not
modify `fact_sales_sellout` / DSI tables (B1-07).

### Superseded?

**No** — `/forecasts` remains Demand Forecast owner until explicitly retired.

---

## Unit B4 (15C) — Promo planner

**Shipped:** 2026-08-14 · commit `a802627`  
**Decisions:** **D-051–D-056** · **BACKLOG-094** closed criteria

### Contract / decisions

| ID | Topic |
|----|--------|
| D-051 | Per-line `build_promo_plan_draft` JSON rows |
| D-052 | Client dirty-flag; refresh merges non-dirty only |
| D-053 | `create_case_from_promo_draft` accepts `lines[]`; `cost_source` manual vs intake_weighted |
| D-054 | Cover override session-only (no `commercial_customer_term` write) |
| D-055 | Editable vs display-only split |
| D-056 | Tenant profile `lineup_export_columns` for draft export |

### (a) Automated

```powershell
cd apps/api
.\.venv\Scripts\activate
pytest tests/test_promo_plan_builder.py -v

cd ../..
$env:ESLINT_USE_FLAT_CONFIG="false"
pnpm --filter @cip/web exec vitest run src/app/(app)/promotions/promoPlanDraftMerge.test.ts
```

Key tests: `test_build_promo_plan_draft_emits_per_line_mac_and_units`,
`test_create_case_from_promo_draft_carries_edits_and_skips_cover_persist`,
`promoPlanDraftMerge` dirty/refresh/reset cases.

### (b) Browser (on **`cip_test`** for create-case)

| Step | Route | Observe |
|------|-------|---------|
| 1 | `/promotions` | Seed case → **Build** grid with per-line MAC/units |
| 2 | Edit MAC + units → **Refresh** | Dirty cells unchanged; clean cells update |
| 3 | **Reset** on dirty MAC | Restores suggested value |
| 4 | MAC popover | Bucket A/B legs display-only (D-055) |
| 5 | **Create case** | New case lines carry `manual` vs `intake_weighted` cost_source |
| 6 | Export draft lineup | Column headers match tenant `lineup_export_columns` (D-056) |

### (c) Data

```sql
-- Read-only: tenant export config on cip
SELECT config_json->'lineup_export_columns'
FROM commercial_tenant_profile WHERE tenant_id = 'default';

-- After create on cip_test:
SELECT cost_source, cost_basis, cost_evidence_json IS NOT NULL
FROM commercial_lineup_line
WHERE case_id = <new_case_id>
LIMIT 10;
```

### Superseded?

**Pending NS-6.** `IMPLEMENTATION_PLAN.md` NS-6 retires `/promotions` → Response container.
When NS-6 ships without VERIFY, close B4 debt as **SUPERSEDED** only after NS-6 VERIFY includes
B4 criteria re-run (`IMPLEMENTATION_PLAN.md` NS-6 VERIFY). Until then, verify on `/promotions`.

**Note:** `BACKLOG-094` claims "Unit 15C Opus VERDICT: PASS" — charter amendment 7 still lists B4
as debt because archived VERIFY was unavailable/incomplete. Re-verify required.

---

## North Star supersession summary

| Unit | Status now | When to mark SUPERSEDED |
|------|------------|-------------------------|
| 6f | **Active** on `/admin/po-management` | If attribution moves and old review UI removed without NS VERIFY |
| 7 | **Active** on `/shipping` | NS-3 Inbound lens PASS replaces strip check |
| 8 | **Active**; A5 uses `/dashboard` | NS-2 Brief PASS → rewrite A5/A6, then SUPERSEDE old landing checks |
| 11 | **Active** on `/admin/imports` | NS-7 Steward container PASS (may re-verify same S-rows) |
| 12 | **Active** on `/settings` | Unlikely superseded |
| 15B | **Active** on `/forecasts` | No NS retirement planned |
| B4 | **Active** on `/promotions` | NS-6 Response PASS with B4 criteria re-run |

**Do not SUPERSEDE** because North Star is **designed** — only when replacement surface is
**VERIFY-passed** or evidence is **provably gone** (route 404, feature removed).

---

## Consultant invoke (when executing VERIFY — not during discovery)

```powershell
# Example — fill .tmp/unit11_verify_opus_seed.md from verify_seed_template.md first
Get-Content .tmp\unit11_verify_opus_seed.md -Raw |
  claude -p --model opus --output-format text --dangerously-skip-permissions |
  Out-File .tmp\unit11_verify_opus_response.md -Encoding utf8
```

Final line of response must be exactly `VERDICT: PASS` or `VERDICT: STOP`.

---

## Question queue (discovery)

1. CONTEXT `2026-08-08 VERIFY PASS 6f→B4` contradicts amendment 7 register — treat register as authoritative.
2. `test_d040_*` glob in IMPLEMENTATION_PLAN — stale; use `test_lineup_distributor_attribution.py`.
3. Case 1016 — confirm still on Warren's `cip` before Session D browser write plan.
