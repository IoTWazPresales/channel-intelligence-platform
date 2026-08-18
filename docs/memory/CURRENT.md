# CURRENT state

**Last updated:** 2026-08-18 (BACKLOG-132 merged to main)

**Branch:** `main`

**Last content pin:** `eb73232` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head) — applied 2026-08-18 (Warren: upgrade and send)

## On main

- Merged `feat/mailbox-ingest-shipping` @ `eb73232`. Mailbox ingest (Gmail IMAP) + post-apply shipping digest mailer. Job 1159 mailed to the five ASUS addresses from `warren.eliason@gmail.com` (SMTPS 465). Layout: group by distributor, sort by customer. `CIP_SHIPPING_MAILER_SEND` stays in local `.env` (not committed). DSI apply does not send.

## Last recorded test snapshot

`pytest tests/test_shipping_digest.py tests/test_shipping_digest_send.py` **17 passed**. `pnpm lint` 0 errors. `pnpm test:web`: 534 passed, 1 unrelated timeout (`CustomerBulkPromoteDialog.test.tsx`).

## Next

1. Recipients check the mailed digest. New theme → new branch off `main`.
2. Do not re-audit IMAP/Graph.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
