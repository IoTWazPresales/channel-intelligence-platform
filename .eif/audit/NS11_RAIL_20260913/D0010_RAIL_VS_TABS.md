# D-0010 — Rail expansion vs in-page LensTabs

**Status:** proposed. Operator accepts or rejects before any IA implementation.
**Scope:** N-0023. Does not implement the IA half.
**Out of scope:** D-0002, N-0006, N-0013 reopen, Design Language v2 beyond the rail.

## Question

The production rail lists each domain’s live+partial leaves. Most domain pages also have a tab row (`LensTabs`) listing leaves. Every D-0008 domain now lands on an overview hub. Does the rail still need to expand?

## AS-IS — what each control actually provides

Claims below are **VERIFIED** from `navConfig.ts`, domain `*Chrome.tsx` / `*Paths.ts`, `LabShell.tsx`, and Playwright at 1280×800 on 2026-09-13 against `http://localhost:3000` (no `browser_cdp`).

### Rail (`CapabilityRail` / lab `Rail`)

- Cross-domain jump; domain header navigates to domain `href`.
- Lists **live + partial** leaves only (`inRail`). Substrate/planned stay in the capability directory.
- Badges from `spine_badges`. Expand/collapse per domain; production persists `cip.shell.nav.groupExpanded.v2`.
- Lab auto-opens only the active domain. Production also persists previously opened groups, so Funding/Market stayed expanded on Data and pushed Data below the fold until the rail was scrolled (**VERIFIED** screenshot on `/admin/imports`).
- Footer: capability directory.

### Tabs (`LensTabs` on domain chrome)

- In-domain sibling switch on the current page.
- Optional counts (Cover breach, Import Center failed+pending, Funding planner/book).
- Market tabs preserve `customer` / `product` / `activation` query scope (`hrefWithScope`) — the rail does not.
- Not mounted on Overview at all (`OverviewChrome` has DomainHeader only).
- Hidden on Supply / Planning / Administration **hubs** (`lens === 'hub'`); shown on those domains’ leaf pages.
- Always mounted on Stock, Funding, Market, Data.

### Hubs

Supply (and the DomainOverview pattern) lists the same live+partial workflows in a **Workflows** panel with `CapabilityStatus`, **without** tabs. Overview composes Business dashboard + Needs attention + pinned reports and has **no** tab row.

### The lists are not the same destinations

| Domain | Tabs on hub? | Tabs on leaves? | Rail leaves | Tab leaves | Match? |
|--------|--------------|-----------------|-------------|------------|--------|
| Overview | no | no | 4 | none | Rail is the only persistent leaf list |
| Stock | yes | yes | 5 | 5 | Near-duplicate |
| Supply | no (Workflows panel) | yes | 3 | 3 | Hub panel duplicates rail; tabs only on leaves |
| Planning | no | yes | 2 (roadmap is substrate → directory) | 3 including Product roadmap | Tabs are a superset. Rail “Lineup cases” `href` is `/lineup` (the hub); tab “Lineup cases” is `/lineup/cases` |
| Funding | yes | yes | 6 live+partial | 7 including Budget ledger (substrate) | Tabs are a superset (**VERIFIED** Case book) |
| Market | yes | yes | live+partial | includes planned/substrate | Tabs are a superset (source) |
| Data | yes | yes | **13** | **4** grouped (Import Center · Steward queue · Master data · Steward audit) | Tabs are a grouping, not a duplicate (**VERIFIED** scrolled rail) |
| Administration | no | yes | 4 live (Audit log planned → directory) | 4; Users & roles tab → `/admin/users/list` | Rail “Users & roles” `href` is `/admin/users` (the hub) |

Data’s rail-only destinations include Products, Customers, Distributors, duplicates, CST steward, Channels & regions, Customer sell-through files. Those are not tabs.

## Collapsed-active domain (token, not IA)

Lab after 130189e, measured at `/design-lab/stock?lens=cover` after collapsing Stock and clicking the H1 to drop hover:

- collapsed-active background `rgba(0,0,0,0)` (**VERIFIED**)
- icon `rgb(61, 184, 232)`, label weight `600` (**VERIFIED**)
- no `::before` bar (**VERIFIED**)
- hover/focus can leave a transient primary alpha (~0.24); that is not selected fill

**Decision recorded for the N-0023 port:** keep that treatment. The 3px bar is leaf language. The raised `background.paper` surface is expanded-group language. Collapsed-active is weaker on purpose. Tabs (where they exist) remain the leaf locator while the group is collapsed. Rejected alternatives: 3px bar on the domain (collides with leaf language); refuse collapse of the active domain (lab allows it); restore selected fill (undoes BACKLOG-181).

## SHOULD-BE — disposition for the operator

**Do not collapse the rail to domains-only in this node.** The two controls do not share one destination set. Collapsing expansion now would hide Data’s 13-leaf catalog and Overview’s only persistent leaf list.

### Option A — Keep expansion (recommended)

Accept duplication on Stock / Funding / Market as the cost of cross-domain jump + in-page sibling switch. Token port (N-0023) is independent. No href/label/order change.

### Option B — Domains-only rail

Only after every hub owns a complete workflow list **and** Overview gains a leaf switcher **and** Data’s long tail is re-homed under Master data or the directory. That is a later implement node, not N-0023.

### Option C — Remove tabs where the lists already match

Stock is the only clean 1:1. Removing those tabs would leave collapsed-active Stock with no leaf locator. Not recommended until Option A/B is settled.

### Related observation (not this decision)

Production persists every expanded group; lab opens only the active domain. That persist is why Data sat below the fold. N-0023 **preserves** `NAV_STORAGE_GROUP_EXPANDED`. Changing the default is a follow-up if Option A is accepted.

## Operator action

Reply **accept A**, **accept B** (charter a later node), **accept C**, or **reject / amend**.
