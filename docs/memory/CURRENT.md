# CURRENT state

**Last updated:** 2026-08-07 (PROGRAM-A Unit 6 merged to main)

**Branch:** `main` @ `f49a7c8` (pushed; in sync with `origin/main`)

**Alembic:** `20260802_0009` (unchanged)

## Done

- **PROGRAM-A Unit 6 merged** (fast-forward `189246c`→`f49a7c8`): 6a unlink (BACKLOG-109 / D-037) + 6b customer-token stamp (BACKLOG-112 path) + first live `opts.target` (PROVEN).
- Ship-candidate scope via `commercial_lineup_case_po`→PO→shipment (`09506fa`) — architecture fix, not a workaround.
- Stampable 112 residual cleared in browser (sadc-compuspeed→107, mitsumi distribution→18). stampable-left=0.
- Smoke: stamp confirm + opts.target success; unlink dialog open/cancel (no unlink write).

## Next

1. **Residual genuine_conflict** (~53 unresolved-with-token): steward routing only — SCOPED / MERGE / DATA_ERROR. Agent must not pick winners.
2. **BACKLOG-124** — empty_token (~939 lines): parked until empty-token blocks planning.
3. **BACKLOG-123** — promote/merge → ResolutionWorklist: parked; opts.target already PROVEN; TRIGGER = promote/merge migration.
4. **Roadmap (v3.1):** P1 exited; startable lanes **A1 / A2 / A3** (∥ allowed) + continuous **X**. PROGRAM-A residual steward queue is done for stampable path — next PROGRAM unit only if Warren names one.

**Env:** local Windows. `cip`.
