# CURRENT state

**Last updated:** 2026-07-31 (governing docs v3/v1.1 + domain rules; pre-P1 pg_dump)
**Verify git:** `git branch --show-current` · `git rev-parse --short HEAD`

---

## Branch and delivery

| Field | Value |
|-------|--------|
| **Branch** | `main` (P1 units may use short-lived `feat/p1-*` same-day merge) |
| **Alembic (DB)** | **`20260727_0074` on cip** (`20260730_0075` authored, **not applied**) |
| **HEAD** | tip of `main` (verify: `git rev-parse --short HEAD`) |
| **Pushed?** | verify before claiming |
| **Current phase** | **P1 — Load the corpus** |
| **Next** | New chat: P1 kickoff — do **not** start loads until Warren uploads source files on request |

---

## Governing set (authoritative)

| Doc | Role |
|-----|------|
| [`docs/ROADMAP.md`](../ROADMAP.md) **v3.0** | What to build, phase order |
| [`docs/AUTONOMOUS_BUILD_CHARTER.md`](../AUTONOMOUS_BUILD_CHARTER.md) **v1.1** | How work is executed (zones, gates, question queue) |
| [`docs/COMMERCIAL_DOMAIN_RULES.md`](../COMMERCIAL_DOMAIN_RULES.md) **v1.0** | **Domain ground truth — never overridden by any agent** |
| [`docs/OPEN_QUESTIONS.md`](../OPEN_QUESTIONS.md) | Question queue (charter protocol) |
| [`docs/STEWARD_EXPERIENCE_CONTRACT.md`](../STEWARD_EXPERIENCE_CONTRACT.md) | What done means for steward surfaces |
| [`docs/STEWARD_ENGINE_DECISIONS.md`](../STEWARD_ENGINE_DECISIONS.md) | Why steward is built this way |

If CURRENT disagrees with ROADMAP about what's next for the session, CURRENT wins and ROADMAP gets corrected.

---

## Pre-P1 database snapshot

| Field | Value |
|-------|--------|
| **Binary** | `C:\Program Files\PostgreSQL\18\bin\pg_dump.exe` |
| **Database** | `cip` (verified `current_database() = cip` before dump) |
| **Dump path** | `C:\Users\warren_eliason\cip-db-snapshots\cip_pre_p1_2026-07-31.dump` |
| **Format** | custom (`-F c`) |
| **Taken** | 2026-07-31 |

---

## Source-file access (session override)

**No staging folder on disk.** When a step needs real data, STOP and tell Warren exactly what to upload (domain, periods, file count, what will be done). Do not search for or assume file locations.

`.gitignore` excludes `*.xlsx`, `*.xls`, `*.csv`, `*.dump` (and related dump patterns) so uploaded commercial data / dumps are never committed.

---

## P1 lock (2026-07-30, still in force)

| Item | Decision |
|------|----------|
| Load order | P1-0 scaffold → P1-1 **082** → P1-2 DSI → P1-3 shipment → P1-4 CPOR → P1-5 lineups → P1-X batch-fix |
| Exit artifacts | [`docs/DATA_CENSUS.md`](../DATA_CENSUS.md) + [`docs/P1_LOAD_DEFECT_LOG.md`](../P1_LOAD_DEFECT_LOG.md) |
| A1 window | All quarters with lineup coverage on cip; **credible core 26Q1 → current** |
| Open Decision #4 / BACKLOG-068 | **Superseded by domain rules:** landing-quarter is A1/A2 core; fill rate stays shipped-basis; budget = landed-basis |
| Defect discipline | Log unless load-blocking; no inline drive-by fixes |
| Domain halt | After each of P1-2…P1-5: update census, print numbers, **HALT**; Warren must say VERIFIED |

---

## P1 unit status

| Unit | Status |
|------|--------|
| P1-0 Census + defect-log scaffold | **Done** (scaffold files may be uncommitted — verify) |
| P1-1 BACKLOG-082 header config | **Implemented in dirty tree** — migration `20260730_0075` authored, **not applied**; not part of governing-docs commit |
| P1-2…P1-5 domain loads | Pending (halt after each) — **not started this session** |
| P1-X boundary batch-fix | Pending |

---

## Standing quality bar

**Contract or STOP · no half-PASS · code is evidence.** Steward contract **v1.6**.  
Behaviour-changing units must ship a **## Verification sequence**.  
CI API defects: `docs/CI_API_DEFECT_LOG_2026-07-29.md` — batch-fix later, not during P1 load.

---

## Parked / extracted

| Item | Where |
|------|--------|
| GitHub required CI check | BACKLOG-**087** |
| Header ASUS seed + denylist | BACKLOG-**082** (Active — P1-1) |
| Customer merge alias seal | BACKLOG-**081** |
| CST alias batch confirm/reject | BACKLOG-**080** |
| Ops-list shell parity (fold-in) | BACKLOG-**079** |
| Customer merge companions | BACKLOG-**083** |
| URL helpers | BACKLOG-**084** |
| Ops-list pagination (fold-in) | BACKLOG-**085** |
| PM channel_id CASE redo | BACKLOG-**086** |
| Landing-quarter KPI (old BACKLOG-068) | **Superseded** → A1/A2 core per domain rules §4.3 |
