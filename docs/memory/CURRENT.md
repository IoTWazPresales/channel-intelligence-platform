# CURRENT state

**Last updated:** 2026-08-01 (A1 AMBER halt — fill surface live; A2/A3 design queue)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260730_0075` on cip** |
| **HEAD** | tip of `main` (verify: `git rev-parse --short HEAD`) |
| **Pushed?** | verify before claiming |
| **Current phase** | **A-lane** (P1 exit sealed) |
| **Next** | **AMBER — Warren:** A1 fill plausibility (26Q2 ~46.5%). Design-halt: A2 metrics (Q-006), A3 replenishment/WoC grain (Q-007), PM bias/slip (Q-005). Do not invent A2 analytics or new PvE tiles. |

---

## Governing set (authoritative)

| Doc | Role |
|-----|------|
| [`docs/ROADMAP.md`](../ROADMAP.md) **v3.0** | What to build, phase order |
| [`docs/AUTONOMOUS_BUILD_CHARTER.md`](../AUTONOMOUS_BUILD_CHARTER.md) **v1.1** | How work is executed (zones, gates, question queue) |
| [`docs/COMMERCIAL_DOMAIN_RULES.md`](../COMMERCIAL_DOMAIN_RULES.md) **v1.0** | **Domain ground truth — never overridden by any agent** |
| [`docs/SURFACE_OWNERSHIP.md`](../SURFACE_OWNERSHIP.md) | Which surface owns which concept — **authoritative** |
| [`docs/OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) | Question queue (charter protocol) |
| [`docs/STEWARD_EXPERIENCE_CONTRACT.md`](../STEWARD_EXPERIENCE_CONTRACT.md) | What done means for steward surfaces |
| [`docs/STEWARD_ENGINE_DECISIONS.md`](../STEWARD_ENGINE_DECISIONS.md) | Why steward is built this way |

If CURRENT disagrees with ROADMAP about what's next for the session, CURRENT wins and ROADMAP gets corrected.

---

## P1 exit (sealed 2026-08-01)

| Artifact | Path |
|----------|------|
| Census | [`docs/DATA_CENSUS.md`](../DATA_CENSUS.md) |
| Defect log | [`docs/P1_LOAD_DEFECT_LOG.md`](../P1_LOAD_DEFECT_LOG.md) |
| Batch deferral | P1-D004 → [`BACKLOG-088`](../BACKLOG.md) (Shipping POD propagation) |

| Unit | Outcome |
|------|---------|
| P1-0 | Scaffold done |
| P1-1 | D-022 header `_policy` + `0075` on cip |
| P1-2 | DSI leave-alone |
| P1-3 | Shipment `#605` Warren OK |
| P1-4 | CPOR `#560` Warren OK |
| P1-5 | Lineups leave-alone: 3 `po_issued` / 285 lines / 52 PO links |
| P1-X | D001–D003 fixed-inline; D004 deferred |

**Pre-P1 dump:** `C:\Users\warren_eliason\cip-db-snapshots\cip_pre_p1_2026-07-31_172744.dump`

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Surface ownership + pre-build audit mandatory.  
AMBER: design-stage for new metrics/tiles; post-build for domain number judgment.  
RED: migrations beyond `0075`, schema, merges without clone-proof.

---

## Parked / extracted

| Item | Where |
|------|--------|
| Evidence POD → fact/current | BACKLOG-**088** (P1-D004) |
| Landing-quarter reattribution | BACKLOG-**068** (Shipping measurement first) |
| GitHub required CI check | BACKLOG-**087** |
| Customer merge alias seal | BACKLOG-**081** |
| CST alias batch confirm/reject | BACKLOG-**080** |
| Ops-list shell / pagination | BACKLOG-**079** / **085** |
| Customer merge companions | BACKLOG-**083** |
| URL helpers | BACKLOG-**084** |
| PM channel_id CASE redo | BACKLOG-**086** |
