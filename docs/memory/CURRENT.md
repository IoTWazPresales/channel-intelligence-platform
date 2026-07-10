# Current state

**Last updated:** 2026-07-10 (PR #7 merged to main ù BACKLOG-061 Theme B)
**Verify git:** `git branch --show-current` ù `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` |
| **HEAD** | `8866bbe` |
| **PR** | [#7](https://github.com/IoTWazPresales/channel-intelligence-platform/pull/7) ù **merged** |
| **Alembic (DB)** | **`20260710_0072`** on cip |

---

## What shipped (PR #7)

- BACKLOG-061 Theme B: MasterDataGridShell + customer/distributor promote-in-place (map, mint, park/exclude)
- U-G2 / U-B2 / U-B3a / U-B3b Fable PASS
- Migrations through `20260710_0072` (distributor code mint setting)

---

## Next

1. Optional human soak: `/admin/customers` + `/admin/distributors` promote/disposition.
2. New feature branch when next TRIGGER fires ù likely BACKLOG-073 (import-job fact purge) if Warren prioritizes junk cleanup.
3. CI note: GitHub Actions `pnpm/action-setup` fails on version clash (`version: 9` vs `packageManager: pnpm@9.15.9`) ù infra fix, not Theme B.

**Do not re-audit:** U2a/U2b/U-D1/U-G2/U-B2/U-B3a/U-B3b PASSes.
