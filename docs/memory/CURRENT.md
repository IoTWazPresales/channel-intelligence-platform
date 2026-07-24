# CURRENT state

**Last updated:** 2026-07-24 (Unit A — generic steward engine extracted; DSI consumer #1)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260720_0073` on cip** |
| **HEAD** | (see git after Unit A commit) |
| **Pushed?** | after Unit A commit |
| **Next** | Unit B — migrate shipment twins onto generic engine; delete `Shipment*` steward twins. Then Unit C — CPOR mounts engine (S6/S8/S9) + rowId fix. |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (v1.0).  

**Consolidation arc:** Unit A shipped (wired + unit-tested). Units B–C open.

---

## CPOR historical import — status language

| Label | Fact |
|-------|------|
| **Proven** | H1; H2 apply; smoke `H2-SMOKE-556` |
| **Proven (this arc)** | Unit 1 suggestions @ `50c1ee8`; Unit 2 intelligence @ `ade5624`; Unit 3 upload-first @ `5044fce` |
| **Known contract gaps (v1.0)** | S9 absent; S6 nulled evidence; S12 unverified at volume; S14 violated by `cporTokenRowId` string-hash keys — close in Unit C |
| **Out of scope** | Unit 4 config-driven `ImportJobResolutionSection`; relocate into `admin/imports/page.tsx` |

Route (keep): `/commercial-planner/cpor-cases/historical-import`

---

## Unit A (this session)

| Label | Fact |
|-------|------|
| **Wired + unit-tested** | Generic engine under `features/import-steward/`: `useStewardResolutionPlan`, `StewardResolutionPlanToolbar`, `useStewardBulkSteward`, `StewardBulkSection`, `StewardBulkActionInlineForm`, `StewardCandidateDrawer`, `stewardCandidateFilterLogic` + `DSI_ENGINE_CONFIG` bind. DSI thin `@deprecated` wrappers. |
| **Opus VERIFY** | **PASS** @ `ce1ca27` (prior STOP on missing `StewardCatalogOpt` fixed) |
| **Baseline** | Web vitest import-steward+imports: 190/190 before+after. API DSI steward/plan/bulk subset: 93 passed, 6 skipped. No cip writes. |
| **Not proven** | Live operator soak of DSI Resolve after extraction |

---

## Parked — DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Relocate CPOR into imports monolith
- Auto-create dims; change DSI resolution tiers
- Claim Unit 4 done
- Create new `Dsi*` / `Shipment*` / `Cpor*` files under `features/import-steward/` (except existing `dsiSteward.*` bind/config pattern)
- Touch shipment twins until Unit B
