# CURRENT state

**Last updated:** 2026-07-29 (P0 CI cip_test + verify-gate merged)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | tip of `main` (verify: `git rev-parse --short HEAD`) — includes PR #9 + #8 |
| **Pushed?** | yes |
| **Phase source of truth** | **`docs/ROADMAP.md`** (Warren-approved v1.0) |
| **Current phase** | **P0 — Stabilise the base** |
| **Next** | P0 remaining: header-vocabulary (D-022 / BACKLOG-082); PM `channel_id` CASE (BACKLOG-086) |

---

## P0 remaining

| Item | Status |
|------|--------|
| CI pnpm gate (required) | **Clash fixed** · suite runs on `cip_test` · **required status check → BACKLOG-087** (TRIGGER: GitHub Pro purchased). Process-only until then: **no `--admin` merges**. |
| `scripts/verify-gate` | **Done** — `pnpm verify-gate`; proven clean + known-tsc catch |
| Header-vocabulary config unit (D-022 / BACKLOG-**082**) | Open |
| PM `channel_id` CASE / typed cast (`558d088`) | BACKLOG-**086** |
| Kill `feat/ops-master-grid-shell-parity` | **Done** |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Steward contract **v1.6**.  
CI API defects recorded in `docs/CI_API_DEFECT_LOG_2026-07-29.md` (1550 passed / 79 failed / 30 errors on `cip_test`) — batch-fix later, not this unit.

---

## Parked / extracted

| Item | Where |
|------|--------|
| GitHub required CI check | BACKLOG-**087** |
| Header ASUS seed + denylist | BACKLOG-**082** |
| Customer merge alias seal | BACKLOG-**081** |
| CST alias batch confirm/reject | BACKLOG-**080** |
| Ops-list shell parity (fold-in) | BACKLOG-**079** |
| Customer merge companions | BACKLOG-**083** |
| URL helpers | BACKLOG-**084** |
| Ops-list pagination (fold-in) | BACKLOG-**085** |
| PM channel_id CASE redo | BACKLOG-**086** |
