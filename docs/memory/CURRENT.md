# CURRENT state

**Last updated:** 2026-08-16 (P3-1 U3 VERIFY PASS on `feat/finish-roadmap`; confirm HEAD with `git rev-parse`)

**Branch:** `feat/finish-roadmap`

**Last content pin:** `5deadb8` — branched from `origin/main` for finish-roadmap (do not treat a hash in this file as HEAD)

**Alembic (code):** `20260814_0016` (`20260814_0016_customer_term_cover_weeks.py`)

**Alembic on cip:** `20260814_0016` (head) — do not upgrade unless approved

## On this branch

- P0 hygiene (`4effbb5`): `tsc --noEmit` 0; CI lint+typecheck; BACKLOG-070 legacy shim.
- BACKLOG-079 chrome: owning-route PageHeader crumbs/titles from `navPageChrome` (`navConfig`). Did not wrap PvE scorecard or PM-gaps worklist in `MasterDataGridShell`.
- BACKLOG-085 fold: client AG Grid pagination on CST steward / PO gap / PM-gaps worklist.
- **P3-1 U1:** tenant metric overlay is `semantic_overlay` on `tenant_profiles/{id}.json`. Governed merge (relabel / hide / restrict grains only). Blind `{**base, **overlay}` removed. No migration.
- **P3-1 U2:** tenant-composed metrics (intra-family ratio + grain-restricted alias) evaluated via `dispatch_handler` on existing inputs. No new SQL/handlers.
- **P3-1 U3:** admin Settings overlay editor (`GET`/`PUT /semantics/overlay`). Relabel / hide / grain-restrict; composed builder is ratio|alias same-family only. Steward cannot PUT. Default-tenant browser E2E recorded in `.tmp/p3_1_u3_browser_smoke.md`. Overlay was reverted after smoke so `default` labels stay platform.

## Last recorded test snapshot

P0 live gates 2026-08-15: lint 0 errors (51 hook warnings); tsc 0; API vs live cip not green (env/data).  
079 focused web vitest 2026-08-15: **151 passed**.  
P3-1 U1 focused API 2026-08-16: overlay + semantic layer + tenant-profile + query/dashboard catalog tests **passed**.  
P3-1 U2 focused API 2026-08-16: `test_query_compose` + overlay/semantic/query/dashboard regressions **passed**.  
P3-1 U3 2026-08-16: `test_semantic_overlay_api` + compose + governed overlay **23 passed**; Settings vitest **4 passed**. Browser smoke: Settings save → dashboards palette + report builder `fill_vs_hit` **126.2%** (26Q2); PvE fill-rate headline still **13.2%** (formula locked). No alembic upgrade.

## Next

1. P4 Amazon ASIN FLAG / optional Game W27. Skip blocked: Q-003, P6 second company, P5 intel v1, BACKLOG-098 Monday beat, 076/089 unless Warren asks.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
