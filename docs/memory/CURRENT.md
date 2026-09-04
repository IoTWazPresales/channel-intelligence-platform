# CURRENT state

**Last updated:** 2026-09-04 (Promotions & Funding production migration)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** `4fd05c4`

**Alembic (code):** `20260902_0020` (N-0006 FX enforcement)

**Alembic on cip:** `20260902_0020`

## On feat/ns-2-brief-nav-collapse

- **Product (this session):** Promotions & Funding design-lab experience migrated onto production routes against real `cpor_case` data. Shared chrome in `features/workbench-ui/` (lab primitives re-export). Planner `/promotions`, case book, claims leaf, payments, templates, terms, budgets, settlement desk. List `GET /cpor/cases` returns line-sum `ttl_support_zar` + tenant `status_counts` (I1/I4). No fixture writes on production paths.
- **I1–I5:** I1/I3/I4/I5 closed on production funding (browser: C26760971 list and workspace both R1.6m / 18 lines / 420 units; rails Draft 3 · Ended 75 · Settled 210 on planner and case book; no N-0010 copy). **I2** is lab Market fixture/copy only — production `/competition` has no factor panel. Do not invent one in funding.
- **Programme:** PRG-20260831T145514 rev **295**; `frontier` is **only N-0006**. Do not start N-0006. Do not reopen N-0013, D-0008, D-0009. D-0009 ledger (`.eif/`) may still be uncommitted — leave it.
- **D-0009 accepted:** Actions fold into Attention; N-0010 is not a work container. **D-0002** remains the open decision.
- **Tests:** `@cip/web` **111 / 589 passed** (was 107 / 583). API `test_cpor_cases_api.py` 9 passed with `ALLOW_TESTS_ON_DEV_DB=1` (mocked; no cip writes).
- **Ops required:** `pnpm dev:api-web` — local API/web were down after the restart job exited.

**Programme frontier:** N-0006 only. Do not manufacture a path.

**Design language:** FROZEN v1.1 is **demoted**. Production funding follows the implemented design-lab React, not CIP_DESIGN_LANGUAGE.md grammar containers.

**Findings (not invented):** no AM vs Ken permission split on CPOR API; listing/competitor/cover not joined on `cpor_case_line`; B4 propose still needs a seed case id; no `proposed→draft`; template-driven export not built.

**Deferred:** BACKLOG-164 now I2-only (Market mapping). Duplicate Price History / product-scoped listing headlines are Market, not this slice.

**Env:** local Windows. Web `:3000` + API `:8001`.
