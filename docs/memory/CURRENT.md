# CURRENT state

**Last updated:** 2026-07-24 (Steward Experience Contract v1.0 + consolidation arc opened)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260720_0073` on cip** |
| **HEAD** | (see git — docs commit lands this session) |
| **Pushed?** | after this commit |
| **Next** | Consolidation arc Units A–C (generic steward engine → CPOR meets contract v1.0). No new import surfaces until then. Operator soak on CPOR Resolve + upload-first still open. |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.**  
Authoritative steward slot inventory: `docs/STEWARD_EXPERIENCE_CONTRACT.md` (v1.0).  
Warren override (2026-07-22): CPOR Resolve = DSI+shipment **operator intelligence** + upload-first wizard — now graded via contract S-rows.

**Consolidation arc open (Units A–C).**  
No new import surfaces until the steward engine is generic and CPOR meets contract v1.0.

---

## CPOR historical import — status language

| Label | Fact |
|-------|------|
| **Proven** | H1; H2 apply; smoke `H2-SMOKE-556` |
| **Proven (this arc)** | Unit 1 suggestions contract PASS @ `50c1ee8`; Unit 2 frontend intelligence PASS @ `ade5624`; Unit 3 upload-first PASS @ `5044fce` |
| **Known contract gaps (v1.0)** | S9 absent; S6 nulled evidence; S12 unverified at volume; S14 violated by `cporTokenRowId` string-hash keys |
| **Out of scope** | Unit 4 config-driven `ImportJobResolutionSection`; relocate into `admin/imports/page.tsx` |

Route (keep): `/commercial-planner/cpor-cases/historical-import`  
Canonical references: contract S-rows + shared `features/import-steward/` engine (post-consolidation)

---

## Parked — DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Relocate CPOR into imports monolith
- Auto-create dims; change DSI resolution tiers
- Claim Unit 4 done
- Start Unit A in the same commit as this docs land
- Create new `Dsi*` / `Shipment*` / `Cpor*` files under `features/import-steward/`
