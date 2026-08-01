# CURRENT state

**Last updated:** 2026-08-01 (P3 complete)
**Branch:** `feat/p2-auth-rbac` @ P3-6 pending commit
**Alembic:** `20260801_0008` on cip

## Done this session

- **P3-1…P3-5** already live (semantics → query → builder → dashboards → export/inbox)
- **P3-6 SQL viewer:** admin-only `/admin/sql-viewer`; read-only gate + 5s timeout + row cap; `sql_viewer_audit`; browser smoke PASS (`current_database=cip`, DELETE refused, audit shows who-ran-what)
- Nav: SQL viewer **admin only** (viewer/planner/steward gated out)

## Next

1. Open PR for `feat/p2-auth-rbac` (P2+P3) when Warren asks
2. **X-1 CST Unit E VERIFY** (prefer dedicated chat)
3. Lane B / other ROADMAP after merge

**Env:** local Windows. API `:8001` session, web `:3000`. Seed `admin@local` / `changeme`.
