# Current state

**Last updated:** 2026-07-11 (related-master U1+U2 implemented, uncommitted; search-debounce WIP still dirty)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `feat/channel-ops-kpi-and-gap-scan-perf` |
| **HEAD** | see `git rev-parse --short HEAD` (last pushed: BACKLOG-074 U4g docs pin) |
| **PR** | Not opened |
| **Alembic (DB)** | **`20260710_0072`** on cip — no new migrations |

---

## In progress (uncommitted)

**Related-master customer groups (Fable CONSULT READY ? U1+U2):**
- Detector: anchored token-prefix containment + guarded root similarity
- `GET /api/v1/customers/duplicate-groups/related`
- Merge via existing preview/confirm with `similarity_key=related:<anchor>` + subset select
- UI tab **Related names (review)** on `/admin/customers/duplicates` — no `return_job` / revalidate bounce
- Tests: `test_customer_related_master_groups.py` 7/7; related merge cases in `test_customer_full_merge.py` green

**Also dirty (separate):** master search debounce (`useDebouncedUrlQuery*`) — do not mix into related-master commit.

---

## Next

1. Commit related-master U1+U2 (explicit paths) ? Fable VERIFY ? push
2. Optional: commit search debounce separately
3. Distributors related-names (U3) when prioritized
4. Lineup multi-folder + browser/DB audit (fresh chat)

**Do not:** expand alias-scope return_job pattern to related tab; auto-merge; non-anchored shared-root clusters in v1.
