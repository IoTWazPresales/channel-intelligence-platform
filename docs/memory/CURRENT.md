# CURRENT state

**Last updated:** 2026-08-08 (CST multi-file batch shipped)

**Branch:** `feat/cst-takealot-pilot-config`

**Alembic:** `20260807_0010`

## Locked CST product rule (Warren)

Unmappable CST product → **Ignore** (`ignore_no_catalogue`) → **Product catalogue gaps** (`source=cst`). Never auto-create PM. FLAG ≠ BLOCK.

## Done this session

- Takealot CST pilot + multi-token resolve; BACKLOG-129; soft-data hygiene
- **CST multi-file → DSI parity:** `cst_batch.py` + `/cst/batch-propose|batch-jobs` + `CstBulkUploadDialog` + period strip; flat process iterates all raws with per-file period. Live job **799**: WEEK 28–31 → 4 periods, 96 staging rows.

## Next

1. Browser smoke CST multi-file batch UI (Import Centre) / Opus VERIFY when available
2. Historical backfill via product UI
3. Open PR for `feat/cst-takealot-pilot-config` when ready to promote

**Env:** local Windows. `cip` @ `20260807_0010`. Takealot customer_id=20. Consult deferred (limit); Codex not wired.
