# CURRENT state

**Last updated:** 2026-07-26 (Unit B revised — engine genericity + shipment consumer #2)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260720_0073` on cip** |
| **HEAD** | (see git after Unit B commit) |
| **Pushed?** | after Unit B commit |
| **Next** | Unit B VERIFY (Opus). Then Unit B2 (shipment bulk preview + S9-partial) or Unit C (CPOR). |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (**v1.1**).

**Consolidation arc:** Units A–B shipped (wired + unit-tested). Unit B2 / C / D / E open.

---

## CPOR historical import — status language

| Label | Fact |
|-------|------|
| **Proven** | H1; H2 apply; smoke `H2-SMOKE-556` |
| **Proven (this arc)** | Unit 1 suggestions @ `50c1ee8`; Unit 2 intelligence @ `ade5624`; Unit 3 upload-first @ `5044fce` |
| **Known contract gaps (v1.1)** | S9 absent; S6 nulled evidence; S12 unverified at volume; S14 `cporTokenRowId` — close in Unit C |
| **Out of scope** | Unit 4 config-driven `ImportJobResolutionSection`; relocate into `admin/imports/page.tsx` |

Route (keep): `/commercial-planner/cpor-cases/historical-import`

---

## Unit B (this session)

| Label | Fact |
|-------|------|
| **Wired + unit-tested** | Core `useStewardResolutionPlan` geo-free; DSI composes geo via `useDsiResolutionPlan`; shipment binds `SHIPMENT_ENGINE_CONFIG` + core toolbar/drawer/paginate; shipment domain relocated to `admin/shipment-evidence/`; bulk relocated untouched |
| **Predicate** | Shipment plan payload has **no** `duplicate_review_required` — core ready=`ready===true`; DSI composes duplicate gate |
| **Baselines** | Steward vitest 199/199 before+after; shipment+DSI API steward 84 passed; no cip writes |
| **Contract** | v1.1 — gaps + consolidation arc + apply-all dual placement note |
| **Not proven** | Live operator soak; Opus VERIFY pending |

---

## Unit A

| Label | Fact |
|-------|------|
| **Opus VERIFY** | **PASS** @ `ce1ca27` / pin `ead4e9f` |

---

## Parked — DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Relocate CPOR into imports monolith
- Auto-create dims; change DSI resolution tiers
- Claim Unit 4 done
- Create new `Dsi*` / `Shipment*` / `Cpor*` files under `features/import-steward/`
- Add `bulkStrategy` / capability flags that fossilize S8 in the engine core
- Close S6/S7/S8/S9-partial in this unit (B2/D)
