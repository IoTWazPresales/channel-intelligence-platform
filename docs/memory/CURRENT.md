# Current state

**Last updated:** 2026-07-12 (audit-gap fixes: shipping UTC overdue parity, stock-health empty UI, related nav, exclude merged customers, WoC, OPEN_CHANNEL loser guard, shipping attribution TTL cache)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | see git (uncommitted audit fixes on working tree) |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip — no new migrations |

---

## Shipped this session

| Item | Status |
|------|--------|
| Related-name groups U1+U2 + alias seal + redirect-follow | pushed earlier |
| OPEN_CHANNEL repair + alias backfill | applied on cip earlier |
| Shipping overdue smart-preset ? KPI UTC alignment | implemented (uncommitted) |
| Dashboard stock-health empty state (no `{}`) | implemented (uncommitted) |
| Related names nav + customers toolbar link | implemented (uncommitted) |
| Customers list excludes merged by default | implemented (uncommitted) |
| Channel-ops weeks-of-cover: sum(vel) + max 104w | implemented (uncommitted) |
| OPEN_CHANNEL cannot be merge loser | implemented (uncommitted) |
| Shipping attribution context 45s TTL cache | implemented (uncommitted) |

---

## Proven smoke (local)

- Customers default **4908** / `include_merged=true` **5049**
- Overdue KPI **827** = overdue chip grid **827**
- Shipping `/lines` warm ~**0.4s** (was ~17s cold before cache)
- Channel-ops weeks_of_cover ~**69** (was ~143k)
- Dashboard: empty stock-health copy, no `{}`

---

## Next

1. Commit + push audit-gap fixes (Warren ask)
2. Fable VERIFY / soak Related merge + re-upload
3. Distributors related-names; lineup multi-folder (fresh chat)
4. Test-fixture customer cleanup (optional)
