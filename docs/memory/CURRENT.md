# CURRENT state

**Last updated:** 2026-08-01 (A3-03 replenishment flag v1)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260730_0075` on cip** |
| **HEAD** | `d6de3e0` |
| **Pushed?** | yes (`origin/main`) |
| **Current phase** | **A-lane** — A1 + A2 + A3 WoC + A3-03 replenishment shipped |
| **Next** | BACKLOG-092 paid recon when Ken files land; Q-001/002/003/009 still open; B-lane when A closed |

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
| **A3-03** | Replenishment flag v1 — `REPLENISHMENT_WOC_THRESHOLD_WEEKS=4`; summary + inventory; UI on `/sell-out` |
| **A1-07 / A1-08** | BU volume bias + ship-quarter slip; BACKLOG-091 Over-plan intake |
| **A2-U2** | Norms + comparable cases |
| **A3 WoC** | Dist×product velocity; BACKLOG-090 resolved |

---

## Standing quality bar

**Contract or STOP · code is evidence.** Metrics only from `COMMERCIAL_SEMANTICS`.  
AMBER: design-stage for new metrics/tiles; post-build for domain number judgment.  
RED: merges/supersessions without clone-proof; migrations/schema without Warren approval.
**Smoke:** browser automation only (`.cursor/rules/smoke-via-browser.mdc`).
