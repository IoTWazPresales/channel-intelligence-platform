# CURRENT state

**Last updated:** 2026-08-23 (EIF v0.5.0 upgrade blocked — framework only; mint state unchanged)

**EIF:** compiled `0.4.0-draft` L3 accepted, workspace shell. v0.5.0 Programme Release **not installed**. Installer/product tree is outside CIP `allowed_roots` (`FOREIGN_PATH`); control-plane writes denied. Operator must run v0.5.0 install/migrate/compile from host PowerShell. Do not reuse probe `R20260822192834_EECF1A` as v0.5 evidence. North Star programme **not started**. Details: `.eif/ESCALATION.md` `ESC-20260823-EIF-V050-PROGRAMME`.

**Branch:** `feat/promote-provisionals-run`

**Last content pin:** `0a649df` (main at branch-off) — do not treat a hash in this file as HEAD

**Alembic (code):** `20260818_0019` (`20260818_0019_shipping_mailer_recipient.py`)

**Alembic on cip:** `20260818_0019` (already stamped; no upgrade of cip this session)

**Alembic on cip_test:** `20260818_0018` (OWNER cip)

## On this branch

- Steward mint run, not a build. No migration, no model/service change.
- **Phase B complete (2026-08-21).** `current_database()=cip` at B.1 / B.2 / B.3.
- Customers promoted **4795/4795**, seq **1..4795**, `customer_code_mint_setting.next_seq` **1 → 4796**. Failures: none.
- Distributors promoted **25/25**, seq **1..25**, `distributor_code_mint_setting.next_seq` **1 → 26**. Failures: none.
- Provenance note (same on every row): `system-minted code, BACKLOG-061 bulk mint; recode pending BACKLOG-145`
- `dim_customer.notes_summary` contains that string: **4795** (= promoted).
- `dim_distributor.notes_summary`: **column does not exist**. Shipped path writes `merge_note`. `merge_note` contains the string: **25** (= promoted). Not backfilled onto a notes_summary column. GAP vs the B.3 notes_summary check is structural.
- Queue-depth after: TMP-CUST open **0**; TMP-DIST open **0**; `cpor_case` customer TMP-CUST% **0**. Merged-loser TMP-CUST excluded still **216**.
- BACKLOG-145: recode-after-promote has no path (accepted going in).
- **RBAC program CLOSED at R1–R1d** (on main, inherited).

## Next

Mint is done. Recode when an ERP code is needed (BACKLOG-145). CPOR settlement / MAC / line-windows from `docs/CPOR_SETTLEMENT_SPEC.md` §8 and BACKLOG-135–140. Merge `feat/promote-provisionals-run` (docs) and `feat/steward-queue-depth` when Warren says. **`cip_test` is real test infra — do not drop.**

**Env:** local Windows. Web `:3000` + API `:8001`. `cip_auth_mode` default in `config.py` is `stub`.
