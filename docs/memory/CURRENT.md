# CURRENT state

**Last updated:** 2026-08-18 (BACKLOG-132 mailbox ingest + digest mailer)

**Branch:** `feat/mailbox-ingest-shipping`

**Last content pin:** `847aaf8` — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0018` (`20260818_0018_report_delivery_email_channel.py`)

**Alembic on cip:** `20260818_0018` (head) — applied 2026-08-18 (Warren: upgrade and send)

## On this branch

- Mailbox ingest (Gmail IMAP) → inbound shipments apply. Digest after shipment apply only (not DSI).
- Job 1159 digest mailed 2026-08-18 to Leigh_Sharpe, Wayne_Holt, Kyle_Chung, Theshan_Naidoo, Warren_Eliason @asus.com. From `warren.eliason@gmail.com` via smtp.gmail.com **465**. Layout: group by distributor, sort by customer. `CIP_SHIPPING_MAILER_SEND=1` is local env, not committed.

## Last recorded test snapshot

`pytest tests/test_shipping_digest.py tests/test_shipping_digest_send.py` **17 passed**. Live SMTP: audit rows 12–16 delivered. Alembic `20260818_0018` on cip.

## Next

1. Merge this branch to main (Warren instructed). Recipients continue checking mail.
2. Do not re-audit IMAP/Graph.

**Env:** local Windows. Web `:3000` + API `:8001`. No Docker.
