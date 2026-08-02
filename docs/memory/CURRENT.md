# CURRENT state

**Last updated:** 2026-08-02 (POD foundation merged to main; A2-04/05 audit)

**Branch:** `main` @ `094c3ee` (merge of `fix/commercial-foundation-pod`) · prior schedules work remains on `feat/report-schedules-beat` (PR #17) tip `2ae6192` pushed

**Alembic:** `20260802_0009` on cip / code head (sticky POD view)

## Done (this session)

- **Merged** `fix/commercial-foundation-pod` → `main` (`094c3ee`) and pushing — same-day; carries real cip data changes.
- **WoC note:** cover rising ~13.6 → ~25.0 weeks is the **correct** consequence of sticky POD backfill (more landed stock in the WoC cover calc). Not a regression.
- **BACKLOG-088 / P1-D004:** sticky POD on observation + fact upsert + `shipment_evidence_current` view; fact backfill **5961** rows (156 remain without evidence POD).
- **YoY coverage (A3-04):** empty current quarter → `has_data=false`, YoY null + vintage.
- **OPEN_CHANNEL:** absorb clone-proof then cip (skip re-audit).

## Next

1. A2-04/05 existence audit — tree already has A2-U2 (`norms_and_comparable`); close doc drift + any axis-display gaps; do not rebuild.
2. Merge PR #17 / #16 when ready; B-lane UI only after SKU economics steward seed.
3. Remaining residual: P4–P6 / Q-004 CST formats.

**Env:** local Windows. API `:8001`, web `:3000`.
