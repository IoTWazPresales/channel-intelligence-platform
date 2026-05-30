# Commercial Planner — Gap Analysis & Risk Register

**Branch:** `cursor/commercial-planner-program-84b1`  
**Date:** 2026-05-30  
**Scope:** Program phase 1 delivery + post-implementation review (testing, risks, gaps vs approved plan)

---

## Executive summary

Phase 1 delivers a **shippable foundation**: feature flag, preview/apply lineup import, deterministic product rankings, intelligent add UI, and suggestion precedence for current lineup cases. The module remains **operationally usable** but **not parity** with DSI/Product Master import maturity, dashboard integration, or full multi-signal intelligence.

| Area | Status | Gap severity |
|------|--------|--------------|
| Plan builder (lines, recalc, economics) | Working (pre-existing) | Low — monolithic UI |
| Current lineup import | Preview/apply on retry + create-case flows | Medium — no Celery for large files |
| Intelligence rankings | v1 deterministic + SRP hints | Medium — 500-SKU cap, sparse data |
| Steward / mapping queue | Case-scoped resolution only | High — no global steward bridge |
| Feature flag / removability | API + nav | Low |
| Dashboard / analytics | Not integrated | Medium |
| Security / RBAC | Stub auth | High (platform-wide) |

---

## Module-by-module review

### 1. API router (`commercial_planner.py` ~3.2k lines)

**What works**

- Full CRUD for plans, lines, terms, assumptions, suggestions, readiness
- Lineup cases, parse-preview, parse-apply, legacy parse-upload
- Intelligence `product-rankings` endpoint
- Suggestions prefer `CommercialLineupCase` lines when plan-linked
- `data_unavailable`-style patterns on optional facts (where implemented)

**Risks**

| Risk | Impact | Mitigation |
|------|--------|------------|
| Monolithic file | Hard to review, merge conflicts | Split by domain (plans, lineup, intelligence) — phase 2 |
| No RBAC | Any authenticated stub user can mutate plans | Platform auth workstream |
| `parse-apply` re-uploads file | Large files block request thread | Celery + activity feed (helper exists, task not wired) |
| Duplicate parse paths | `parse-upload` bypasses `confirm=true` | Deprecate after UI fully on preview/apply |

**Gaps**

- No `parse-apply-async` / 202 response for files >500 rows or >512KB
- No mapping-queue export to central steward inbox
- Budget / allocation facts not exposed on rankings endpoint

---

### 2. Services (`apps/api/app/services/commercial_planner/`)

| Module | Role | Status | Risk |
|--------|------|--------|------|
| `calculator.py` | Line economics | Stable | DAP vs controlled cost confusion in ops |
| `economics_trust.py` | Trust tiers | Stable | Rankings cap score when `blocked` |
| `suggestions.py` | Qty/price suggestions | Stable | Historical lineup qty filtered by `customer_id` on header — misses null-customer headers |
| `lineup_case_parser.py` | CSV/XLSX → lines | Improved | `can_apply` now requires ≥1 resolved product; apply still writes unresolved rows as token-only lines |
| `lineup_entity_resolution.py` | Token → dim | Case-scoped | No corroboration pipeline like DSI |
| `lineup_header_mapping.py` | Column map | Stable | Promo vs MSRP alias collisions documented in historical import |
| `intelligence/product_rankings.py` | Opportunity scores | v1+ | Scans first **500** `DimProduct` by SKU order; customer-scoped net price + lineup MSRP + promo flag |
| `lineup_parse_worker.py` | Celery sync wrapper | **Not wired** | Ready for task registration |
| `sku_economics_import.py` | SKU assumptions import | Pre-existing | Separate from lineup upload |

**Gaps vs approved intelligence plan**

- No persisted `recommendation` table / audit trail for scores
- No customer-scoped `FactForecast` (product-level only)
- No allocation / buy-plan / budget signals in score
- No LLM layer (correctly deferred)

---

### 3. Data model (no new migrations in program branch)

**Three lineup concepts — do not merge casually**

1. `CommercialPlan` / `CommercialPlanLine` — plan builder economics  
2. `CommercialLineupCase` / `CommercialLineupLine` — working lineup uploads  
3. `HistoricalLineupImport*` — admin template `historical_lineup`  
4. `FactLineupPlanItem` — separate `/lineup` assortment page  

**Risks**

- Linking plan ↔ case is manual; orphaned cases possible
- `dap_evidence_local` on lineup lines is evidence only — training/docs must reinforce

---

### 4. Web — Commercial Planner page (`page.tsx` ~3.6k lines)

**What works**

- Plan grid, recalculate, suggestions drawer, lineup evidence
- Intelligent add dialog (rankings → bulk line create with suggested SRP/units)
- Feature flag hides nav when disabled

**Risks**

| Risk | Notes |
|------|-------|
| Monolithic page | Same merge/review cost as API monolith |
| Intelligent add creates lines with default promo_mix 0.5 | User must recalculate for trust |
| Grid edit + recalc not automatic after intelligent add | By design; document in UI |

**Gaps**

- No dashboard widgets summarizing plan readiness / trust distribution
- No dedicated “historical vs current” toggle on main page (cases are “current”; historical via imports module)

---

### 5. Web — Current lineup (`CurrentLineupSection.tsx` ~2.7k lines)

**What works**

- Case workbench, entity resolution (open channel, unassigned distributor)
- Retry parse: preview → apply
- Create case dialog: create → preview → apply (phase 1 completion)

**Risks**

- Workbench column prefs in localStorage — version drift across deploys
- Entity resolution is not full steward queue — ambiguous tokens stay on case

---

### 6. Feature flags

| Env | Layer | Default |
|-----|-------|---------|
| `CIP_COMMERCIAL_PLANNER_ENABLED` | API router registration + endpoint guard | on |
| `NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED` | Nav | on |

**Gap:** Disabling API but leaving web deep-links/bookmarks can 404 — need friendly empty state on direct URL (minor).

---

### 7. Background tasks / Celery

**Gap:** Commercial planner has **no** registered Celery task. PM/DSI use `apps/api/app/worker/tasks.py` + activity feed metadata.

`lineup_parse_worker.py` provides `run_lineup_case_parse_sync` and thresholds (`500` rows, `512KB`) but is not called from API or worker.

**Risk:** Parsing 10k-row XLSX on API worker blocks Uvicorn thread; timeout on reverse proxy.

---

## Testing performed (2026-05-30)

| Suite | Command | Result |
|-------|---------|--------|
| Intelligence + lineup preview + services | `pytest tests/test_commercial_planner_intelligence.py tests/test_lineup_parse_preview.py tests/test_commercial_planner_services.py` | **13 passed** |
| Commercial planner API (no DB) | `pytest tests/test_commercial_planner_api.py` | **74 passed** |
| Reference bootstrap | `test_commercial_planner_reference_bootstrap.py` | **1 failed** — Postgres not running on agent host (`Connection refused`) |
| Web CP page | `vitest commercial-planner/page.test.tsx` | **83 passed** |
| Web CurrentLineupSection | `vitest CurrentLineupSection.test.tsx` | **7 passed** |
| Web EntitySearchAutocomplete | **1 passed** |

**Not run (environment):** Full API suite against live `cip` DB; E2E browser smoke on Docker stack.

**Recommended manual smoke (local/Docker)**

1. Create plan → intelligent add → recalculate → verify economics trust  
2. Create lineup case → preview file with mixed resolved/unresolved SKUs → apply  
3. Toggle `CIP_COMMERCIAL_PLANNER_ENABLED=false` → API 404, nav hidden  
4. Suggestions on plan with linked lineup case → verify `current_lineup_case` in `_meta`

---

## Phase delivery vs approved program

| Phase | Planned | Delivered | Remaining |
|-------|---------|-----------|-----------|
| 1a Feature flag | Yes | Yes | URL empty state |
| 1b Preview/apply lineup | Yes | Yes (retry + create-case) | Celery async |
| 1c Intelligence rankings | Yes | Yes (+ SRP, promo signal) | Customer forecast, budget, allocation |
| 1d Intelligent add UI | Yes | Yes (+ suggested SRP) | Inline edit before add |
| 1e Suggestions precedence | Yes | Yes | — |
| 2 Mapping queue bridge | Planned | **No** | Export case tokens to steward |
| 2 Router split | Optional | **No** | Maintainability |
| 3 Dashboard widgets | Optional | **No** | Readiness summary on `/dashboard` |
| 4 Persisted recommendations | Optional | **No** | Audit + replay |

---

## Priority risk register

| ID | Risk | Likelihood | Impact | Owner action |
|----|------|------------|--------|--------------|
| R1 | Rankings omit products outside first 500 SKUs | High in large catalogues | Wrong “best product” list | Paginate or filter by category/customer sellout first |
| R2 | Empty rankings for customers with no sellout/history | Medium | User thinks feature broken | UI empty state + explain signals needed |
| R3 | Historical lineup qty misses headers with `customer_id` null | Medium | Under-weight historical signal | Join on dealer token or plan customer |
| R4 | Large file parse blocks API | Medium | Timeout 500 | Wire Celery + activity feed |
| R5 | `target_srp_local: 0` if API omits field | Low (fixed) | Bad economics until recalc | Fallback 1000 in UI |
| R6 | No RBAC on CP endpoints | High (org) | Data leak / misuse | Platform security |
| R7 | Apply writes unresolved product rows | Medium | Dirty case data | Block apply when `resolved_products == 0` (preview); consider hard block on apply |
| R8 | Monolith regression surface | Ongoing | Slow delivery | Incremental router extraction |

---

## Removability assessment

**Can disable Commercial Planner without breaking core platform?**

- Set both feature flags false → nav hidden, API 404 on `/commercial-planner/*`
- DB tables remain (no migration rollback required)
- Historical lineup imports and `/lineup` page are **separate** — unaffected
- Plans already in DB remain; re-enable shows data

**Verdict:** Removable at runtime; schema is additive.

---

## Recommended next steps (ordered)

1. **Celery:** Register `commercial_planner.parse_lineup_case` task; `POST parse-apply` returns 202 when over threshold; activity bell metadata.  
2. **Rankings:** Pre-filter catalogue to customer sellout ∪ lineup ∪ plan SKUs before 500-cap scan.  
3. **Apply guard:** Reject apply when preview `resolved_products == 0`.  
4. **Steward bridge:** Read-only export of unresolved tokens from case → existing steward panels (no auto-create).  
5. **Router split:** `commercial_planner_plans.py`, `commercial_planner_lineup.py`, `commercial_planner_intelligence.py`.  
6. **Dashboard:** Plan readiness chip on overview (reuse `GET …/readiness`).

---

## References

- `docs/COMMERCIAL_PLANNER_PROGRAM.md` — delivery log  
- `docs/COMMERCIAL_PLANNER_AUDIT.md` — pre-program audit (if present)  
- `.cursor/rules/Supply-Chain-Intelligence-Project-Rules.mdc` — DSI governance (do not weaken for CP shortcuts)
