# CURRENT state

**Last updated:** 2026-08-14 (merged leftover-close; full audit + test pass)

**Branch:** `main` @ `8d4c8da` (in sync with `origin/main`)

**Alembic on cip:** `20260814_0016` (head — do not upgrade unless approved)

## On main

Units 8 / 11 / 12, P2 local, P5 residual, 13–15 are on `main`. Hosting stays local (Q-003). P6 waits for a second company.

## Full test (2026-08-14, this machine)

| Gate | Result |
|---|---|
| Lint (`ESLINT_USE_FLAT_CONFIG=false`) | **0 errors**, 51 hook warnings |
| Web Vitest | **510 passed**; 1 timeout flake (`distributors/page.test.tsx` drawer) — **6/6 on re-run** |
| API pytest (`ALLOW_TESTS_ON_DEV_DB=1`) | **2005 passed**, 4 skipped, **16 failed**, **2 errors** (~18 min) |
| `alembic current` | `20260814_0016 (head)` on `cip` |
| API `/health/ready` | `cip` ok (after pytest) |
| Browser | Control tower, Forecasts, Promotions, Dashboards, Listing Capture, CPOR Cases, Channel Ops, Settings — headings loaded as Local Admin |

Pytest failures are **not** from the leftover-close docs merge. Two are the ALLOW-flag guards (they assert the flag is unset). Two errors: `cip_bulk_smoke` alembic still `20260702_0066` (test expected `20260812_0014`). Rest: DSI/live-schema/integrity/auth 401 on mocked CPOR create. Do not treat as a green suite.

`verify-gate --skip-tests`: tsc compare vs empty worktree is noisy. Live `tsc --noEmit` has pre-existing errors (mostly tests; prod: shipment steward types, CPOR column-picker `id`, lineup `data-testid` on file input).

## Next (new units)

- **P3-1** tenant-defined metrics (CONSULT first)
- **P5 intelligence v1** after ≥2 weeks observations
- **P6** second tenant
- Optional hygiene: pytest/tsc debt above — new chat, not this pin

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
