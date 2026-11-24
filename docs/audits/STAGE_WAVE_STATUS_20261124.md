# Stage and wave status, 2026-11-24

Read-only check of `docs/CIP_ORCHESTRATOR_WAVES.md`, `.eif/PROGRAM.md` (generated, snapshot 2928), `docs/BACKLOG.md` and `docs/memory/CURRENT.md` against integrate `91bdbb00`, which has been live since restart batch3 (03:48 SAST). Main is still at `46368f6c` (nothing promoted).

## Closed in docs today
BACKLOG-262, 263, 264 (merged 2026-11-19, live; screenshots waived 2026-11-23), BACKLOG-250 (live read-only check), BACKLOG-168 (verified), 266, 269, 270, 272. BACKLOG-245 closed after its first passing `-Execute` (04:08 SAST).

## EIF nodes: list only (closure goes through `.eif/runtime/programme/program.py`, not by editing docs)
- Built and live tonight, but the node is still `proposed`: **N-0102** (generic discovery and readers; Discovery v2 + BACKLOG-270), **N-0119** (On the water / Shipments map), part of **N-0085** (non-leaf) and **N-0103** (worklist not built).
- Still `in_progress` (W1-E): N-0080, N-0082, N-0083, N-0089, N-0095, N-0096, N-0110, N-0111, N-0112, N-0113, N-0114, N-0115, N-0116 (dashboard V2 / targets / BACKLOG-269 feed this one; BACKLOG-217 tracks the gaps).
- `ready`: N-0072, N-0100, N-0117. `blocked`: N-0045, N-0060, N-0081. `deferred`: N-0054, N-0063, N-0074.

## Table

| Stage / wave | Status | Still open | Evidence |
|---|---|---|---|
| W1-A Replenishment (N-0117) | Partial | Node `ready`, not closed; store pins and map shipped; the real suburb for named centres (BACKLOG-267); N-0118 load waits on Warren | `dc55a56e` (264), BACKLOG-268, 267 |
| W1-B Listings generic (N-0102) | Built and live; node open | Takealot finds no pages (robots.txt blocks its search, web search found none); N-0103 worklist, N-0076 alerts, N-0077 competitors not built; live Preview blocked by D-0061 | Discovery v2 merge, BACKLOG-270, `42229c73` (263) |
| W1-C Planner quantities (N-0088) | Not started | Whole node | PROGRAM.md `proposed` |
| W1-D Defects 12/13 Nov | Not re-verified tonight | Check each item against code | - |
| W1-E Close in-progress nodes | Open | 13 nodes `in_progress` (list above) need Codex review + an EIF stage record | PROGRAM.md |
| Wave 2 web-app verification | Not done | No `docs/audits/WEBAPP_VERIFICATION_<date>.md`; harness only | `docs/audits/WAVE2_VERIFICATION_HARNESS.md` |
| Wave 3 B1 CI gate | Built | Merge-requires-green (branch protection) not verified | `.github/workflows/ci.yml`, PR #109 `72812f38` (BACKLOG-231) |
| Wave 3 B2 scripted deploy | **Done** 2026-11-24 | - | BACKLOG-245; `-Execute` record deploy-20261124-040848 |
| Wave 3 B3 promote to main | Not done | N-0099 second look; Warren says "promote to main" | main `46368f6c` |
| Wave 3 Phase C (N-0089, backups) | In progress | Node `in_progress`; restore test | PROGRAM.md |
| Final (a) new-customer line-up | Partial-deferred | See BACKLOG-252 | `804b470a` |
| Final (b) line-up customer/period views | Partial-deferred | See BACKLOG-251 | `bf0ae8fa` |
| Final (c) aged/slow duplication | **Done** | - | PR #114 `39a470b5`; live check today (BACKLOG-250) |
| Final (d) promotion calendar | Code merged; not live-usable | Migration `20261118_0063` never applied to `cip` (Warren + backup); real calendars; rejected-window decision | `a98a3af2`, BACKLOG-253 |
| Final (e) planner layout and cards | Part 1 shipped | See BACKLOG-254 | `22beb215` |
| Stages 2.9 / 4.7 / 7.4 / 8 / 10 | Deferred / ready / deferred / proposed / proposed | N-0054, N-0072, N-0063, N-0069, N-0070 | PROGRAM.md |
