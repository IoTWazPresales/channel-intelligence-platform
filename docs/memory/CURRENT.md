# CURRENT state

**Last updated:** 2026-08-05 (PROGRAM-A Unit 2 shipping)

**Branch:** `main`

**Alembic:** `20260802_0009` · no migration this unit

## Done

- **Unit 1** VERIFY PASS `7390921` — PR#17 split land.
- **§0 / Unit 3** prior.
- **Unit 2 (in commit):** property-based bulk protection + `allow_protected` + select-all exclude; case 145 via `CIP_LINEUP_PROTECTED_CASE_IDS`.

## Printed before Unit 2 implement

| id | commercial_status | po_links | covered by |
|----|-------------------|----------|------------|
| 7 | po_issued | 1 | status + links |
| 90 | po_issued | 23 | status + links |
| 122 | po_pending | 28 | status + links |
| 145 | draft_imported | 0 | **config set only** |

## Next

Unit 2 VERIFY → Unit 4 contested residual (Q-012).

**Env:** local Windows. `cip`. Local `.env` has `CIP_LINEUP_PROTECTED_CASE_IDS=145` (not committed).
