# Current state

**Last updated:** 2026-07-09 (CPOR U6 ? scaffold reader migration)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/cpor-unit-6-scaffold-readers` |
| **HEAD** | *(update after commit)* ? off LC-U1 tip `a5cca19` |
| **PR** | None open |
| **Alembic (code)** | `20260709_0069` (LC-U1; U6 no new migration) |
| **Alembic (DB)** | **`20260709_0068`** on cip ? **0069 NOT applied** (Warren gate) |

---

## CPOR U6 ? DONE (promo scaffold readers ? CPOR; no schema)

| Item | Status |
|------|--------|
| A1 cpor_xlsx | Documented legacy; U4 CPOR export is canonical |
| A2 promotions UI/API | plans/readiness parked empty; meta parked hint; page banner ? CPOR Cases |
| A3 product_rankings | Re-pointed to `cpor_case_line` |
| A4 product_usage | Added CPOR case lines; kept old promo checks |
| A5 seed | Stopped FactPromotionPlan seeding |
| A6 template | promotion_plan disabled (U5 already added cpor_claim_evidence) |
| A7 DSI `_has_cpor_data` | Wired to non-cancelled `cpor_case` count |
| A8 nav | No /promotions nav entry (already absent); page parked in place |
| Tests | 6 U6 + DSI awareness green |
| Next | Fable verify ? BACKLOG-072 ? BACKLOG-061 |

---

## HARD GATE

**Apply `20260709_0069` on cip only after Warren explicit approval** (LC-U1 listing tables).

---

## Prior units (tips)

| Unit | Tip |
|------|-----|
| LC-U1 | `a5cca19` |
| U4.6 | `c593677` |
| U5 | `a1b6e84` |
