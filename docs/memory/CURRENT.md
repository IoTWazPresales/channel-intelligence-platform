# CURRENT state

**Last updated:** 2026-07-30 (verify-gate junction wipe fixed; web node_modules restored)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` (P1 units may use short-lived `feat/p1-*` same-day merge) |
| **Alembic (DB)** | **`20260727_0074` on cip** |
| **HEAD** | tip of `main` (verify: `git rev-parse --short HEAD`) |
| **Pushed?** | verify before claiming |
| **Phase source of truth** | **`docs/ROADMAP.md`** |
| **Current phase** | **P1 — Load the corpus** |
| **Next** | Apply alembic `20260730_0075` on cip (Warren); Warren runs P1-1 verification sequence; then P1-2 DSI load with halt |

---

## P1 lock (2026-07-30)

| Item | Decision |
|------|----------|
| Load order | P1-0 scaffold → P1-1 **082** → P1-2 DSI → P1-3 shipment → P1-4 CPOR → P1-5 lineups → P1-X batch-fix |
| Exit artifacts | [`docs/DATA_CENSUS.md`](../DATA_CENSUS.md) + [`docs/P1_LOAD_DEFECT_LOG.md`](../P1_LOAD_DEFECT_LOG.md) |
| A1 window | All quarters with lineup coverage on cip; **credible core 26Q1 → current**; census reports per-quarter coverage |
| Open Decision #4 / BACKLOG-068 | **A1 v1 fill = shipped-basis, ungated on `pod_date`**. Landed = additional lens (tile later). P1 shipment census **measures** `pod_date` completeness only |
| Defect discipline | Log unless load-blocking; no inline drive-by fixes |
| Domain halt | After each of P1-2…P1-5: update census, print numbers, **HALT** with numbered verification sequence; Warren must say VERIFIED |

---

## P1 unit status

| Unit | Status |
|------|--------|
| P1-0 Census + defect-log scaffold | **Done** |
| P1-1 BACKLOG-082 header config | **Implemented** — migration `20260730_0075` authored, **not applied**; awaiting Warren verify sequence + upgrade |
| P1-2…P1-5 domain loads | Pending (halt after each) |
| P1-X boundary batch-fix | Pending |

---

## P0 closed (2026-07-29)

| Item | Status |
|------|--------|
| CI pnpm + `cip_test` suite path | Done (PR #8) — **required GitHub check → BACKLOG-087** (Pro). Process: **no `--admin` merges** |
| `scripts/verify-gate` | Done (PR #9) |
| Kill `feat/ops-master-grid-shell-parity` | Done |
| Header-vocabulary (was P0 remaining) | **Moved into P1** as P1-1 / BACKLOG-**082** |
| PM `channel_id` CASE | BACKLOG-**086** (not P1 load path) |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Steward contract **v1.6**.  
Behaviour-changing units must ship a **## Verification sequence** (see `docs/WORKFLOW_DUAL_AGENT.md`) — authored before implementation.  
CI API defects: `docs/CI_API_DEFECT_LOG_2026-07-29.md` — batch-fix later, not during P1 load.

---

## Parked / extracted

| Item | Where |
|------|--------|
| GitHub required CI check | BACKLOG-**087** |
| Header ASUS seed + denylist | BACKLOG-**082** (Active — P1-1) |
| Customer merge alias seal | BACKLOG-**081** |
| CST alias batch confirm/reject | BACKLOG-**080** |
| Ops-list shell parity (fold-in) | BACKLOG-**079** |
| Customer merge companions | BACKLOG-**083** |
| URL helpers | BACKLOG-**084** |
| Ops-list pagination (fold-in) | BACKLOG-**085** |
| PM channel_id CASE redo | BACKLOG-**086** |
| Landing-quarter reattribution KPI | BACKLOG-**068** (A1 gating settled; KPI build still deferred) |
