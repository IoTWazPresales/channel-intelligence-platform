# CURRENT state

**Last updated:** 2026-07-20 (quality bar lock + CPOR steward parity fix)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260720_0073` on cip** |
| **Next** | Fable VERIFY steward parity (clone bar) ? H3 only after PASS |

---

## Standing quality bar (Warren 2026-07-20)

Locked in `docs/WORKFLOW_DUAL_AGENT.md`, import-parity, cip-dual-agent skill:
**Canonical clone or STOP · no half-PASS · never skim · own surface ? weaker UX.**
Optimize for UX/architecture/best-in-market ? never speed.

---

## CPOR historical import

- H1 PASS; H2 apply path existed but steward UX was a **thin mount** (rejected)
- **Parity fix (in flight):** shipment-shaped `CporHistoricalImportJobResolutionSection` (tabs, selection, bulk map, drawer), async validate + Celery-shaped `/progress`, `BackgroundTaskKind` + poll, wizard steps upload?validate?resolve?apply
- Smoke earlier: `H2-SMOKE-556` applied OK

---

## Parked ? DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Half-parity PASS; push main; auto-create dims; waterfall rewrite of settled Results
