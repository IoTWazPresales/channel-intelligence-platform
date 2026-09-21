# N-0033 implementation baseline — observed at `ff118ec` (pre-gate)

**Run:** `STAGE3_ACCESS_20260921` · **Actor:** `stage3-001` · **Date:** 2026-09-21 · **Provenance:** implementation-observation

## Observed behaviour before change

| Surface | Observed |
|---|---|
| `apps/api/.env` | 0 bytes → effective `cip_auth_mode = stub`; every unauthenticated request resolved to `admin@local` ADMIN; `X-User-Role` / `X-User-Id` honoured (forgeable). |
| Session mode, per-endpoint auth | With `CIP_AUTH_MODE=session` set, a live enumeration of 207 sampled GET routes returned **200 with no token on 127**, 401/403 on 35 — customers, products, distributors, imports, CPOR settlement/pivot/events/exports, lineup, budgets, dashboards, saved reports, steward queue, `GET /api/v1/dev/database-wipe`. 23 endpoint modules used `get_optional_current_user` ("public reads"). |
| Web | `next dev` on `:3000` bound to all interfaces by `start` script; same-origin `/api/v1` proxy to loopback `:8001`; `redirectToLoginOn401` in `lib/api.ts`; `/login` page exists. |
| External access | None. cloudflared not installed. `winget` not on any tool-shell PATH. |
| Users | `app_user`: `admin@local` (admin), `viewer@local` (viewer), both with password hashes (PBKDF2-SHA256 × 260k); 68 `auth_session` rows. Passwords set by Warren on 2026-09-21 before the mode flip. |

## Latent capabilities to preserve

- Stub mode behaviour for local dev and the pytest suite (conftest pins `CIP_AUTH_MODE=stub`)
- `/auth/login`, `/auth/logout`, `/auth/me`, user CRUD and admin password reset
- `redirectToLoginOn401` client behaviour and the `/login` page
- Same-origin Next proxy to `127.0.0.1:8001`; `/docs` and `/openapi.json` reachable only on `:8001`
- `ALLOW_DB_WIPE` gate on `POST /dev/database-wipe` (default False)
- Existing endpoint-level `require_roles` (e.g. `shipment_evidence.py` ADMIN-only) — unchanged, now additive on top of the router gate
