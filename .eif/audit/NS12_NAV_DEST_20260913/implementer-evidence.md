# N-0024 implementer evidence — label vs destination

**Run:** `NS12_NAV_DEST_20260913` · **Actor:** `gov-001` · **2026-09-14**
**Do not complete.** Independent GOV-008 is a later session, different run and actor.
**Playwright MCP only.** No `browser_cdp`. No writes to `cip`.

## Enumeration (source, then click)

Surfaces read: `navConfig.ts`, `brief_signals.py`, hub `*Overview.tsx` Workflows + `HeadlineFigure` `onClick`, `CoverLensView.tsx` chips, plus labelled links that named the same jobs (`getting-started`, Import Center footer, Market “Planning lineup”, PO auto-link case chip).

| # | Surface | Label | Before href | After | Class? |
|---|---|---|---|---|---|
| 1 | Rail | Lineup cases | `/lineup` (Planning hub) | `/lineup/cases` | yes |
| 2 | Rail | Users & roles | `/admin/users` (Admin hub) | `/admin/users/list` | yes |
| 3 | Brief / Overview attention | steward queue (failed_imports) | `/admin/imports?status=failed` | `/admin/mappings` | yes — label kept |
| 4 | Brief / Overview attention | under 4 weeks of cover / Open Stock · Cover | `/sell-out` → Movement | `/stock?lens=cover&status=under4w` | yes |
| 5 | Brief signal (not live this session) | Open Stock · Cover (`soh_recon_not_run`) | `/sell-out` | `/stock?lens=cover` | yes |
| 6 | Brief / Overview attention | Open Stock · Inbound (`inbound_open`) | `/shipping` hop | label Open Supply · Shipments; `/supply/shipments` | yes |
| 7 | Planning hub figure | Lineup cases | `/commercial-planner` | `/lineup/cases` | yes |
| 8 | Planning Workflows | Lineup cases | already `/lineup/cases` via remap | pass-through after rail change | yes (already mapped) |
| 9 | Admin Workflows | Users & roles | already `/admin/users/list` via remap | pass-through | yes (already mapped) |
| 10 | Supply hub figure + attention | Unreceived past ETA | `/admin/shipment-evidence` | `/supply/shipments` | yes |
| 11 | Getting started | Users & roles / Lineup cases | hub hrefs | workspaces | yes |
| 12 | Import Center footer | Lineup cases | `/lineup` | `/lineup/cases` | yes |
| 13 | Market “Planning lineup” | Planning lineup | `/lineup` | `/lineup/cases` | yes |
| 14 | PO auto-link case chip | Case {id} | `/lineup` | `/lineup/cases` | yes |

**Not this class (recorded, not changed):** domain homes `/lineup` and `/admin/users`; Sell-through `/channel-intelligence` and Forecasts `/forecasts` (N-0022 honesty landings); Receipts & POD → `/admin/shipment-evidence`; “Open Settlement” → Case book; D-0002 steward-queue disposition; Movement/Execution relocated workspaces; rail expansion / LensTabs (D-0010 Option A).

**Cover filter:** new chip `Under 4w` (`status=under4w`) is the union of under-2w (`breach`) and 2–4w (`watch`). Existing chips unchanged.

## Click verification (Playwright, 2026-09-14)

| Control | Final URL | Verdict |
|---|---|---|
| Rail Lineup cases | `http://localhost:3000/lineup/cases` | **VERIFIED** |
| Rail Users & roles | `http://localhost:3000/admin/users/list` | **VERIFIED** |
| Planning hub Lineup cases figure | `http://localhost:3000/lineup/cases` | **VERIFIED** |
| Planning Workflows Lineup cases | `http://localhost:3000/lineup/cases` | **VERIFIED** |
| Admin Workflows Users & roles | `http://localhost:3000/admin/users/list` | **VERIFIED** |
| Supply Unreceived past ETA figure | `http://localhost:3000/supply/shipments` | **VERIFIED** |
| Attention failed_imports | `http://localhost:3000/admin/mappings` | **VERIFIED** |
| Attention cover_breach | `http://localhost:3000/stock?lens=cover&status=under4w` | **VERIFIED** |
| Cover chip Under 4w · 467 (430+37) | present on Cover after signal click | **VERIFIED** |
| Attention inbound_open | `http://localhost:3000/supply/shipments` (no `/shipping`) | **VERIFIED** |
| soh_recon_not_run click | signal not in live blotter (3 urgent) | **UNVERIFIED** (source href changed) |
| Getting-started / Import footer / Market / PO chip | not clicked this session | **ASSERTED** from source |

API process was restarted with the project venv so `brief_signals.py` loaded. Operator re-signed in with the on-screen seed (`admin@local`). Session cookie from the previous API PID did not survive the kill.

## Preservation

D-0010 Option A kept. D-0002 / N-0006 / N-0013 / BACKLOG-181 untouched. No column-picker work. No IA collapse.
