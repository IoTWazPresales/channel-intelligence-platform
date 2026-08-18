# CURRENT state

**Last updated:** 2026-08-18 (shipping-mailer recipients U1+U2)

**Branch:** `feat/shipping-mailer-recipients`

**Last content pin:** `2b2e552` on `main` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`)

**Alembic on cip:** `20260818_0019` (head) — GRANT to role `cip` applied (migrate owner). Table seeded on first Settings GET.

## On this branch

- Table `shipping_mailer_recipient` + unique `(tenant_id, lower(address))`. Casing preserved.
- Digest send list is `resolve_shipping_recipients` (empty → seed five; any rows → enabled subset; all disabled = mute).
- Admin API + Settings section *Shipping digest recipients* (`features/shipping-mailer`).
- Browser-proven 2026-08-18: GET seeded five; POST/PATCH/DELETE smoke row; list back to five.

## Last recorded test snapshot

`pytest tests/test_shipping_mailer_recipients.py` **14 passed**. Vitest panel + settings page **9 passed**.

## Next

1. Merge to `main` when Warren says (VERIFY PASS).
2. Do not re-audit IMAP/Graph/job 1159. Alembic `20260818_0019` is already on this cip.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
