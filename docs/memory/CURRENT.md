# CURRENT state

**Last updated:** 2026-07-29 (P0 hygiene — ROADMAP + decisions + backlog extract)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | tip of `main` (verify: `git rev-parse --short HEAD`) |
| **Pushed?** | pending this hygiene push |
| **Phase source of truth** | **`docs/ROADMAP.md`** (Warren-approved v1.0) |
| **Current phase** | **P0 — Stabilise the base** |
| **Next** | P0 remaining only — no P0 implementation this session |

---

## P0 remaining

| Item | Status |
|------|--------|
| CI pnpm gate (required) | Open |
| `scripts/verify-gate` | Open |
| Header-vocabulary config unit (D-015 / BACKLOG-**082**) | Open — ASUS seed extracted; stash dropped |
| Cherry-pick `558d088` channel_id CASE | **Skipped** — conflicts in `product_import_sync.py`; not applied |
| Kill `feat/ops-master-grid-shell-parity` | **STOPPED** — diff has substantial extras beyond D-014’s three extracts; BACKLOG-079–081 written; branch **not** deleted |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Steward contract **v1.6**.  
Decisions append-only: D-013–D-015 (2026-07-28 hygiene) appended after existing D-013–D-019 (CPOR/CST) — **ID reuse by date**; do not renumber.

---

## Parked / extracted

| Item | Where |
|------|--------|
| Header ASUS seed + denylist | BACKLOG-**082** |
| Customer merge alias seal | BACKLOG-**081** |
| CST alias batch confirm/reject | BACKLOG-**080** |
| Ops-list shell parity (fold-in, not standalone) | BACKLOG-**079** |
| `feat/ops-master-grid-shell-parity` | Still on origin — awaiting Warren delete call |
| Stash `park-dsi-asus-dealer-name-automap` | **Dropped** after knowledge extract |
