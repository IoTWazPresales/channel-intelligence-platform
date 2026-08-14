# Demo script — manager walkthrough

**Purpose:** First-class demo artifact (charter). Walk a second user through CIP without the builder in the loop.

**Last proven:** Unit 8 Demo/P2 gate re-walked 2026-08-14 — see `docs/UNIT8_DEMO_P2_GATE.md`.

**Hosting:** deferred (P2-1). This script assumes local topology: web `:3000`, API `:8001`, DB `cip`.

---

## Preconditions

1. Admin has created the guest account on **Admin → Users** (role `viewer` or `planner`).
2. Guest knows email + temporary password (admin used **Reset password** if needed).
3. Stack is up (`pnpm dev:api` + `pnpm dev:web`).

---

## Spine (say this)

| Step | Where | What they should see | What you say |
|------|--------|----------------------|--------------|
| 1 | `/login` | Channel Intelligence sign-in | “Your account — not a shared laptop login.” |
| 2 | `/dashboard` | **Control tower** — welcome by name, freshness banner, KPIs, recommended actions | “Landing is state of the business + what needs attention.” |
| 3 | Shortcut or nav → **Plan vs executed** | Plan-accuracy / shipped fill surface loads | “Plan vs reality from shipped facts — not a spreadsheet guess.” |
| 4 | Nav → **Promotions** or **CPOR Cases** | Promo / case list (role permitting) | “Support spend and case outcomes live here.” |
| 5 | Nav → **Lineup** (planner+) | Lineup author / cases | “Next-quarter lineup is authored in CIP, not only imported.” |
| 6 | Nav → **Inbox** | Scheduled / delivered reports with vintage | “Reports land with freshness declared.” |
| 7 | (Optional) Admin-only pages as viewer | **Users** / **SQL viewer** refuse or hide | “Roles are enforced — viewers consume, admins configure.” |

---

## Numbers to expect (local cip — refresh when data moves)

Do not invent KPIs. Read Control tower + owning surfaces live; note plausible ranges for the room:

- Freshness: newest completed import age (hours/days) from Control tower banner
- Exceptions / failed jobs: Control tower tiles
- Plan vs executed: quarter window with lineup coverage (credible core 26Q1 → current)
- CPOR: case list non-empty after payment-evidence / historical loads

If a tile is empty, say so — empty is better than a wrong story.

---

## Out of scope for this script

- Remote URL / hosted deploy (Q-003 / P2-1)
- Self-serve email password reset (admin set-password is the local bar)
- Full import steward deep-dives (separate operator runbooks)
