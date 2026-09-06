# CURRENT state

**Last updated:** 2026-09-06 (Stock Cover lens migrated from design-lab)

**Branch:** `feat/ns-2-brief-nav-collapse`

**Last content pin:** Cover lens + Stock chrome on `feat/ns-2-brief-nav-collapse` (hash on CONTEXT changelog after commit)

**Alembic (code):** `20260906_0022` (`cpor_case.intelligence_exclude`)

**Alembic on cip:** `20260906_0022` (clone-tested on `cip_alembic_smoke`, then applied; `current_database=cip`)

## On feat/ns-2-brief-nav-collapse

- **Product (Stock chrome):** DomainHeader + five lab lenses on `/stock`, `/channel-intelligence`, `/forecasts`. Default lens is cover. `/stock?lens=inbound` stays Supply.
- **Product (Stock Cover):** Lab Cover structure on `CoverLensView` (headlines, 6-bucket histogram, sell-out vs shipped, ScopeBar, pair grid, context panel). Numbers from `weeks_of_cover_observation` on cip — not lab fixtures. I2 / BACKLOG-164 closed earlier this wave (stored score + explanation). `/market` stub untouched.
- **Product (Unit 5):** Seven explicit fixture/smoke cases flagged `intelligence_exclude` (not deleted). Default lists, chips, ageing, comparables, norms, portfolio, settlement book, brief open-case counts and incremental-cost summary are commercial-only (304 cases). Reversible Test data chip + workspace switch. Do not ILIKE `%test%`.
- **Product (Units 2–4):** `evidence_basis` derived; booked FX mode declaration; case find filters; Est. units on settlement lines. N-0006 not started.
- **Product (Unit 1):** Booked FX lifecycle extends declared `roe_snapshot`. Daily USDZAR from Frankfurter (ECB); last-known fallback never blocks a case.
- **Product (Unit 0):** Promotions & Funding desktop dimensions migrated from design-lab source at 1280×800.
- **I1–I5:** I1/I3/I4/I5 remain closed. **I2 closed** (BACKLOG-164): stored score + explanation, no factor panel.
- **Programme:** PRG-20260831T145514; `verify` ok rev **295**; `frontier` is **only N-0006**. Do not start N-0006 (BACKLOG-170). Do not reopen N-0013, D-0008 or D-0009. Container migration is **not** a lawful new node this session (BACKLOG-171 instance 4); product work continues under accepted D-0008.
- **D-0009 accepted:** Actions fold into Attention. Ledger still uncommitted.
- **D-0002** remains the open decision.
- **Next:** Stock Movement lens (lab 4 headlines + SOH-vs-sell-out TrendChart + family CategoryBars). Relocate Channel Ops nested tabs rather than deleting them.

**Programme frontier:** N-0006 only. Do not manufacture a path. BACKLOG-171 instance (4): no covering node for this wave.

**Design language:** FROZEN v1.1 is **demoted**. Production funding follows the implemented design-lab React, including lab-specified dimensions.

**Deferred:** BACKLOG-173 (EIF NO_PROGRESS fingerprint on reads). Budget ledger writer not chartered. Floating FX re-rate after approval is not implemented (mode exists; booked is the norm). CIP cases absent from the pending report (47) observed, not acted on. C23C16234 not auto-flagged.

**Env:** local Windows. Web `:3000` + API `:8001`. Local API currently 500s on `/api/v1/*` including `/auth/me` — Cover UI empty in browser; SQL via sync engine on `cip` still works.

**Programme frontier:** N-0006 only. Do not manufacture a path. BACKLOG-171 instance (4): no covering node for this wave.

**Design language:** FROZEN v1.1 is **demoted**. Production funding follows the implemented design-lab React, including lab-specified dimensions.

**Deferred:** BACKLOG-164 I2-only until Market mapping. Budget ledger writer not chartered. Floating FX re-rate after approval is not implemented (mode exists; booked is the norm). CIP cases absent from the pending report (47) observed, not acted on. C23C16234 not auto-flagged.

**Env:** local Windows. Web `:3000` + API `:8001`.
