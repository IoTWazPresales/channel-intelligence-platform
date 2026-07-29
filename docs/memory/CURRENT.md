# CURRENT state

**Last updated:** 2026-07-29 (P0 hygiene — D-020–022 renumber, ops-master kill, BACKLOG-083–086)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | tip of `main` (verify: `git rev-parse --short HEAD`) |
| **Pushed?** | yes (this hygiene follow-up) |
| **Phase source of truth** | **`docs/ROADMAP.md`** (Warren-approved v1.0) |
| **Current phase** | **P0 — Stabilise the base** |
| **Next** | P0 remaining only — **new chat** for implementation |

---

## P0 remaining

| Item | Status |
|------|--------|
| CI pnpm gate (required) | Open |
| `scripts/verify-gate` | Open |
| Header-vocabulary config unit (D-022 / BACKLOG-**082**) | Open — ASUS seed extracted; stash dropped |
| PM `channel_id` CASE / typed cast (`558d088`) | BACKLOG-**086** — cherry-pick skipped (conflict); redo natively |
| Kill `feat/ops-master-grid-shell-parity` | **Done** — deleted local + remote after D-021 fuller extract |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Steward contract **v1.6**.  
Decisions: 2026-07-28 hygiene entries renumbered **D-020 / D-021 / D-022** (collision with 2026-07-27 D-013–D-015 fixed). Do not renumber 2026-07-27 entries.

---

## Parked / extracted

| Item | Where |
|------|--------|
| Header ASUS seed + denylist | BACKLOG-**082** |
| Customer merge alias seal | BACKLOG-**081** |
| CST alias batch confirm/reject | BACKLOG-**080** |
| Ops-list shell parity (fold-in) | BACKLOG-**079** |
| Customer merge companions | BACKLOG-**083** |
| URL helpers (`useDebouncedUrlQuery` / `skipLimitSearchParams`) | BACKLOG-**084** |
| Ops-list pagination (fold-in) | BACKLOG-**085** |
| PM channel_id CASE redo | BACKLOG-**086** |
| `feat/ops-master-grid-shell-parity` | **Deleted** (was `d789ad9`) |
| Stash `park-dsi-asus-dealer-name-automap` | **Dropped** after knowledge extract |
| Channel-ops KPI / `shippingUtcDates.ts` | **Not backloged** — superseded by main commercial KPI rebuild (D-021) |
