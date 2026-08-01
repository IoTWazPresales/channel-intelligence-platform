# CURRENT state

**Last updated:** 2026-08-01 (A2-U1 + A3 WoC grain fix)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260730_0075` on cip** |
| **HEAD** | tip of `main` (verify) |
| **Pushed?** | verify before claiming |
| **Current phase** | **A-lane** — A2-U1 shipped; A3 WoC grain fixed |
| **Next** | A1 bias/slip SPEC ONLY tiles; BACKLOG-091 UI rename on next A1 touch; BACKLOG-092 paid recon when Ken files land |

---

## Governing set (authoritative)

| Doc | Role |
|-----|------|
| [`docs/ROADMAP.md`](../ROADMAP.md) **v3.0** | What to build, phase order |
| [`docs/AUTONOMOUS_BUILD_CHARTER.md`](../AUTONOMOUS_BUILD_CHARTER.md) **v1.2** | Execution: zones, gates, dual-agent loop |
| [`docs/COMMERCIAL_DOMAIN_RULES.md`](../COMMERCIAL_DOMAIN_RULES.md) **v1.0** | **Domain ground truth — never overridden by any agent** |
| [`docs/COMMERCIAL_SEMANTICS.md`](../COMMERCIAL_SEMANTICS.md) | Metrics, grains, lifecycle, owning surfaces — **authoritative** |
| [`docs/OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) | Question queue (charter protocol) |
| [`docs/STEWARD_EXPERIENCE_CONTRACT.md`](../STEWARD_EXPERIENCE_CONTRACT.md) | What done means for steward surfaces |
| [`docs/STEWARD_ENGINE_DECISIONS.md`](../STEWARD_ENGINE_DECISIONS.md) | Why steward / process is built this way |

Stubs: `SURFACE_OWNERSHIP.md`, `PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md`, `PLAN_VS_EXECUTED_SPEC.md`, `WORKFLOW_DUAL_AGENT.md`.

---

## Just shipped (2026-08-01)

| Item | Evidence |
|------|----------|
| **Q-008** | Claim rate **non-computable** (D-027); no distinct **owed** amount in U5 settlement (not “paid” — paid = Ken payment recon) |
| **A2-U2** | Norms + comparable cases (`/intelligence/norms`, `/comparable-cases`) |
| **A3 WoC** | Sell-out velocity at dist×product; portfolio Σstock/Σvelocity. **Before** ~78 956 weeks · **After** ~13.6 weeks (cip; stock 33 571) |
| **BACKLOG-090** | Resolved |

---

## Standing quality bar

**Contract or STOP · code is evidence.** Metrics only from `COMMERCIAL_SEMANTICS`.  
AMBER: design-stage for new metrics/tiles; post-build for domain number judgment.  
RED: merges/supersessions without clone-proof; migrations/schema without Warren approval.
