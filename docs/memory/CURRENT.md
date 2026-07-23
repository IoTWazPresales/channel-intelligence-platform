# CURRENT state

**Last updated:** 2026-07-23 (CPOR intelligence + upload-first Units 1–3 PASS)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260720_0073` on cip** |
| **HEAD** | `5044fce` (Unit 3) on `ade5624` (U2) on `50c1ee8` (U1) |
| **Pushed?** | yes |
| **Next** | Operator soak on Resolve + upload-first; then PR or next TRIGGER. Unit 4 config-driven section = separate PR later. |

---

## Standing quality bar

**Canonical clone or STOP · no half-PASS · code is evidence.**  
Warren override (2026-07-22): CPOR Resolve = DSI+shipment **operator intelligence** + upload-first wizard.

---

## CPOR historical import — status language

| Label | Fact |
|-------|------|
| **Proven** | H1; H2 apply; smoke `H2-SMOKE-556` |
| **Proven (this arc)** | Unit 1 suggestions contract PASS @ `50c1ee8`; Unit 2 frontend intelligence PASS @ `ade5624`; Unit 3 upload-first PASS @ `5044fce` |
| **Out of scope** | Unit 4 config-driven `ImportJobResolutionSection`; relocate into `admin/imports/page.tsx` |

Route (keep): `/commercial-planner/cpor-cases/historical-import`  
Canonical references: `DsiImportJobResolutionSection`, `ShipmentImportJobResolutionSection`

---

## Parked — DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Relocate CPOR into imports monolith
- Auto-create dims; change DSI resolution tiers
- Claim Unit 4 done
