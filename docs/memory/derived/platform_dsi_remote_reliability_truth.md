# Platform truth — DSI remote Supabase reliability (derived memory)

**Last updated:** 2026-06-05  
**Source session:** DSI job #43 audit (`docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md`)  
**Audience:** Future agents (Claude Code audit, Opus review) — operational truth, not user docs.

---

## Decision record

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-05 | **Stay on remote Supabase** for DSI testing | Must validate real deployment path (EU pooler, latency); switching to local `cip` hides the failure class |
| 2026-06-05 | **Do not** adopt temp-file download/delete for shipment evidence during DSI validate | Evidence lives in `shipment_evidence_line`; already preloaded to `ShipmentCorroborationCache`; upload file already read once from storage |
| 2026-06-05 | **Priority work = BACKLOG-030** (batched DSI validate + chunked commits) before cosmetic backlogs | Only code path that directly shortens monolithic transaction on remote pooler |

---

## Active database target (Warren machine, 2026-06-05)

| Variable | Target |
|----------|--------|
| `DATABASE_URL` | Supabase EU transaction pooler `:6543`, database `postgres` |
| `DATABASE_URL_SYNC` | Supabase EU session pooler `:5432`, database `postgres` |
| Config file | `apps/api/.env` (gitignored) |
| `DATABASE_URL_LOCAL*` | `localhost:5432/cip` — present but **inactive** unless URLs swapped |

**Implication:** `conftest.py` guard for database name `cip` does **not** protect Supabase runs. Always `SELECT current_database()` before writes.

---

## Incident: import job #43

| Field | Value |
|-------|--------|
| Template | `distributor_inventory` |
| File | `RAW.xlsx` |
| Rows | ~168,839 |
| Observed validate duration | ~45 min (worker) before failure |
| Terminal job state | `failed` / `failed` |
| `error_summary` | `psycopg.OperationalError` … `server closed the connection unexpectedly` |
| Failing SQL shape | `SELECT … FROM dim_customer LIMIT 60` |
| Candidates after failure | 0 (full `rollback`) |
| Celery task log | May show **succeeded** (task returns after writing `failed` to DB — not a success) |

**Failure locus:** `customer_candidates()` in AI resolution path during row loop (`distributor_sales_inventory.py`), not file I/O.

---

## Architectural gaps (DSI vs shipment validate)

| Concern | Shipment | DSI (current) |
|---------|----------|---------------|
| Staging write | Chunked `INSERT ON CONFLICT` | Per-row `db.add` |
| Transaction scope | Single commit at end (but faster) | Single commit — **45+ min** on 169k @ remote |
| Corroboration | N/A | `ShipmentCorroborationCache` (good) |
| Master preload | Varies | `_build_resolution_cache` (good) |
| Stray per-row SELECTs | Reduced | `customer_candidates` still hits DB |

---

## Backlog relevance matrix (remote DSI success)

| Tier | IDs | Helps remote 169k DSI validate? |
|------|-----|----------------------------------|
| **P0 — must** | **BACKLOG-030** (new) | **Yes** — batched writes + chunked commits |
| **P1 — should** | BACKLOG-028, BACKLOG-002, BACKLOG-003 | **Yes** — pooler / pooling / co-location |
| **P2 — steward perf** | BACKLOG-006, BACKLOG-018 | Partial — after validate succeeds |
| **P3 — UX / other importers** | 001, 004, 005, 007, 013, 020, 023, 029(b) | No direct validate survival |
| **P4 — PM / PIM** | 009–011, 026, 027 | No |
| **P5 — done** | 022, 025(A), 029(a,c) | Already shipped on branch |

**Completing every backlog entry does NOT guarantee Supabase validate success.**

---

## Implementation audit checklist

When reviewing a Phase 1 PR, verify:

- [ ] Staging upsert uses set-based SQL with chunk size documented (shipment pattern cited)
- [ ] Chunk commits persist recoverable progress in `import_job` / `staged_metadata`
- [ ] No per-row `select(DimCustomer).limit(60)` in hot loop
- [ ] Governance unchanged (no auto-create masters; DSI tier order untouched)
- [ ] Real Supabase execution evidence in PR description or test log
- [ ] Wall time recorded for ≥10k row fixture minimum; 169k soak noted
- [ ] `pipeline.py` rollback behavior documented if still all-or-nothing per chunk
- [ ] Parity rule `.cursor/rules/import-parity.mdc` cited in commit message

---

## Ops truths

- `pnpm dev:api` uses `--reload` (`scripts/dev-api.js`) — kills API mid long validate; use plain uvicorn for soak tests
- Re-validate job #43 on Supabase **before** Phase 1 is a soak test only — may fail again
- Computer reboot **not** required for pooler disconnect class

---

## Cross-links

- Handover: `docs/SESSION_HANDOVER_2026_06_05_DSI_REMOTE_SUPABASE.md`
- Backlog: `docs/BACKLOG.md` → BACKLOG-030
- Living history: `CONTEXT.md` (top section)
