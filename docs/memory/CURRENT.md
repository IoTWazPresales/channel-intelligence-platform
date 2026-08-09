# CURRENT state

**Last updated:** 2026-08-09 (Client RAW re-ingest Takealot/Evetech/Game)

**Branch:** `feat/p4-cst-six-customer-shapes` → **PR #26**

**Alembic on cip:** `20260808_0011` (head)

## Locked rules

- CST unmappable → Ignore → catalogue gaps (`source=cst`). Never auto-create PM.
- Game ≠ new structure_type — dual_header + wide-week unpivot.
- P5: live fetch now; intelligence v1 → BACKLOG-130 (≥14d obs).

## Proven

| Item | Proof |
|---|---|
| Takealot W31 from Client RAW | job **927** → **24** seeds confirmed → `customer_listing` takealot |
| Evetech Sales | job **925** → **44** proposed (Web ID); no auto-URL — human paste |
| Game W27 wide-week | job **928** → **565** staging rows across **6** periods |
| Amazon soak | 51 listings (prior) |

**Folder:** `…\Retail\Client RAW Report\` (Takealot / Evetech / Game)

## Next

1. Evetech: paste PDP URLs on Feed proposals (44 left)
2. Optional: poll takealot listings; worker/beat for history
3. Promote PR #26 when Warren asks

**Env:** local Windows. `cip` @ `20260808_0011`.
