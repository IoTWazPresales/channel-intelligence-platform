# CURRENT state

**Last updated:** 2026-08-08 (BACKLOG-124 tokenless empty_token on feature branch)

**Branch:** `feat/backlog-124-empty-token` (from `main` @ `c312375`)

**Alembic:** `20260807_0010` — applied on local `cip`

## Done

- **PR #18 MERGED** (Unit 6c+6f / D-040) on main.
- **BACKLOG-124 IMPLEMENT** (this branch): Mechanism D tokenless customer stamp —
  per-case `empty_token` worklist items; `…/tokenless/preview|apply` stamps
  `customer_id` by `line_ids` only (no alias, no invented token); ship/PO hints
  never auto-picked; free pick + confirm. Browser smoke PASS (Empty token 20,
  case 127 preview Evetech 52 · cancel, no write).

## Next

1. Commit + push `feat/backlog-124-empty-token`; open/merge PR when Warren asks.
2. BACKLOG-125 / 126 residual stems without ship sole.
3. BACKLOG-127 DAP confirmer / BACKLOG-128 Stylus PO-link when TRIGGER fires.
4. Roadmap A1∥A2∥A3 only after Warren confirms 124 handling closed on main.

**Env:** local Windows. `cip` @ `20260807_0010`.
