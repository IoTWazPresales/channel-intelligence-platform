# CURRENT state

**Last updated:** 2026-08-16 (P3-1 U1 overlay on `feat/finish-roadmap`; confirm HEAD with `git rev-parse`)

**Branch:** `feat/finish-roadmap`

**Last content pin:** `5deadb8` — branched from `origin/main` for finish-roadmap (do not treat a hash in this file as HEAD)

**Alembic (code):** `20260814_0016` (`20260814_0016_customer_term_cover_weeks.py`)

**Alembic on cip:** `20260814_0016` (head) — do not upgrade unless approved

## On this branch

- P0 hygiene (`4effbb5`): `tsc --noEmit` 0; CI lint+typecheck; BACKLOG-070 legacy shim.
- BACKLOG-079 chrome: owning-route PageHeader crumbs/titles from `navPageChrome` (`navConfig`). Did not wrap PvE scorecard or PM-gaps worklist in `MasterDataGridShell`.
- BACKLOG-085 fold: client AG Grid pagination on CST steward / PO gap / PM-gaps worklist.
- **P3-1 U1:** tenant metric overlay is `semantic_overlay` on `tenant_profiles/{id}.json`. Governed merge (relabel / hide / restrict grains only). Blind `{**base, **overlay}` removed. No migration. Composition (U2) and Settings editor (U3) not in this unit.

## Last recorded test snapshot

P0 live gates 2026-08-15: lint 0 errors (51 hook warnings); tsc 0; API vs live cip not green (env/data).  
079 focused web vitest 2026-08-15: **151 passed**.  
P3-1 U1 focused API 2026-08-16: overlay + semantic layer + tenant-profile + query/dashboard catalog tests **passed** (32 + 39 in two runs; overlap). No alembic upgrade. No browser Settings proof (U3).

## Next

1. Opus VERIFY this P3-1 U1 unit.
2. P3-1 U2 — composition evaluator (intra-family ratio + grain-restricted alias). Do not start until `VERDICT: PASS`.
3. P3-1 U3 — admin Settings editor + default-tenant E2E. Then P4 Amazon ASIN FLAG / optional Game W27. Skip blocked: Q-003, P6 second company, P5 intel v1, BACKLOG-098 Monday beat, 076/089 unless Warren asks.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
