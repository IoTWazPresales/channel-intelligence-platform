# Current state

**Last updated:** 2026-07-11 (U5a+U5b alias seal + redirect-follow; OPEN_CHANNEL repair applied on cip)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | see git |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip — no new migrations |

---

## Shipped this session

| Item | Status |
|------|--------|
| Related-name groups U1+U2 | pushed earlier |
| Search debounce | pushed earlier |
| U5a merge mints global loser-name aliases | committing |
| U5b DSI resolve follows `merged_into_customer_id` | committing |
| Backfill script for prior merges | applied on cip (89 minted); script in repo |
| OPEN_CHANNEL wrong-merge repair | applied on cip (TMP-19 ? system id=1); script in repo |

---

## Next

1. Fable VERIFY / soak Related merge + re-upload
2. Optional: block UI from merging OPEN_CHANNEL as a loser
3. Distributors related-names; lineup multi-folder (fresh chat)
