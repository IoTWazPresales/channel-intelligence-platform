# CURRENT state

**Last updated:** 2026-08-01 (A1 bias/slip + over-plan rename)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260730_0075` on cip** |
| **HEAD** | `8110cb3` |
| **Pushed?** | yes (`origin/main`) |
| **Current phase** | **A-lane** — A1 bias/slip + A2-U1/U2 + A3 WoC shipped |
| **Next** | A3 replenishment flag v1 (tenant config; default 4 weeks); BACKLOG-092 paid recon when Ken files land; Q-001/002/003 still open |

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
| **A1-07 / A1-08** | BU volume bias + ship-quarter slip on `/plan-vs-executed` (`volume_bias`, `slip`). PM bias = `unavailable` until **Q-009** |
| **BACKLOG-091** | Resolved — UI **Over-plan intake** (+ API aliases) |
| **Q-008** | Claim rate **non-computable** (D-027) |
| **A2-U2** | Norms + comparable cases |
| **A3 WoC** | Dist×product velocity; cip ~13.6 weeks. **BACKLOG-090** resolved |

---

## Standing quality bar

**Contract or STOP · code is evidence.** Metrics only from `COMMERCIAL_SEMANTICS`.  
AMBER: design-stage for new metrics/tiles; post-build for domain number judgment.  
RED: merges/supersessions without clone-proof; migrations/schema without Warren approval.
