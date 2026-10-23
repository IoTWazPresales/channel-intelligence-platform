# N-0115 design panel brief (shared by every seat)

Repo: C:\Users\warren_eliason\channel-intelligence-platform (Windows, Git Bash).

## How you work
- You are ONE independent seat. Form your own view; you do not see the other seats.
- Do not edit any product or project file. The ONLY file you create is your own report, path given in
  your prompt, with the Write tool. Write a first version early and overwrite it as you go, so nothing is
  lost if you are interrupted. Finish with a one-line final message naming the report path.
- Guard rules: never `cd`; shell text must not name `.claude/`, `CLAUDE.md`, `.eif/program/`,
  `.eif/runtime/` or `.cursor/hooks`. Do not use SendMessage or TaskStop.
- Never connect to database `cip`. Read-only pg_dump clone of cip (taken 2026-10-23):
  `apps/api/.venv/Scripts/python.exe apps/api/scripts/db_on.py sql --owner --db cip_n0115 --timing -c "<SQL>"`
  (read-only transaction; owner login bypasses row security, say so when timing).
- Report: concrete, max about 1,800 words, cite file:line, separate FACT (seen in code/data) from PROPOSAL.

## Start here
`.eif/audit/PROGRAMME_20261023/N0115_DISCOVERY.md` holds the facts already gathered: catalog, handlers,
engine, every caller, saved state on cip, fact tables with row counts and columns.

## Operator's mandate (Unit B: data model under the builder; replaces one hand-written query per metric)
- Fact tables declared as models with measures (sum units, sum value, count, distinct count, average,
  min/max): sell-out (DSI), customer sell-through, shipments/sell-in, distributor stock, returns, lineup
  plan, CPOR cases/lines, recorded prices.
- Shared breakdowns: period at day/week/month/quarter/year on the tenant business calendar, customer,
  distributor, product and every product attribute and spec (specs_json), business unit, channel,
  region, store/site, promo type.
- Which breakdowns a measure allows is DERIVED from the model's joins and declared walls, never
  hand-listed per metric. Walls (CST customer is not DSI customer, site_label CST-only, etc.) are declared
  once with plain-words reasons; keep every existing refuse_example.
- Calculated measures: ratio, difference, % change, prior period, prior year, running total, share of
  total, per-week rate.
- Existing metrics (fill rate, weeks of cover, support spend, etc.) re-expressed as calculated measures
  or kept as governed handlers. Parity: each returns identical numbers, proven on cip_test AND read-only
  on a clone of cip (old vs new per metric). A metric that does not match keeps its old handler and is
  listed; it does not block.
- One query compiler: measure x breakdowns x filters -> SQL, tenant and product-line scope (D-0056,
  row security bound per transaction on the request session) always applied, row limits, explain output,
  caching. Timings on the clone; target under 2 s per widget query.
- Catalog definitions are per-tenant configuration with the current catalog as default, not constants.
- Catalog API returns measures, breakdowns and derived allowed combinations so the UI builds itself.
  Every existing caller keeps working (tests per caller).
- Domain or commercial definitions (ex/inc VAT, which price, DAP vs sell price, currency): use what the
  code already uses; if none, the most conservative; record as a proposed decision. Never invent a figure.
  Never change a number to make two surfaces agree.
- Change scope: apps/api, apps/web, packages/ui, docs. No new libraries. One engineer agent implements it
  in one long session tonight, then Unit C (the builder UI, migration of 6 widgets / 3 saved reports,
  scheduled report keeps sending, three starter dashboards) builds on it.
