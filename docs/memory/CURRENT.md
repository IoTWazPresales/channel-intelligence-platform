# CURRENT state

**Last updated:** 2026-08-01 (governing set → charter v1.2 + COMMERCIAL_SEMANTICS)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **Alembic (DB)** | **`20260730_0075` on cip** |
| **HEAD** | tip of `main` (verify: `git rev-parse --short HEAD`) |
| **Pushed?** | verify before claiming |
| **Current phase** | **A-lane** (P1 exit sealed; A1 fill VERIFIED) |
| **Next** | A2/A3 build only for metrics defined in `COMMERCIAL_SEMANTICS`. Open: Q-005–Q-007 answers; BACKLOG-090 WoC grain defect (do not fix inline). |

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

Stubs (do not edit for content): `SURFACE_OWNERSHIP.md`, `PLAN_VS_EXECUTED_SHIPPED_TAXONOMY.md`, `PLAN_VS_EXECUTED_SPEC.md`, `WORKFLOW_DUAL_AGENT.md` → point at the docs above.

If CURRENT disagrees with ROADMAP about what's next for the session, CURRENT wins and ROADMAP gets corrected.

---

## P1 exit (sealed 2026-08-01)

| Artifact | Path |
|----------|------|
| Census | [`docs/DATA_CENSUS.md`](../DATA_CENSUS.md) |
| Defect log | [`docs/P1_LOAD_DEFECT_LOG.md`](../P1_LOAD_DEFECT_LOG.md) |
| Batch deferral | P1-D004 → BACKLOG-088 |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Metrics only from `COMMERCIAL_SEMANTICS`.  
AMBER: design-stage for new metrics/tiles; post-build for domain number judgment.  
RED: merges/supersessions without clone-proof; migrations/schema without Warren approval.  
Import/steward loads: unattended per autonomy zones (D-026).

---

## Open defects / backlog (A-lane)

| Item | Where |
|------|--------|
| Channel Ops summary WoC grain mismatch | BACKLOG-**090** |
| Evidence POD → fact/current | BACKLOG-**088** |
| Over-plan intake UI rename | BACKLOG-**091** |
| Cost per incremental unit | BACKLOG-**089** (do not build) |
