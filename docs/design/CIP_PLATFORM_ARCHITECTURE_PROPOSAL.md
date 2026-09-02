# CIP Full-Platform Architecture Proposal (amended)

> **REJECTED BY OPERATOR 2026-09-02 (D-0004 / D-0005; D-0002 deferred by D-0006).** Preserved as history only.
> The current proposal is `.eif/audit/NS_REDESIGN_R3_20260902/DIRECTION.md` (D-0007, proposed) with the React
> prototype at `apps/web/src/design-lab`. Do not implement anything from this document.

**Status:** ~~Awaiting operator approval — amended package~~ **Rejected 2026-09-02**  
**Amendment:** 2026-09-02 — mobile evidence correction, naming re-challenge, utility demonstration, split capability decisions  
**Evidence base:** `docs/design/CIP_FULL_PLATFORM_RECONCILIATION.md`  
**Programme:** PRG-20260831T145514 · **N-0013**

---

## 1. Executive summary

Reconciliation and operator challenge show the **job-boundary architecture** remains sound, but r1 approval evidence was **insufficient**:

- Mobile 390px PASS was **incorrect** (CSS conflict) — corrected in r2 evidence
- Independent r1 review contained **unsupported assertions** — superseded by r2 review
- **Channel** and **Data** spine labels fail buyer-language and collision tests
- Reports/Admin needed **rendered utility architecture**, not text sub-links
- Mapping queue and dashboard KPI decisions must **not** hide inside a single architecture approve

**Amended spine (six jobs + two utilities):**

| # | Label | Job | Grammar |
|---|---|---|---|
| 1 | **Brief** | Attention queue (landing) | 3 |
| 2 | **Plan** | Assortment & buy planning | 2 |
| 3 | **Position** | Channel position & execution vs plan | 2 |
| 4 | **Settlement** | Funding & claims | 1 |
| 5 | **Actions** | Ranked commercial response | 4 |
| 6 | **Imports** | File ingest, steward worklists, identity masters | 5 |
| U | **Reports** | Build · Dashboards · Inbox | 6 |
| U | **Admin** | Access · Settings · Operations · Trust | utility |

---

## 2. What changed in this amendment (not a programme reset)

| Item | r1 | Amended |
|---|---|---|
| Stock/execution container | Channel | **Position** |
| Steward/imports container | Data | **Imports** |
| Mobile evidence | FAIL (claimed PASS) | **PASS** (isolated `cip-base.css`) |
| Reports/Admin | Text sub-links | **Utility hub mockups** |
| D-0001 | Bundled 6 capability decisions | **Split** — D-0001 core IA only; D-0002 mapping queue; D-0003 KPI vs Brief |
| Container-count reasoning | Implicit nav ceiling | **Job-boundary only** |

Completed nodes N-0004–N-0009 are **not reopened**.

---

## 3. Architecture challenge — container count

Alternatives evaluated on **job boundaries and capability mapping only** (no predetermined count ceiling or floor).

| Model | Verdict | Rationale |
|---|---|---|
| **Six jobs + two utilities** | **ACCEPT** | Distinct jobs: attention, plan origination, execution measurement, funding, commercial action, data ingest/trust; Reports and Admin are episodic/platform utilities |
| Merge Plan + Position | REJECT | Plan origination vs execution measurement is a domain boundary (BLN-0001, N-0009 preservation) |
| Merge Settlement + Actions | REJECT | Funding book vs ranked response; B4 handoff is not a merge |
| Promote Reports to primary job | REJECT | Build/dashboard/inbox are episodic outputs, not daily operator workflow spine |
| Split Imports into separate Masters job | REJECT | Masters are resolution targets for import/steward workflows; splitting recreates admin/master-data nav sprawl without a distinct daily job |

**Conclusion:** Count follows from jobs; navigation complexity is managed via utility hubs and lenses, not by forcing merges.

---

## 4. Buyer-facing naming (amended)

| Was (r1) | Amended | Rationale |
|---|---|---|
| Brief | **Brief** | Retain — attention landing |
| Plan | **Plan** | Retain |
| Channel | **Position** | Avoids collision with product name "Channel Intelligence" and `/channel-intelligence` CST context route; job is "where we stand" (cover, movement, fill vs plan, inbound) |
| Settlement | **Settlement** | Retain |
| Actions | **Actions** | Retain |
| Data | **Imports** | Job is ingest + resolve; matches Import Center; masters/worklists live inside container |
| Reports | **Reports** | Retain; interior split Build / Dashboards / Inbox |
| Admin | **Admin** | Retain; interior split Access / Settings / Operations / Trust |

**Context route:** `/channel-intelligence` remains; breadcrumbs use "CST intelligence" or similar — not spine label "Channel".

### Secondary terms

| Term | Amended |
|---|---|
| Execution lens | **Fill vs plan** |
| `/stock` | **`/position`** (redirect from legacy) |
| `/admin/imports` hub | **`/imports`** |

---

## 5. Information architecture

### 5.1 Primary spine

```
Channel Intelligence
  Brief          ← landing / attention; replaces dashboard landing job
  Plan           ← /plan
  Position       ← /position?lens=Cover|Movement|Fill vs plan|Inbound
  Settlement     ← /settlement
  Actions        ← /actions
  Imports        ← /imports (Import Center, worklists, master grids)
  ─────────
  Reports        ← utility hub → Build | Dashboards | Inbox
  Admin          ← utility hub → Access | Settings | Operations | Trust
```

### 5.2 Reports utility architecture (demonstrated)

| Destination | Operator job | Capability |
|---|---|---|
| **Build** | Compose analytical output | Report builder / grammar 6 composer |
| **Dashboards** | Return to saved analytical views | Saved dashboards; **proposed home for KPI tile capability** (D-0003) |
| **Inbox** | Collect scheduled deliveries | Report inbox / digests |

### 5.3 Admin utility architecture (demonstrated)

| Group | Contents | Not in Admin |
|---|---|---|
| **Access** | Users, roles | — |
| **Settings** | Tenant profile, wipe | — |
| **Operations** | Ops monitoring | — |
| **Trust** | Steward audit, SQL viewer | File ingest, master grids → **Imports** |

### 5.4 Middleware redirects (unchanged pattern, amended targets)

| Legacy | Target |
|---|---|
| `/dashboard`, `/exceptions`, `/getting-started` | `/brief` |
| `/lineup`, `/buy-plans` | `/plan` |
| `/sell-out`, `/plan-vs-executed`, `/shipping`, `/inventory` | `/position?lens=…` |
| `/stock` | `/position?lens=…` |
| `/commercial-planner/cpor-cases` | `/settlement` |
| `/commercial-planner` | `/actions` |
| `/admin/imports` | `/imports` |

---

## 6. Operator capability decisions (explicit — not in D-0001 alone)

### D-0002 — Mapping queue UI

See `.eif/audit/NS_RECONCILE_20260902/OPERATOR_DECISIONS.md`.

**EIF recommendation:** RESTORE nav under Imports until steward parity proven. **Do not** RETIRE UI in architecture approval.

### D-0003 — Dashboard landing vs KPI capability vs Brief

| Concept | Proposal |
|---|---|
| Landing job | **Brief** replaces control-tower landing |
| Signal queue | **Brief** |
| KPI card analytical grid | **Reports → Dashboards** (restore capability; not silent retirement) |
| `/dashboard` route | Redirect to Brief; page retired after transition — **not** restored as landing |

**Warren chooses** KPI placement option A/B/C in OPERATOR_DECISIONS.md.

---

## 7. UI redesign direction (unchanged intent; no Phase A yet)

Phases A/B/C as r1 — shell convergence, primitive library, migration waves. **Blocked** until amended D-0001 + D-0002 + D-0003 accepted.

---

## 8. Evidence (r2 — authoritative)

| Artifact | Path |
|---|---|
| Gallery | `.eif/audit/NS_RECONCILE_20260902/index.html` |
| Mobile 390px | `platform-shell-mobile.html` |
| Position/Cover | `position-cover-desktop.html` |
| Reports utility | `reports-utility-desktop.html` |
| Admin utility | `admin-utility-desktop.html` |
| Verification r2 | `rendered-verification-r2.md` |
| Independent review r2 | `independent-rendered-review-r2.md` |
| Operator decisions | `OPERATOR_DECISIONS.md` |

r1 `rendered-verification.md` and `independent-rendered-review.md` are **superseded**.

---

## 9. Operator approval package (amended)

Three decisions — one session, not repeated loops:

1. **D-0001 (amended)** — Approve core IA: Brief · Plan · Position · Settlement · Actions · Imports + Reports · Admin utilities  
2. **D-0002** — Mapping queue UI: RESTORE (recommended) or RETIRE with explicit acceptance  
3. **D-0003** — KPI capability placement relative to Brief landing  

**Do not begin Phase A** until all three are recorded.

---

*Amendment to N-0013. Implementation change scope: NONE.*
