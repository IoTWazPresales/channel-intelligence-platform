# CURRENT state

**Last updated:** 2026-07-20 (backlog prune + shipment viewport shell 069)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-listing-status-audit` |
| **Alembic (DB)** | **`20260720_0073` on cip** |
| **Next** | Fable/Opus VERIFY CPOR steward parity → H3 only after PASS |

---

## Standing quality bar (Warren 2026-07-20)

Locked in `docs/WORKFLOW_DUAL_AGENT.md`, import-parity, cip-dual-agent skill:
**Canonical clone or STOP · no half-PASS · never skim · own surface ≠ weaker UX.**
Optimize for UX/architecture/best-in-market — never speed.

---

## CPOR historical import

- H1 PASS; H2 apply + steward/progress parity fix on branch (VERIFY pending)
- Smoke earlier: `H2-SMOKE-556` applied OK

---

## Backlog prune (2026-07-20 / re-audit 2026-07-21)

- Opus CONSULT READY prune; then re-audit removed **043** + **072** (were wrongly kept)
- **49** remain in `docs/BACKLOG.md`
- **069 Done:** shared `StewardWorkspaceViewportShell` (DSI + shipment)
- Ignored: Supabase pooling (002), EU redeploy (003)

---

## Parked — DSI unified multifile

- Branch `feat/dsi-unified-multifile` @ `2c2391e`; stash `park-dsi-asus-dealer-name-automap`

---

## Do not

- Half-parity PASS; push main; auto-create dims; waterfall rewrite of settled Results
- Revive Supabase pooling / redeploy work while local cip is the topology
