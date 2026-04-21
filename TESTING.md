# Testing

## Commands (repo root)

| Script | What runs |
|--------|-----------|
| `pnpm test` | Python API tests + Vitest (web unit/integration) |
| `pnpm test:api` | `pytest` in `apps/api/tests` (no database required) |
| `pnpm test:web` | Vitest in `apps/web` |
| `pnpm test:e2e` | Playwright against Next dev server (starts server automatically) |
| `pnpm test:all` | `pnpm test` then E2E |
| `pnpm verify` | `pnpm test` then `pnpm build` |

First-time E2E locally: `pnpm --filter @cip/web exec playwright install chromium`.

API tests use `httpx` (via Starlette’s `TestClient`). After pulling, run `pip install -r apps/api/requirements.txt` in your API virtualenv. `pnpm test:api` prefers `apps/api/.venv` when present (`scripts/run-pytest.cjs`).

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs API tests, web tests, Playwright, and `pnpm build` on push/PR to `main` or `master`.

## Architecture notes

- **API**: `TestClient` tests hit the ASGI app in-process; they do **not** start Postgres. Database-backed scenarios should use a dedicated fixture + marker (e.g. `@pytest.mark.integration_db`) once a test database is wired in.
- **Web**: `vitest.setup.ts` mocks `next/link` and `ResizeObserver` globally so MUI + Next components render under Vitest.
- **E2E**: Specs mock `fetch` to the API via Playwright `page.route` on `**/api/v1/...` so the UI can be exercised without a live API. Add routes when new pages call additional endpoints during load.

After substantive changes, run `pnpm test:all` (or rely on CI). Clearing `.next` or restarting dev servers is only needed when debugging stale bundles, not after every green test run.
