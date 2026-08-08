# CURRENT state

**Last updated:** 2026-08-08 (PR #18 merged — Unit 6c + 6f / D-040 on main)

**Branch:** `main` @ `d9857ee` (merge of `feat/unit6f-distributor-attribution-confirm`)

**Alembic:** `20260807_0010` (distributor_attribution_status on commercial_lineup_line) — applied on local `cip`

## Done

- **PR #18 MERGED:** Unit 6c (BACKLOG-112 / D-038/D-039) + Unit 6f (D-040 propose→confirm).
- Browser smoke PASS (signed in): `/admin/po-management` → Distributor attribution review
  shows **Proposed 1016**, `token_proposed` rows, Soft-clear / Run confirmer / Override.
- cip remediation already applied (backfill, confirmer, homeless→Stylus 45; DCC left).

## Next

1. **BACKLOG-124** — empty_token (mandate).
2. BACKLOG-125 / 126 residual stems without ship sole.
3. BACKLOG-127 DAP confirmer / BACKLOG-128 Stylus PO-link when TRIGGER fires.
4. Roadmap A1∥A2∥A3 only after Warren confirms 124 handling.

**Env:** local Windows. `cip` @ `20260807_0010`.
