# CURRENT state

**Last updated:** 2026-08-10 (P4 apply soak + Lane B export/hard-budget + 089 + 076)

**Branch:** `feat/p4-cst-six-customer-shapes` → **PR #26** (promote when CI allows / Warren)

**Alembic on cip:** `20260808_0011` (head)

## Locked rules

- CST unmappable → Ignore → catalogue gaps (`source=cst`). Never auto-create PM.
- Game ≠ new structure_type — dual_header + wide-week unpivot.
- Listing↔CPOR activation = point-in-time vs `cpor_case_line.srp`; `no_case_detected` when none.
- B2 export sheet titles = **tenant profile** (not OEM hardcoding).
- A2-X incremental unit cost = baseline FLAG-first (not A2-06 rename).

## P4 forward soak (2026-08-10)

| Customer | Job | Facts after apply | Notes |
|---|---|---|---|
| Takealot | 927 | 20 | already had facts; re-apply ok |
| Evetech | 925 | 37 | |
| CM | 917 | 78 | MTD week29 |
| IC | 912 | 82 | |
| HiFi | 913 | 51 | |
| Makro | 903 | 47 | |
| Game | 911 | 3 | W33; W27 wide-week 928 still unresolved |
| Amazon | 918 | **0 FLAG** | 51/51 products unresolved — sample not forward-week PM match |

## Also shipped this arc

- Lane B: tenant export sheet names in profile; B4 `create_blocked` when hard enforce **or** `over_budget_action=block`
- BACKLOG-089 FLAG-first incremental metric on portfolio + UI tile
- BACKLOG-076: 17 suspect inbound amounts quarantined (amount→0 + stamp)

## Next

1. Promote PR #26 (CI has pre-existing unrelated failures — use admin merge or fix tip tests)
2. P5: upload CPOR → re-poll activation; Takealot SPA fetch
3. Q-013 / Q-014 Warren picks; BACKLOG-010 only with backup+approve
4. CST historical backfill after forward soak trusted

**Env:** local Windows. `cip` @ `20260808_0011`.
