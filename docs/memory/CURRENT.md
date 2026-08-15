# CURRENT state

**Last updated:** 2026-08-15 (docs pin from git + code; D-022 verified in tree)

**Branch:** `main`

**Last content pin:** `602d926` — docs from git + D-022 code check (confirm HEAD with `git rev-parse`; do not treat a hash in this file as HEAD)

**Alembic (code):** `20260814_0016` (`20260814_0016_customer_term_cover_weeks.py`)

**Alembic on cip:** `20260814_0016` (head) — re-read 2026-08-15; do not upgrade unless approved

## On main (git)

Through `d80d13c`: Units 8 / 11 / 12, leftover-close / P2 local, P5 residual, Units 13–15. Hosting stays local (Q-003). P6 waits for a second company.

## D-022 / BACKLOG-082 (read in tree 2026-08-15)

**Done in code — not a next unit.** Do not re-implement from ROADMAP/BACKLOG “Done” text.

- Aliases + denylist live in `template_definitions.py` `distributor_inventory` `expected_columns._policy`
- `build_initial_dsi_field_mapping` overlays confirmed steward memory **last** (memory > alias > heuristic)
- `dsi_mapping_workflow.py` has no tenant/vendor header string literals (`Dealer Name`, `ASUS Part No.`, etc.)
- Residual: generic substring heuristics (`dealer`+`group`, `customer`+`name`) as fallback after policy

## Last recorded test snapshot (2026-08-14 — not re-run 2026-08-15)

| Gate | Result |
|---|---|
| Lint (`ESLINT_USE_FLAT_CONFIG=false`) | **0 errors**, 51 hook warnings |
| Web Vitest | **510 passed**; 1 timeout flake (`distributors/page.test.tsx` drawer) — **6/6 on re-run** |
| API pytest (`ALLOW_TESTS_ON_DEV_DB=1`) | **2005 passed**, 4 skipped, **16 failed**, **2 errors** (~18 min) |
| API `/health/ready` | `cip` ok (after pytest) |
| Browser | Control tower, Forecasts, Promotions, Dashboards, Listing Capture, CPOR Cases, Channel Ops, Settings — headings loaded as Local Admin |

Do not treat the API suite as green. Next chat must **re-run** gates and classify from that output — do not copy this paragraph as a work order.

## Next

Finish remaining ROADMAP + outstanding leftover-close items + BACKLOG entries whose TRIGGER has fired. Do **not** start module deepening until Warren asks.

1. P0 hygiene — live lint / `tsc` / web tests / API tests; fix real contract/type bugs so “CI is a gate” is true. Do not mass-fix hook warnings. Do not alembic-upgrade without approval.
2. BACKLOG-079 chrome — PageHeader / crumbs on owning routes (`COMMERCIAL_SEMANTICS`). Fold-only; D-021 holds.
3. Continue ROADMAP still-open in phase order (P3-1 CONSULT, P3-5 beat soak, P4 Amazon FLAG / Game W27, Lane X 076/089/085). Report and skip only what is blocked on Warren (Q-003 hosting, P6 second company, P5 intel v1 ≥2 weeks obs, BACKLOG-098 real Monday 07:00).
4. Burn BACKLOG with fired TRIGGER as you pass that phase. Import header vocabulary (082) is already in the tree.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
