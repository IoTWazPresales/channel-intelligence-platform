# Claude chat handover — 2 Nov 2026

Written by Claude (claude.ai project chat, Opus 5.5) for whichever Claude picks up next on another account. Everything below was decided or verified with Warren in this chat between 28 Oct and 2 Nov 2026. The repo stays authoritative: read `docs/memory/CURRENT.md`, `CONTEXT.md` and the programme status first. This file holds what lives only in the chat.

## How the work runs

- **The chat** (this role) reviews, checks commits against code and data, and writes prompts. It labels claims VERIFIED or ASSERTED. It has repo read and push access (cloud clone) and has pushed audit and spec files only, never product code.
- **Claude Code on Warren's PC** implements: Sonnet 5.5, high effort. Opus is for independent review only, in a separate session from the writer.
- **Cursor is not used for this repo.** Its hook calls arrive at the EIF guard as empty requests (`HOOK_INPUT_INVALID`, empty stdin), and its background `git status` holds `index.lock`. Sessions die within a few calls.
- **One agent session at a time** in the CIP folder. Two parallel sessions wedged the guard on 30 Oct.
- **cip writes:** clone proof first, then Warren types "run against cip". The session reports dry-run counts against the proof, and they must match.

## Settled decisions (Warren)

1. A Shipped-sheet line with no ship-confirm date, or one dated after the report date, is not shipped. It is stored as an open order. (28 Oct)
2. Each ACZA Shipped_Unshipped report is the complete ACZA open book at its report date. Lines that leave it close (`closed_shipped`, `closed_disappeared`, `closed_moved`); nothing is deleted. Only report types configured as complete books close lines. (28–29 Oct)
3. Earlier shipment reports are never deleted. The report overwrites ETA, so delay is only visible across reports. (28 Oct)
4. "BOM not ready" sheet lines are open orders. (29 Oct)
5. No scraping of third-party sites, including port congestion. Port delay is a manual Administration entry until a licensed feed is chosen. (29 Oct)
6. Store and distribution-centre level sales, stock and replenishment are a core priority, **not deferred**. The ROADMAP "deferred by design" wording was never Warren's decision; it was corrected in `f14662f`. **Warren must also delete that line from the claude.ai project brief.** Keep the rule: never alias a store to its parent customer. (30 Oct)
7. Channel chain: **ASUS → distributor → customer DC → store**. DCs belong to the customers, not the distributors. (30 Oct)
8. **Pepkor is a direct customer**: ASUS ships to its DC (`PEPKOR-ZA-DR-01`), which receives for IC, Hifi, JD Furniture and others. Game and Makro (Massmart) buy through distributors; their DCs appear only as sites in their own reports, e.g. "Massmart Brackengate DC" and "Massmart Gosforth FC". A DC serves several accounts in one retail group. (30 Oct)
9. DC detection: name patterns (tenant config), behaviour (high stock, no consumer sales), and Warren confirms each DC once, after which it is remembered. (30 Oct, proposed by Claude, accepted)
10. Account managers **default** to their own accounts; they are not restricted. Claude's call, delegated by Warren on 2 Nov: a "My accounts" filter that they can clear, with no database restriction. A per-user restriction can come later if needed.

## Shipping work landed 28 Oct – 2 Nov (all on `feat/ns-2-brief-nav-collapse`, cip at 20261101_0050)

- **E10 query fixes:** calendar-aware prior period and prior year, retail calendars by day, and shipped quantity split from open quantity.
- **Open book:** closing on apply, the full-book config, the BOM sheet, and a one-off close on cip (audit event 18).
- **Import friction:** listing poll in 5-listing batches, saved mapping skipped, earlier steward decisions reused automatically, special-case clears remembered, and a searchable picker in bulk map.
- **Dashboard polish:** see `.eif/audit/DASHBOARD_POLISH_20261029/`.
- **On the water** (the Shipments map): spec in `.eif/audit/ON_THE_WATER_20261029/`. Voyage columns and backfill (audit event 22).
- **PO-less shipped twins:** 47 retired.
- **Loader:** blank-invoice Shipped rows no longer collapse; source key includes the order. Job 1697 was re-processed.
- **Fact writer:** a 500-row chunk-split loss is fixed.
- **Verified against the 27 Oct workbook:** 14,987 units at sea, 5,512 arrived (City Deep 5,108, Port Louis 404), 8 vessels, 3 overdue.
- **In flight on 2 Nov** (fixes from Warren's review):
  - click-to-filter must refresh only the grid, not the page;
  - "Needs a look" shows 15 lines / 1,067 units against the workbook's 12 / 1,316, so reconcile;
  - label port ETA against the derived delivery date;
  - vessel badge as "N days overdue · ETA moved +M";
  - side panel minimum width 360 px.

## Known open items

- **3,264 old `needs_review` steward items** from earlier jobs. Re-running the decision-reuse pass over them would likely clear most.
- **Pipeline:** 49,849 units against roughly 48,900 from the 27 Oct workbook (Unship plus BOM plus undated Shipped). Trace it.
- **Product matching:** 479 lines (40,695 units) in the 27 Oct report have no product match. This is the catalogue gap.
- **Staged but never loaded store data:** IC (32,418 staged rows against 82 loaded), Hifi, part of Makro and Game.
- **Census** (`.eif/audit/STORE_DC_CENSUS_20261030/REPORT.md`):
  - Game is READY at store grain.
  - Makro, IC and Hifi are PARTIAL.
  - Amazon, Takealot, Computer Mania and Evetech are account-level only.
  - `customer_location` is empty.
  - Distributor ship-to codes (`MUSTEK-ZA-IR-01` etc.) are business-unit accounts, not DCs.
  - ASUS → distributor lead times are learnable from ship-confirm → POD history (Pinnacle 5,252 lines, Mustek 3,431).
- **Dashboard BLOCKED items:** the default size of a new KPI, and the "IAZON" clipping cause (not reproduced).
- **Users** have only admin, steward, planner and viewer roles. There is no job and no customer-account assignment (VERIFIED in `app/core/security.py`, `app/models/iam.py`).

## EIF fix list (for the EIF repo, not CIP)

1. Treat an empty Cursor hook request as an automatic single retry, not a crash.
2. The guard's session check costs 0.7–1.8 s per call, plus a post-tool check. Speed it up.
3. Someone or something edited `.cursor/hooks/eif_guard.py` locally (4 lines in `--verify-closure`) before 30 Oct. Agents should not be able to; find out how. It was repaired with `install_project.py upgrade`.
4. Lock contention when two sessions share one project folder.

## Things that bit us (don't repeat)

- `git worktree remove --force` on Windows followed node_modules junctions and deleted real files. Remove a worktree's junctions first, or don't create worktrees.
- `git pull --autostash` while `.cursor/` has line-ending changes rewrote the guard and broke its fingerprint.
- Port 3000 is the supervisor's **production** build. After code changes: rebuild the web, then restart worker, API and web before any upload.
- Shipment imports have two steps: Validate, then Apply. A job at `validated` is waiting for Apply.

## Priority order agreed 2 Nov (for account-manager rollout)

1. Close N-0114, N-0115 and N-0116 through one independent Opus review, which also covers On the water and the shipment fixes.
2. **N-0100 extended:** a job per user (account manager, product manager, finance, country manager, admin) plus the customer accounts each user covers. Dashboards, Brief and Attention default to "My accounts". A "My accounts" starter dashboard from the existing builder, with the account filter bound to the user.
3. Load the staged-but-unloaded store data (IC, Hifi, Makro, Game).
4. **New inception module, store and DC replenishment:**
   - store sales and stock;
   - customer DC stock (group DCs, direct and indirect);
   - DC → store needs;
   - which distributor supplies the DC, from distributor stock and learned lead times;
   - slow and unsold stock with a suggested path (promote, move between stores or customers, return to distributor);
   - the store map in the On the water style.

   N-0110 and N-0108 fold in.
5. **Competition and customer websites:** N-0102, then N-0105, N-0106, N-0104, N-0103, N-0076, N-0077.
6. **Enablers:** N-0074 (stable domain address; account managers cannot reach CIP otherwise, and the tunnel port is blocked on Warren's network), N-0089 data health, N-0111 history upload, N-0088 promotion planner quantities.
7. **Later:** N-0094, N-0097, N-0098, N-0084, N-0070, and the blocked or deferred nodes.

## Next prompts

1. Wait for the On the water review fixes to land, then review the commit.
2. **Independent review**, in a new Claude Code session on **Opus**, separate from the writer: GOV-008 under its own `--run` over N-0114/0115/0116, On the water and the shipment fixes since 23 Oct. Read-only, findings only.
3. **Record the plan in the ledger** (Claude Code, Sonnet, one session):

```
Run cip-session-handover. Branch feat/ns-2-brief-nav-collapse.
Record in the programme ledger through program.py only (bare CLI, payload files, expected_revision). Ledger files stay uncommitted for Warren to commit.
1. decision.add (status accepted, Warren 2 Nov): the priority order in docs/memory/CLAUDE_CHAT_HANDOVER_20261102.md "Priority order", and decisions 6–10 from its "Settled decisions".
2. N-0100: extend scope with user job and customer-account assignment, a "My accounts" default filter on dashboards, Brief and Attention, and a "My accounts" starter dashboard (stage note plus decision reference).
3. add-node, class inception: "Store and DC replenishment", with the scope from item 4 of the priority order, evidence pointing to .eif/audit/STORE_DC_CENSUS_20261030/REPORT.md. Link N-0110 and N-0108 under it or as dependencies.
4. add-node, feature: "Load staged-but-unloaded store sell-through (IC, Hifi, Makro, Game)".
5. If On the water has no node yet, record it retroactively.
Report the node ids and the ledger revision.
```
