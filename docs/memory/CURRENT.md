# CURRENT state

**Last updated:** 2026-08-07 (PROGRAM-A Unit 6b IMPLEMENT — awaiting VERIFY)

**Branch:** `feat/unit6a-po-unlink` (6a+6b sequential)

**Alembic:** `20260802_0009` (unchanged)

## Done

- **Unit 6a** `d1d9000` / pin `b9756bd` — Opus VERIFY **PASS**. BACKLOG-109 closed.
- **Unit 6b** (c143c94) — customer-token stamp (C) + first live `opts.target`:
  - Service `lineup_customer_token_stamp.py` (preview/apply/revoke + worklist)
  - API stamp/preview/apply/revoke + worklist + minted-aliases
  - `CustomerTokenWorklistSection` on Po Management (requiresTarget + applyAdapter opts.target)
  - BACKLOG-124 tokenless; BACKLOG-112 in progress
  - pytest 5/5; vitest 3/3

## Next

Opus **VERIFY** 6b → must declare `opts.target` **PROVEN** or STOP. Then PROGRAM-A Unit 6 queue empty / merge PR.

**Skip re-audit:** D-032…D-037, Unit 2, S10 (PoAutoLink), 6a unlink.

**Env:** local Windows. `cip`. Local `.env`: `CIP_LINEUP_PROTECTED_CASE_IDS=145` (not committed).

