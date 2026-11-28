# Morning note — 28 Nov 2026 (Africa/Johannesburg)

This is not closure. The deploy did not run. The live checkout was not pulled. 0067 was not applied. Margins were not saved. Nodes were not started. The unresolved EIF mutation (CREATE DATABASE cip_restore_20261127, sqlstate 42501) was not repaired.

## What is on the trunk, and what is live

| | Branch | SHA |
|---|---|---|
| Trunk code, before this docs commit | `feat/integrate-20261103` | `352a5f7a26ab81ea2f40a7ca1ae4e4ca94bedfc9` |
| Live checkout, not pulled | `feat/integrate-20261103` | `f4feb367a8c8982d6e5a3c7b951a8b431f5af297` |

`f4feb367` is an ancestor of `352a5f7a`. The running app on http://127.0.0.1:3000 is the live checkout. BUILD_ID was not read this morning because deploy did not run. There is no new live BUILD_ID.

PRs 135 and 136 are merged. They were not merged again.

Trunk commits after the live checkout, newest first:

| SHA | What |
|---|---|
| `352a5f7a` | Below-SRP tolerance does not fall back to 1.0. Settings can save it. PR 136. |
| `8deb92d3` | Site confirm bar on Monitored listings. Promotions title is the theme h1. PR 135. |
| `aa69befc` | Discovery startup runs when beat is off. Matrix extras reach the readers. Hydration does not PUT. |
| `4b1ff421` | Tenant VAT, currency, margins, timezone. PR 131. Migration file `20261127_0067` is in the tree and was not applied. |
| `08ab9f78` | Planner: a reason is required to end a promotion before sales cover the window. PR 132. Do not merge it again. |
| `f8b38110` | Listings health scope and the shared customer search URL. PR 130. |

## Click-by-click test list

Open http://127.0.0.1:3000. Do not sign in. A redirect to `/login` is the result: stop, and do not authenticate. Switch theme with the sun/moon control in the shell. Dark background seen on the worktree servers was `rgb(20, 22, 26)`. Light background seen on a login page after the toggle was `rgb(243, 245, 247)`.

The rows marked **live** can be clicked on the running app. The rows marked **trunk only** are on `352a5f7a` and are not in the running app until a deploy.

1. **Monitored listings** — http://127.0.0.1:3000/listing-capture
   - **Live.** Open the page. The price matrix is the centre of Monitored listings (step 1, already in `f4feb367`).
   - **Trunk only.** A site confirm bar sits above that matrix, and only on Monitored listings. Price history, Discover sites, and Feed proposals do not mount it. Seen on a worktree server at port 3020, dark: the bar was before the matrix.
2. **Promotions** — http://127.0.0.1:3000/promotions
   - **Trunk only.** The title "Promotion planner" is a theme `h1` at 27px and weight 650. Seen on port 3020 in dark. Light mode redirected to login before that title was read again.
   - **Trunk only.** Ending a customer sell-through promotion before sales cover the window asks for a reason.
3. **Settings** — http://127.0.0.1:3000/settings
   - **Trunk only.** Currency, reporting time zone, VAT rate, VAT by country, promotion types, and channels start blank until saved.
   - **Trunk only.** Below SRP tolerance starts blank, placeholder "Not set". Seen on port 3021 in dark. Light mode went to login before the field was read.
   - Do not save the three margins. Warren sets those.
4. **Discovery** — listing-capture, Discover sites.
   - **Trunk only.** Startup still queues discovery when the dev beat is off, and only for a tenant that has saved both timings. Step 3b (turning discovery on for real) was not done.
5. **Pages that read the new settings**, after a future deploy and only if the keys were saved: a new case with no currency shows not configured; a sell-out row with no VAT basis uses the country rate, then the tenant rate; a shelf price is "Below SRP" only when a tolerance is saved.

## VERIFIED WITH LIMITATIONS

- Tests ran on `cip_test`, not on `cip`. No test wrote to `cip`.
- Browser checks used worktree dev servers (ports 3018, 3019, 3020, 3021), not the live app on port 3000 after this trunk. No login was posted.
- Dark promotions title and the confirm-bar order were seen. Light theme on those pages was not read, because the browser was sent to `/login`.
- Discovery library proof exited 0 (14 libraries, `works=yes`). Proposal counts on `cip_test` were `proposed_customer_web_site=0` and `proposed_cst_listing_seed=0`. No discovery writer ran, so there is no separate after count.
- Codex: listings r2 PASS, planner r2 PASS (r1 on monthly coverage was not accepted; the tested contract is period end), tenant settings r2 PASS, discovery PASS, follow-ups r2 PASS, below-SRP tolerance PASS.
- Live `alembic_version` was read earlier this run as `20261123_0066` with `current_database()` `cip`. It was not read again for this note. 0067 was not applied.

## Backup refusal

`pg_dump` as role `cip` failed. `current_database()` was `cip`. `current_user` was `cip`, not a superuser, and `rolbypassrls` was false. `budget_ledger_entry` is owned by `postgres` with forced row security. The error was: query would be affected by row-level security policy for table `budget_ledger_entry`. The select policy depends on `cip.product_lines`, so a dump that honours row security would omit rows. 53 public tables have row security. There is no `pgpass` file and no admin URL in the API env. The postgres password was not guessed. The dump was not retried as `cip` after that finding.

The partial file `cip_20261128_021330_pre-deploy.dump` (892656 bytes) was deleted.

The last complete dump is `C:\Users\warren_eliason\channel-intelligence-platform\.tmp\backups\cip_20261126_205640_pre-step1-4a.dump`. Header `PGDMP`. Size 3375201234 bytes. That file is from 26 Nov. It is not a backup from this morning.

`cip-deploy.ps1` was printed as a plan only. `-Execute` was not run.

## Clone, 0067, margins

- Clone: the app role on database `postgres` got sqlstate 42501 on `CREATE DATABASE cip_restore_20261127`. Passwordless user `postgres` did not connect. The command did run. It was not repaired and was not retried. The four 0067 proofs on a clone were not recorded.
- 0067: the migration file is on the trunk. It was not applied to `cip` and not applied to `cip_test` as a stand-in. Merging the file does not apply it. Deploy did not apply it.
- Margins: not saved. Currency `ZAR` and reporting time zone `Africa/Johannesburg` were not written. Promotion types and channels were not written. Nothing on live settings was changed.

## Line-up gaps (still open)

These were not changed on 28 Nov.

- A line-up case has `inferred_period_start` and no period-end column. A case whose start is on or before today still supplies an SRP.
- Warren's words were accepted cases only. The code still treats `accepted` or any later ladder status (`po_pending` through `work_closed`) as accepted. That wider set is an assumption recorded in `lineup_case_status.py`, not a new decision.
- The VAT-inclusive chain figure `srp_inc_vat_local` is used first. When it is absent, `msrp_local` is used. The column does not say whether `msrp_local` is VAT-inclusive.

## Retry summary

- Worktree as the shell directory was refused (`WORKTREE_ROOT_UNSUPPORTED`). Commands ran from the repo root with `git -C` and `pnpm --dir`.
- `CREATE DATABASE` failed once (42501). Not retried.
- `pg_dump` as `cip` failed. A second run only captured a redacted error. Not run again.
- Codex on the planner and on tenant settings failed once on real or rejected findings, then passed. Follow-ups failed once on a fixture name (`North shop`), then passed after that name was removed. Discovery and the tolerance change passed on the first review.
- Visual light-theme reads lost a race to `/login`. Not treated as a product failure. Not looped.
- No push to `main`. No force-push. The discovery commit `874fd6e0` was already inside the pushed discovery tip before an instruction arrived to leave it unpushed. It was not rewound.

## WARREN list

His decisions only, quoted. Sources are the overnight instruction and the step handoff that records his 27 Nov decisions.

26 Nov, price chain: "use sell out price, fall back to Line up price, fall back to website off promo price."

26 Nov, line-ups, as recorded in `price_matrix.py`: "the line-up has the price excluding and including VAT. The shelf basis is the VAT-inclusive figure, read as stored: the price chain's explicit `srp_inc_vat_local` first, `msrp_local` when the chain does not carry it." And, same date, as recorded in `lineup_case_status.py`: "ONLY ACCEPTED ONES FFS."

26 Nov, page title, as recorded on the step 4b tracker: "Yes" — the element is an h1.

27 Nov, VAT, currency, margins, time zone: "VAT comes from the row, else the data's country, else the tenant rate. Currency, the three margins and the reporting timezone are tenant settings, and unset means not configured."

27 Nov, ending a promotion early: "Manual end of a promotion before the sales cover the window is ALLOWED, with a reason required, the actor stamped and a flag so settlement still sees the gap."

27 Nov, discovery, quoted from `docs/handoffs/2026-11-24/steps/04-step3-discovery-libraries-autodiscover.md`:

1. "`ultimate-sitemap-parser==1.8.2` (GPL-3.0-or-later) is added and reads product-page sitemaps through `web_discovery/sitemaps.py`. Every sitemap request still goes through the robots check and the site's pacing. `web_discovery/pages.py` (domain detection) keeps its own sitemap reader."
2. "`listing_seed` is a source of a site again in product-page discovery: a named marketplace, a domain or origin seed, and the seed's site fields copied onto blank site fields, plus confirmed web sites. Domain detection (`candidates.py`) still does not use the seed host, as the close-off asked."
3. "No crawl-delay floor on top of the site's own rate."
4. "05:20 UTC only wakes the job. The gap is the tenant's saved hours."
5. "Matrix extras stay this browser's last steward save."
6. "`tenant.locale` stays optional."
7. "`372ea058` reformatted shipment, CST, CPOR, DSI, product-master and listing-poll tasks and non-discovery parts of `autoconfig.py` and `tenant_settings.py`. Those edits are reverted. `_site_health` and `capture_health` match the discovery base."

Not his decisions, so not in the list above: the five PR 131 assumptions (plans with no tenant id, whether an unset time zone blocks imports, margins saved as one object, existing rows kept). Those stay open.

## What was not done

Settings save, live proof on port 3000, deploy, node work, and a fresh backup. Closure is not claimed.
