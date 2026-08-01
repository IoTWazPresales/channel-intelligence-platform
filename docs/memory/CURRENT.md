# CURRENT state

**Last updated:** 2026-08-01 (A-lane wrap)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260730_0075` on cip** |
| **HEAD** | `7db3f02` |
| **Pushed?** | yes (`origin/main`) |
| **Current phase** | **A-lane wrapped** — core A1/A2/A3 IMPLEMENTED; exit criteria met for intelligence surfaces |
| **Next** | **P2 / B-lane** (or Warren-chosen). Do **not** chase BACKLOG-092 payment files (Warren-owned). Promo automation → BACKLOG-093/094 |

---

## A-lane wrap (2026-08-01)

| Lane | Core exit | Status |
|------|-----------|--------|
| **A1** | Fill + exceptions + bias/slip (BU) + Over-plan intake | **Done** — PM bias blocked **Q-009**; support bias blocked **Q-002** / A1-09 |
| **A2** | Portfolio spend/delivery/CPU + norms + comparables | **Done** — claim rate non-computable (**D-027**); paid = **BACKLOG-092** (Warren files) |
| **A3** | Derived stock + WoC dist×product + replenishment flag v1 | **Done** |

**Parked (not A-blockers):** BACKLOG-092 (paid), **093** (customer promo-load recon), **094** (promo MAC + price-delta forecast). Open Qs: Q-001/002/003/009.

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

---

## Standing quality bar

**Contract or STOP · code is evidence.** Metrics only from `COMMERCIAL_SEMANTICS`.  
AMBER: design-stage for new metrics/tiles; post-build for domain number judgment.  
RED: merges/supersessions without clone-proof; migrations/schema without Warren approval.  
**Smoke:** browser automation only (`.cursor/rules/smoke-via-browser.mdc`).
