# N-0021 Administration coverage map

**Source (lab, primary):** `apps/web/src/design-lab/surfaces/DomainOverviewSurface.tsx` `AdminSurface` + `apps/web/src/design-lab/shell/labNav.ts` domain `admin`. Lab page `apps/web/src/app/(design-lab)/design-lab/admin/page.tsx` always renders `AdminSurface` and **ignores** `?tab=`.

Judge production against the lab composition, not LabShell rail (BACKLOG-181).

**NUMBER RULE** (`current_database()=cip`, measured 2026-09-13). Lab figures are class **(i) fixture**. Production headlines are class **(iii)**. Never change a number to make two surfaces agree.

| Headline / panel | Lab fixture (i) | Production grain | cip (iii) | Class |
|---|---|---|---|---|
| Users | 14, caption “3 admin · 4 steward · 5 planner · 2 viewer” | Active `app_user` (`is_active`) by `role` | **2** (1 admin · 0 steward · 0 planner · 1 viewer) | (iii) |
| Background jobs running | 2, “Celery · DSI apply…” | `import_job.status='running'` and `archived_at` is null | **0** (64 pending are queued, not running) | (iii) |
| Failed jobs (24h) | 1 | `import_job.status='failed'` in last 24h via `coalesce(completed_at, updated_at, created_at)` | **0** (44 failed still open — different grain) | (iii) |
| Audited SQL queries (7d) | 38 | `sql_viewer_audit.created_at` last 7 days | **0** (8 all-time) | (iii) |
| Operations panel | 3 fixture job rows | Same `import_job` running/pending/failed, newest 8 | pending/failed rows, no running | (iii) |

---

## Lab routes

| Route | Lab SOURCE | Production analog | Coverage |
|---|---|---|---|
| `/design-lab/admin` | DomainOverview: 4 headlines, Operations PanelRows, attention, workflows | New hub at `/admin/users` (rail href unchanged) | **COVERED** |
| `/design-lab/admin?tab=users` | Same page; tab ignored | Relocate Users & roles workspace to `/admin/users/list` | **COVERED** |
| `/design-lab/admin?tab=ops` | Same page; tab ignored | `/admin/ops` wrapped | **COVERED** |
| `/design-lab/admin?tab=sql` | Same page; tab ignored | `/admin/sql-viewer` wrapped | **COVERED** |
| `/design-lab/admin?tab=settings` | Same page; tab ignored | `/settings` wrapped | **COVERED** |
| `/design-lab/admin?tab=audit` | Same page; tab ignored | Platform audit log stays **planned** honesty; not wired to steward-audit | **PARTIAL** — planned marker retained |

## Production routes (AS-IS → migrate)

| Route | AS-IS | After N-0021 | Coverage |
|---|---|---|---|
| `/admin/users` | Users & roles workspace | Administration hub (`AdminChrome` + `AdminOverview`) | **COVERED** (hub) |
| `/admin/users/list` | (none) | Relocated Users & roles workspace | **COVERED** (relocate, not deleted) |
| `/admin/ops` | PageHeader + ops workspace | `AdminChrome` wrap; workspace not deleted | **COVERED** |
| `/admin/sql-viewer` | PageHeader + SQL console | `AdminChrome` wrap | **COVERED** |
| `/settings` | PageHeader + settings workspace | `AdminChrome` wrap | **COVERED** |
| `/admin/steward-audit` | Data & Stewardship steward audit | **untouched** — not the planned platform audit log | out of Administration map |
| Rail Administration hrefs/labels | `/admin/users`, `/admin/ops`, `/admin/sql-viewer`, `/settings`, planned audit | unchanged | **COVERED** (no rail IA change) |
| D-0002 mapping queue | `/admin/mappings` | untouched | **out of map** |

BACKLOG-181 lab rail is not the production bar.

---

## Browser 1280×800

Administration is **not** a named DIRECTION section 6 390px workflow — 1280 only.

Viewport via Playwright MCP `browser_resize` 1280×800 (not `browser_cdp`). Waits via Playwright `browser_wait_for`. 2026-09-13.

| Check | Result |
|---|---|
| `/admin/users` hub vs `/design-lab/admin` two-column DomainOverview | **VERIFIED** — both DomainHeader + 4 headlines + Operations PanelRows + attention + workflows. Lab fixtures 14 / 2 / 1 / 38; production cip **2 / 0 / 0 / 0**. Lab attention empty; production 2 live signals (44 failed still open + 64 pending, not labeled running). Lab workflows include live Audit log; production keeps Audit log **planned** honesty |
| Workflows › Users & roles real `<a href="/admin/users/list">` | **VERIFIED** — Playwright `browser_find` `/url: /admin/users/list` |
| `/admin/users/list` still mounts `users-workspace` | **VERIFIED** — DomainHeader crumbs Administration / Users & roles; LensTabs (Users & roles selected); `data-testid="users-workspace"`; directory table still present |
| `/admin/ops` DomainHeader + workspace | **VERIFIED** — crumbs Administration / Operations; LensTabs selected; API readiness + Import jobs workspace (Failed open 44; workspace “Running / pending: 64” is existing ops grain, not the hub running headline) |
| `/admin/sql-viewer` DomainHeader + workspace | **VERIFIED** — crumbs Administration / SQL viewer; audited read-only console still present |
| `/settings` DomainHeader + workspace | **VERIFIED** — crumbs Administration / Settings; settings workspace still present (PageHeader removed) |
| 390 named workflow | not required |

D-0002 mapping-queue disposition untouched. `navConfig.ts` Administration hrefs and labels unchanged. Rail Users & roles remains `/admin/users` (hub).
