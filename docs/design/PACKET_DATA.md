# CIP design packet — canonical dataset (26Q3 · ASUS SA)

Authoritative figures for all `docs/design/*.html` mockups. Every shared
number on every surface must match this file. Grain and metric name are part
of the contract — do not relabel without updating here first.

Period context: tenant stamp **ASUS SA · 26Q3** (Brief has no filter bar;
period comes from the stamp).

---

## Spine nav counts (attention badges)

| Nav item | Count | Grain | Notes |
|---|---:|---|---|
| Brief | **8** | signal rows | Equals on-surface blotter row count |
| Stock | **119** | customer×SKU pairs | Pairs under 4w cover (Cover lens filter) |
| Settlement | **310** | cases | Open settlement book |
| Response | **6** | ranked actions | Open commercial responses |
| Steward | **23** | failed import jobs | Failed jobs in Import Center |
| Lineup | — | — | No attention badge in mockups |

---

## Brief — eight signal rows (grammar 3)

Rank order: trust → position → money.

| # | Signal | Key figures |
|---|---|---|
| 1 | Failed imports | **23** jobs · DSI vintage **2026-08-18** |
| 2 | SOH recon not run | book-wide trust block |
| 3 | DSI vintage stale | **2026-08-18** · **12d** old |
| 4 | Sell-out gap | since **2026-06-12** · **6** accounts |
| 5 | Cover breach | **119** pairs under 4w · book mean **24.3w** |
| 6 | Inbound open | **1,713** not-received lines · **Pipeline fill % 38%** |
| 7 | Settlement blocked | **1** case FX undeclared · **R 288,400** held |
| 8 | Missing assumptions | **103** SKUs on open cases |

### Brief federated Read (current signals only)

Cross-day deltas (e.g. 111→119, 22→23) are **deferred** until day-over-day
snapshotting exists in the platform. The Brief Read is computable from listed
signal rows only — no yesterday comparison.

Example Read (traces to signals #1, #2, #5 + Settlement outstanding):
**23** imports failed · SOH recon not run · **119** pairs under 4w cover ·
**R 19,246,828** outstanding · book trust blocked until SOH recon runs.

---

## Stock · Cover lens

| Metric | Value | Grain |
|---|---:|---|
| Pairs under 4w | **119** | customer×SKU pairs |
| Pairs in book | **448** | customer×SKU pairs |
| WOC histogram buckets | **41** · **78** · **186** · **92** · **51** | pairs per bucket (<2w · 2–4w · 4–8w · 8–13w · 13w+) |
| Book mean WOC | **24.3w** | weeks |
| Fill vs plan | **19.5%** | channel execution % (Cover regime label) |
| Not received | **1,713** | **open inbound lines** (outstanding qty on line) |
| Pipeline units | **4,051** | units in inbound pipeline |
| DSI vintage | **2026-08-18** | date |
| SOH recon | not run | book trust flag |

### Cover regime weekly deltas (this wk)

| Metric | Delta |
|---|---|
| Under 4w | ▲ **8** (bad) |
| Book mean | ▼ **0.4w** (good) |
| Fill vs plan | ▲ **1.2 pt** (good) |
| Not received (lines) | ▼ **86** lines (good) — unit receipts do not change line count |

---

## Stock · Inbound lens

| Metric | Value | Grain |
|---|---:|---|
| Pipeline units | **4,051** | units |
| Not received | **1,713** | **open lines** — partial receipt keeps line open (Short) |
| Pipeline fill % | **38%** | received÷ordered on open pipeline (Inbound regime label) |
| Landed this wk (book) | **452** units | unit metric only |
| Overdue open units — Mustek + Axiz share | **62%** | units on overdue open lines |

Inbound Read (concentration): **62% of open units** sit with Mustek and Axiz.

Partial delivery **SHP-88519** (Rectron): ordered **240** · received **120** ·
landed this wk **120** units · line state **Short** · Not received book total
stays **1,713**.

---

## Settlement

| Metric | Value |
|---|---:|
| Open cases | **310** |
| Book total | **R 28,988,034** |
| Settled | **R 9,741,206** |
| Outstanding | **R 19,246,828** |
| Settled this wk | **R 213,410** |
| Blocked FX case | **1** · **R 288,400** |
| Missing SKU assumptions | **103** |

Preview case **C26760971** (Takealot): outstanding **R 1,616,231.52** · FX
**18.00** declared · **0** claim evidence rows.

---

## Response

| Metric | Value |
|---|---:|
| Ranked open actions | **6** |

---

## Lineup (batch 2)

| Metric | Value | Grain |
|---|---:|---|
| Planned units (26Q3) | **12,840** | units |
| Net requirement (B2) | **3,420** | units |
| Approval | **86%** approved · **14** items pending |
| Lineup items | **248** | customer×SKU×period rows |
| Plan coverage (shipped÷planned) | **71%** | Q1+Q2 combined |

---

## Steward (batch 2)

| Metric | Value |
|---|---:|
| Failed import jobs | **23** |
| DSI steward queue | **41** |
| CST steward queue | **18** |
| Shipment steward queue | **12** |
| Lineup steward queue | **6** |
| Unmapped customer tokens (sample queue) | **7** |

---

## Metric naming (never conflate)

| Label | Lens / surface | Meaning |
|---|---|---|
| **Fill vs plan** | Cover · Execution | Channel sell-through vs lineup plan |
| **Pipeline fill %** | Inbound · Brief signal | Inbound received÷ordered on pipeline |
| **Not received** | Inbound · Cover regime | **Open lines** with outstanding quantity |
