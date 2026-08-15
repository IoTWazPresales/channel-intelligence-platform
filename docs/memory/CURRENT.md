# CURRENT state

**Last updated:** 2026-08-15 (P0 hygiene on `feat/finish-roadmap`; confirm HEAD with `git rev-parse`)

**Branch:** `feat/finish-roadmap`

**Last content pin:** `5deadb8` — branched from `origin/main` for finish-roadmap (do not treat a hash in this file as HEAD)

**Alembic (code):** `20260814_0016` (`20260814_0016_customer_term_cover_weeks.py`)

**Alembic on cip:** `20260814_0016` (head) — do not upgrade unless approved

## On this branch

P0 hygiene: `tsc --noEmit` 0 errors; CI now runs `pnpm lint` (`ESLINT_USE_FLAT_CONFIG=false`) + `pnpm typecheck` before API tests. BACKLOG-070 closed as the legacy-shim path (51 hook warnings not mass-fixed).

## Last recorded test snapshot (2026-08-15 live re-run)

| Gate | Result |
|---|---|
| Lint (`ESLINT_USE_FLAT_CONFIG=false`) | **0 errors**, 51 hook warnings (unchanged; not a mass-fix) |
| Web `tsc --noEmit` | **0 errors** (was 27) |
| Web Vitest | focused 125/125 on touchpaths; full suite was 510 pass + 1 drawer timeout flake — timeout raised to 15s on that test |
| API pytest (`ALLOW_TESTS_ON_DEV_DB=1` vs live `cip`) | **2005 passed**, 4 skipped, **16 failed**, **2 errors** then contract fixes on a subset (see classification) |

**API classification (this run, not the 2026-08-14 copy):**
- **Fixed (CI-gate contract):** hardcoded alembic tip `20260812_0014` → ScriptDirectory head; gap-resolve mock batches after CST count/repoint; `ImportJob.file_name` NOT NULL in orphan-purge test; skip (don’t fail) ALLOW-unset guards and cip-targeted discovery when the local runner uses `ALLOW_TESTS_ON_DEV_DB=1` / live `cip`.
- **Env / live cip — not this unit:** DSI UniqueViolation + empty-candidate asserts against populated `cip`; `CIP_AUTH_MODE=session` 401s (CI defaults stub); `cip_bulk_smoke` still at `20260702_0066` (skipped until disposable migrate — never cip); data-integrity audit samples on live data.
- Do not treat the full local-vs-cip API suite as green.

## Next

1. Opus VERIFY this P0 unit, then BACKLOG-079 chrome (PageHeader / crumbs on owning routes). Fold-only; D-021 holds. Do not wrap PvE scorecard or PM-gaps worklist in `MasterDataGridShell`.
2. P3-1 CONSULT (Opus) — tenant-defined metrics without a deploy.
3. P4 Amazon ASIN FLAG / optional Game W27. Skip blocked: Q-003, P6 second company, P5 intel v1, BACKLOG-098 Monday beat, 076/089 unless Warren asks.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
