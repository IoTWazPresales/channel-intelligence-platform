# CURRENT state

**Last updated:** 2026-08-10 (arc complete — PR #26 merged)

**Branch:** `main` @ `86c0540` (merge PR #26)

**Alembic on cip:** `20260808_0011` (head)

## Locked rules

- CST unmappable → Ignore → catalogue gaps (`source=cst`). Never auto-create PM.
- Game ≠ new structure_type — dual_header + wide-week unpivot.
- Listing↔CPOR activation = point-in-time vs `cpor_case_line.srp`; `no_case_detected` when none.
- B2 export sheet titles = **tenant profile** (not OEM hardcoding).
- A2-X incremental unit cost = baseline FLAG-first (not A2-06 rename).

## Arc shipped (P4 → Lane B → 089 → 076)

| Piece | Result |
|---|---|
| P4 forward soak | 7/8 customers with `fact_customer_sellthrough`; Amazon FLAG (0 facts / unresolved ASINs) |
| Lane B | Tenant lineup export sheet names; B4 `create_blocked` when hard-budget / `over_budget_action=block` |
| BACKLOG-089 | FLAG-first incremental unit cost on portfolio + UI tile (`cpor-incremental-unit-cost`) |
| BACKLOG-076 | 17 suspect amounts quarantined; KPI FLAG exclusion remains |
| PR #26 | **Merged** 2026-08-10 → `86c0540` |

Browser smoke: `/promotions` B4 builder loads; `/commercial-planner/cpor-cases` shows Cost/incremental unit ($155 · 2 ok / 198 flagged).

## Warren decisions still required (not agent-auto)

- **BACKLOG-010** — drop legacy `product_attribute_value` (~2M): only after backup + explicit approve.
- **Q-013** — PURMIDR25005866: pick case 90 vs 127.
- **Q-014** — PURMIDR26009979: pick among 121 / 122 / 128.

## Next (TRIGGER-ready)

1. **P5 residual** — upload CPOR → re-poll activation; Takealot SPA/API fetch.
2. CST historical backfill (after forward soak trusted).
3. **BACKLOG-094** — MAC + price-delta once formulas locked.
4. Demo gate / P2 second-user landing; backup restore soak.
5. **BACKLOG-068** landed-quarter lens when Shipping prioritizes.
6. PO residual triage after Q-013/Q-014 answers.
7. P6 second-tenant config-only onboard.

**Env:** local Windows. `cip` @ `20260808_0011`.
