# N-0026 implementer evidence — propose a promotion plan from customer and period

**Run:** `NS14_PROMO_PLAN_20260914` · **Actor:** `gov-001` · **2026-09-15**
**Do not complete.** Independent GOV-008 is a later session, different run and actor.
**Playwright MCP only.** No `browser_cdp`. No writes to `cip` (compose GET only; Create draft not clicked).

Cites **D-0008** (accepted commercial amendment of **N-0013**). N-0013 not reopened. Competition is product-vs-SKU. Other customers are not proposal analogues.

Reconcile: `.eif/audit/NS14_PROMO_PLAN_20260914/RECONCILE.md`. `current_database()=cip` printed first on every SQL probe this session.

---

## Charter (re-read from ledger before close)

N-0026: compose and create a draft `cpor_case` / `cpor_case_line` from `customer_id` + `period_label` without a seed case id. Primary product set: active `commercial_lineup_line`. Fallback: that customer’s historical `cpor_case_line` only. Origin `proposed_by_cip`. Headline strip: no 257% ratio. Start work verb **Create promotion plan** → `/promotions?propose=1`.

---

## Playwright 1280×800 (VERIFIED)

API was down (`API upstream unreachable` on `/login`). Restarted `pnpm dev:api`. Health `{"status":"ok","service":"cip-api"}`.

| Step | Result |
|---|---|
| Sign in `admin@local` | Landed `/brief` |
| Start work **Create promotion plan** | href `/promotions?propose=1`. Clicked. Dialog **Create promotion plan** opened |
| Customer **CUST-000011 — Computer Mania** (`dim_customer.id=18`, `current_database()=cip`) · period **2026Q2** | Propose from evidence enabled |
| Propose from evidence | **Lines: 40 · source: commercial_lineup_line · same-customer comparables: 10** |
| Create draft CPOR case | Enabled after compose. **Not clicked** (would write `cip`) |
| Headline strip | Drafts 0 · Ended 74 · Settled 210 · Planned reserve **$253k** · Actual support **$650k**. Captions: “Not a percent” / “Do not divide these two figures”. **No 257%** |

Empty **New plan** remains on the planner toolbar.

---

## Product land

| Path | Role |
|---|---|
| `apps/api/app/services/cpor/promo_plan_builder.py` | Compose from customer+period; `build_same_customer_comparables`; lineup then same-customer history |
| `apps/api/app/api/v1/endpoints/cpor_cases.py` | Draft GET without `seed_case_id`; create `origin=proposed_by_cip` |
| `apps/web/.../PromoPlanBuilderPanel.tsx` | Customer + period propose; seed id optional |
| `apps/web/.../PromotionPlannerSurface.tsx` | `?propose=1` dialog; strip figures; **Create promotion plan** |
| `apps/web/src/features/overview/startWork.ts` | Verb `create-promo-plan` admin+planner |

Tests: `pytest tests/test_promo_plan_builder.py` **7 passed** (prior session). vitest startWork + PromotionPlannerSurface **6 passed** (prior session). Duplicate “reserved {status}” copy on the compose summary removed this close (NUMBER RULE: status is not money).

---

## UNCOVERED (not substituted)

| Finding | Backlog |
|---|---|
| `fact_competitor_price` empty; listing join sparse (3 customers) | BACKLOG-183 |
| `weeks_of_cover_observation` not used as target cover | BACKLOG-184 |
| Uplift / claim evidence 0 | BACKLOG-185 |
| A2-05 seed-view still ranks other customers | BACKLOG-186 |

---

## Untouched

D-0002, N-0006, N-0013, D-0010, BACKLOG-181, Movement/Execution relocated workspaces, N-0025 remediation. No GOV-008 on this node.
