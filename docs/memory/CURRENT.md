# Current state

**Last updated:** 2026-07-16 (DSI unified multi-file batch)
**Verify git:** `git branch --show-current` ? `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/dsi-unified-multifile` |
| **Alembic (DB)** | **`20260710_0072`** (unchanged) |
| **Scope** | Unified DSI multi-file: matching layouts ? one job / one steward; divergent ? split jobs |

---

## Shipped this branch

- Workflow lock: **no thin-default** in `docs/WORKFLOW_DUAL_AGENT.md` + skills
- DSI batch: signature grouping, `POST /dsi/batch-propose`, `POST /dsi/batch-jobs`
- Multi-file per job: `file::sheet` mapping keys, `_dsi_source_file` provenance
- UI: `DsiBulkUploadDialog` group preview + unified batch upload

---

## Next

- Browser soak: Import Centre ? DSI unified batch (3 same-layout weekly files)
- U-M5 deferred: missed-week coverage calendar (FLAG)
- Merge after soak; shell PR separate on `feat/ops-master-grid-shell-parity`
