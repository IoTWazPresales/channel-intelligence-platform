# CURRENT state

**Last updated:** 2026-07-27 (Unit E1 implemented — VERIFY deferred, no-Opus)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | *(uncommitted E1 until Warren commits)* |
| **Pushed?** | E1 pending commit/push |
| **Next** | When CLI usage resets: **Opus VERIFY Unit E only** (C/D already PASS). Then E2 ([BACKLOG-074](../BACKLOG.md)) or Unit F. |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (**v1.5**).

**No-Opus mode:** E1 **implemented, VERIFY deferred** — do **not** claim PASS. C PASS @ `4a63a30`; D PASS @ `cc0138a`.

**Consolidation arc:** A–D PASS; **E1 implemented (VERIFY deferred)**; E2 = BACKLOG-074; F open.

---

## Unit E1 (this session)

| Label | Fact |
|-------|------|
| **Scope** | CST import steward: suggestion enrich + resolve/ignore/bulk + Import Centre UI |
| **API** | `cst_candidate_suggestions.py`; enrich-after-upsert; POST resolve/ignore/bulk-resolve |
| **Web** | `CstImportJobResolutionSection` under `admin/imports/` (no `Cst*` in `features/import-steward/`) |
| **Decision** | D-018; contract v1.5 |
| **Opus VERIFY** | **Deferred** until usage resets |
| **E2** | BACKLOG-074 — resolution-plan async |

---

## Unit D / C

| Label | Fact |
|-------|------|
| **D PASS** | @ `cc0138a` |
| **C PASS** | @ `4a63a30` |

---

## Do not

- Relocate CPOR into imports monolith
- Claim Unit E PASS without Opus VERIFY
- Invent `bulkStrategy` / engine capabilities
- Put importer-prefixed modules under `features/import-steward/` (D-006)
- Change DSI product tier order
- Relocate `/admin/cst-steward` into the engine
