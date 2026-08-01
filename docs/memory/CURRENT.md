# CURRENT state

**Last updated:** 2026-08-01 (P3-4 authored; **awaiting alembic 0006 apply**)
**Branch:** `feat/p2-auth-rbac` (uncommitted P3-4)
**Alembic:** code head `20260801_0006` — **NOT applied on cip** (still `20260801_0005` until Warren upgrades)

## Done this session

- P3-2 / BACKLOG-097 / P3-3 pushed earlier
- **P3-4 authored:** `saved_report` + `dashboard` + `dashboard_tile`; API `/saved-reports` + `/dashboards`; UI save on `/reports` + `/dashboards` page; personal vs published + role share

## Blocked

1. **Approve `alembic upgrade` to `20260801_0006` on cip** — then browser smoke save/publish/dashboard tiles

## Next after apply

1. Browser smoke: save WoC report → create dashboard → tile shows ~13.6
2. Open PR when ready (not yet)
3. P3-5 export/delivery or X-1 CST VERIFY

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
