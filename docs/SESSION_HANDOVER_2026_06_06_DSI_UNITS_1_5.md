# Session handover — DSI Units 1–5 (Jun 6, 2026)

**Branch:** `fix/shipment-steward-performance` (not merged to `main`)  
**Active DB:** Supabase EU (`postgres` via pooler) — Warren product decision to stay remote for realistic testing.

---

## What shipped this session

| Unit | Backlog | Summary | Acceptance |
|------|---------|---------|------------|
| **1** | BACKLOG-030 | DSI validate throughput: 2k bulk staging chunks, commit every 50k rows, cache-backed resolution, SQL month filter on corroboration | **Accepted** — job #43 re-validate: 168,839 staging lines, 5,425 candidates, ~53 min (~53 rows/s). 62 rows/s gate waived. |
| **2** | BACKLOG-005 | DSI column mapping → shared `CanonicalColumnMappingPanel` | Code complete; browser smoke recommended on `/admin/imports` DSI path. |
| **3** | BACKLOG-023 | DSI progress terminal label: "Apply complete" when `stage=loaded` | Tests pass (`test_dsi_job_progress.py`). |
| **4** | BACKLOG-024 | AI resolver on `distributor_master` + `historical_lineup` | Tests pass; in-memory distributor candidates (no extra DB round-trip). |
| **5** | BACKLOG-012 | AG Grid mock `getDisplayedRowCount` for products suite | 15/15 vitest pass. |

**Docs:** BACKLOG-015 marked done (cancel revokes all slot tasks). BACKLOG-010 N/A (destructive PAV drop needs explicit approval). **BACKLOG-031** added — admin data health dashboard (recommended next ops visibility work, not pgAdmin).

---

## Critical operator truth: validate ≠ apply

| Layer | Table / UI | Job #43 state |
|-------|------------|---------------|
| Validate output | `import_distributor_si_staging_line` (~222k total on Supabase) | 168,839 lines for job #43 |
| Steward candidates | `import_entity_mapping_candidate` | 5,425 tokens |
| **Facts (sell-out)** | `fact_sales_sellout` → Channel Operations Sell-out | **0 rows** until apply completes |

Re-validating does **not** populate sell-out facts. Apply (`post_dsi_apply` / async worker) is a separate step after steward resolution.

---

## Recommended next steps (priority order)

1. **Steward job #43 candidates** (5,425) — bulk/auto where confidence allows; historical mode may auto-apply ≥0.55 per DSI rules.
2. **DSI apply on job #43** — async apply; watch BACKLOG-028 (pooler SSL on long apply). Expect progress via `dsiApplyAsync` poll.
3. **BACKLOG-031 — Data health dashboard** — read-only table counts + import job evidence summary (better than embedding pgAdmin). Use Supabase dashboard for raw SQL/DDL when needed.
4. **Phase 2 remote reliability** — BACKLOG-028, -002, -003 if apply still fails on pooler.

**Not recommended now:** raw seed wipe on Supabase; `alembic upgrade` without approval; merging to `main` without explicit promotion.

---

## Cleanup on Supabase

- Use existing **import job bulk delete** on `/admin/imports` for job-scoped evidence — not `seed.py` or ad-hoc TRUNCATE.
- Scratch scripts under `apps/api/scripts/_*.py` are dev-only — not committed.

---

## Validation run (Jun 6)

- `test_dsi_validate_bulk_staging.py` — 7/7 (when run with dev DB flag)
- `test_dsi_job_progress.py` — pass
- `test_distributors_contract.py::test_distributor_master_import_validate_and_apply_paths` — pass (after Unit 4 fix)
- `admin/products/page.test.tsx` — 15/15

**Not run this session:** full `pnpm lint`, full API suite, browser DSI mapping smoke, job #43 apply E2E.

---

## New-agent prompt

```
Read CONTEXT.md (top section), docs/SESSION_HANDOVER_2026_06_06_DSI_UNITS_1_5.md, and BACKLOG-031.
Branch: fix/shipment-steward-performance. DB: Supabase postgres (not local cip).
Job #43 validated; fact_sales_sellout is empty until apply. Do not merge to main without explicit instruction.
Next: steward candidates → apply job #43, or implement BACKLOG-031 data health page.
```
