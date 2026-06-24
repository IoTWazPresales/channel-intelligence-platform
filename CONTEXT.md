# Channel Intelligence Platform — Context

> **Memory palace router.** Authoritative current state:
> **[`docs/memory/CURRENT.md`](docs/memory/CURRENT.md)**
>
> Read order: **[`docs/memory/MEMORY_PALACE.md`](docs/memory/MEMORY_PALACE.md)**

---

## How agents update state

1. Edit **`docs/memory/CURRENT.md`** after significant work (keep it short).
2. Append **one changelog line** below (newest first).
3. Do **not** add `## CURRENT STATE — supersedes every block below` sections here anymore.

For deferrals use **`docs/BACKLOG.md`**. For conflicts between docs, **ask Warren** before proceeding (see MEMORY_PALACE.md).

---

## Changelog

| Date | Summary |
|------|---------|
| 2026-06-24 | **Shipment apply loaded UX:** shared `ImportJobLoadedSuccessCallout` on imports wizard step 6 when job stage `loaded`; BACKLOG-045 steward UI parity audit parked. |
| 2026-06-24 | **Shipment wizard + steward DSI parity (Phases 1–3):** 7-step wizard; validate progress fix; entity filter fix; `ShipmentImportJobResolutionSection` rework (tabs in workspace, plan toolbar, bulk steward, server re-validate); contract D4 updated. |
| 2026-06-24 | **Local merge:** fast-forward `feat/dsi-async-topology` to `0e61744` from `cursor/cloud-agent-1782231728131-em82n` (Plan C + D + BACKLOG-007). Local `cip` still at alembic `20260609_0049`. |
| 2026-06-24 | **Shipment steward UX + BACKLOG-007:** inline row actions + drawer (DSI parity); auto resolution plan compute on scope change; post-validate re-map UI on imports page; orphan `source_key` purge on re-validate (`test_shipment_evidence_orphan_purge.py`). |
| 2026-06-24 | **Plan D bitemporal shipment evidence (D1–D3):** migration `20260623_0050` (`shipment_evidence_observation` + `shipment_evidence_current` view + backfill); dual-write on validate (`CIP_SHIPMENT_BITEMPORAL_DUAL_WRITE`); corroboration read switch (`CIP_SHIPMENT_BITEMPORAL_READ`). Flags default off. D4–D5 deferred. |
| 2026-06-23 | **Plan C shipment steward parity:** workspace section, resolution plan API, paginated candidates + tab-counts, alias-scope port, operator docs; Plan D bitemporal design doc (no migration). Legacy panel retained in dialog. |
| 2026-06-23 | DSI customer alias-scope module (`dsi_customer_alias_scope.py`) wired to bulk map + provisional + async steward; steward tab-count/cache fixes; read-only customer duplicate groups API + admin page; BACKLOG-044 shipment parity parked. |
| 2026-06-22 | DSI customer sim-name plan tier (`575276f`); provisional create-path similarity reuse (`38b2c9e`); ambiguous product plan crash fix (`9f3206f`); HEAD `9f3206f`, **2 commits unpushed**. |
| 2026-06-22 | Warren local dev on **topology B**: Supabase `public` cloned read-only into local `cip` (pg_dump/pg_restore); `.env` repointed to `127.0.0.1`; anchors verified (`dim_product` 18158, alembic `20260609_0049`); rollback dumps in repo root (untracked). |
| 2026-06-21 | Phase A DSI async topology (BACKLOG-038–043): beat off Windows solo, interactive/batch queues, defer post-validate auto-apply, scaled compute poll grace, dedupe error banners, CI test fix. |
| 2026-06-21 | Added `docs/memory/ROADMAP.md` (phased schedule + done verification); BACKLOG-038–043 for Phase A DSI topology; BACKLOG-001 trigger updated post PR #5. |
| 2026-06-21 | PR **#5** merged to `main` (`0540435`); new branch `feat/dsi-async-topology` for DSI queue/scheduling work; branch/PR lifecycle + context handover rules added. |
| 2026-06-21 | Project rules Memory Palace section aligned to `CURRENT.md` / `MEMORY_PALACE.md`. |
| 2026-06-21 | Memory palace consolidation: `CURRENT.md`, `MEMORY_PALACE.md`, `DEV_TOPOLOGY.md`; full prior CONTEXT → [`docs/memory/CONTEXT-archive-through-2026-06-21.md`](docs/memory/CONTEXT-archive-through-2026-06-21.md); async docs aligned. |

---

## Archive

All append-only history through **2026-06-21** (including duplicate CURRENT STATE blocks):

**[`docs/memory/CONTEXT-archive-through-2026-06-21.md`](docs/memory/CONTEXT-archive-through-2026-06-21.md)**

Use archive for forensic history only — not for current branch, Alembic head, or "what works now".
