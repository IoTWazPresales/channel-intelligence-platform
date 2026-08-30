# Charter review — `docs/AUTONOMOUS_BUILD_CHARTER.md` v1.2

**Date:** 2026-08-30  
**Reviewer:** Cursor (design-freeze batch)  
**Scope:** Read-only assessment. The charter is **not** accepted or modified by this document.

**Cross-read:** `docs/design/CIP_DESIGN_LANGUAGE.md` (FROZEN v1.1 + grammar 6 add),
`docs/design/CIP_NAV_MAP.md`, `docs/STEWARD_ENGINE_DECISIONS.md` (selected locked entries).

---

## (a) What the charter commits us to

The charter (v1.2, 2026-08-01) positions itself as the **authoritative execution doc**
for building the remainder of CIP with bounded autonomy. It explicitly sits under
`docs/ROADMAP.md`, is bound by `docs/COMMERCIAL_DOMAIN_RULES.md` (**domain ground truth —
never overridden**), and beside `STEWARD_EXPERIENCE_CONTRACT.md`, `STEWARD_ENGINE_DECISIONS.md`,
and `COMMERCIAL_SEMANTICS.md`.

Quoted commitments:

> *"Autonomy is only safe on top of guardrails that did not exist a month ago: an enumerated
> contract, an append-only decisions log, a mechanical gate script, clone-proof discipline for
> destructive paths, and a trunk with no diverged branches. Those are the preconditions. Do not
> relax them to move faster — they are the reason speed is available at all."*

> *"Every module carries enumerated contract rows **written before implementation**.
> Verification runs against the rows, never against whatever got built."*

> *"Mechanical reconciliation is Cursor's. Domain plausibility is Warren's, at defined gates,
> with a numbered verification sequence."*

> *"The **Question Queue** is mandatory and must be populated even when nothing feels blocking.
> An empty queue after a module is **a finding** to report."*

> *"Every module has explicit exit criteria and a time budget. Hitting the budget triggers a
> report, not a push."*

> *"**NEVER PATCH — hard constraint.** A fix must name the root cause."*

> *"Tenant vocabulary, period conventions, currency, legal-form rules, column maps, BU grain and
> export templates are **configuration**. Any tenant-specific string entering code is a defect."*

> *"Optimize for UX, design, architecture, scalability, flexibility, best business practice —
> never for speed or 'smallest diff.'"* (dual-agent quality bar)

> *"**Cursor must not self-PASS** — After clone/parity units, seed CLI VERIFY; only
> `VERDICT: PASS` closes."*

In sum: the charter commits the project to **contract-first builds**, **zone-gated autonomy**,
**browser verification with printed reconciliation**, **append-only question logging**,
**no symptom patches**, **config-not-code tenant behaviour**, and a **dual-agent VERIFY loop**
for steward/import parity work — all subordinate to domain rules and commercial semantics.

---

## (b) Gates, approvals, and ceremony — safety vs stall risk

| Gate / ceremony | Charter source | Safety control? | Stall / overhead risk |
|---|---|---|---|
| **Enumerated contract rows before build** | Failure mode #1 mitigation; module exit criteria | **Yes** — prevents "verified what exists, not what was missing" | Low if rows exist; **high** if contract lags design freeze (agent builds to mockups with no row) |
| **AMBER design-stage halt** (new metric / lifecycle / tile before code) | Autonomy zones; D-024 aligned | **Yes** — caught POD-on-wrong-screen class | **Medium** — can pause mid-unit if semantics unclear; non-blocking questions allow proceed-on-assumption |
| **AMBER post-build halt** (domain load sign-off, new file family) | Autonomy zones | **Yes** for data trust | **High for P1** — charter itself says file-dependent steps are AMBER and cannot chain unattended |
| **RED zone** (merges, migrations, unsettled domain rules) | Autonomy zones | **Yes** — irreversible / schema | Low stall if respected; **high** if agent treats RED as negotiable |
| **Alembic / schema — explicit approval only** | Database policy | **Yes** | Low — correct stop |
| **Clone-proof before merge/supersession/destructive bulk** | Database policy; RED | **Yes** | Medium — prep work, but necessary |
| **`pg_dump` before first autonomous load** | Database policy | **Yes** | One-time overhead |
| **Pre-build existence audit** (grep before UI) | Browser verification section | **Yes** — prevents duplicate surfaces | Low–medium — fast grep; **stall** if interpreted as "any hit = stop" without extend-vs-new judgment |
| **Numbered browser verification sequence** | Browser verification | **Yes** for UI regressions | Medium — mandatory per module; smoke suite growth capped at 15 min |
| **Mechanical reconciliation** (file totals vs displayed) | Module exit; verification | **Yes** for imports/facts | Low for data modules |
| **Warren domain plausibility** (A1, P1 sign-off) | Failure mode #2 | **Yes** — agent cannot judge commercial truth | **High** — blocks module close until Warren reads |
| **Question queue — empty is a finding** | Question Queue protocol | **Partial** — forces honesty | Low safety value; **process overhead** if treated as failure when truly nothing unclear |
| **Session time budget → report** | Failure mode #4 | **Partial** — prevents infinite polish | Low stall — charter says budget triggers report, **not** stop |
| **Consult after each module / 2 failed fixes / RED** | Consult section | **Yes** for architecture drift | **High** on steward/import units — VERIFY gate blocks next unit |
| **CLI VERIFY `VERDICT: PASS` before next unit** | Dual-agent loop | **Yes** for parity | **High stall** if consultant unavailable; intentional |
| **Smoke suite blocks commit** | Regression strategy | **Yes** at scale | **Medium** — can block unrelated work if suite brittle |
| **Demo-script maintenance from A1** | Demo artifact | Product discipline | Overhead unless demo is active |
| **Interview triggers one phase early** | Interview triggers | Reduces surprise blocks | Low |

**Summary:** Most gates are **real safety controls** (migrations, merges, contract verification,
domain plausibility, no-patch rule). The highest **mid-flight stall** risks are: (1) **AMBER
file-upload dependency** for loads, (2) **VERIFY PASS** gating between dual-agent units,
(3) **Warren plausibility** on analytics modules, and (4) **contract rows lagging** a frozen
design language the charter never references.

---

## (c) Contradictions with frozen design language, nav map, or steward decisions

### C1 — Landing / app shell vs Brief grammar 3 (design language + nav map)

**Charter (P2-4):** *"Navigation, IA, **landing surface**, freshness banner"* — exit: *"A manager
reaches any surface unaided"* (AMBER).

**Frozen design:** Container 1 is **Brief** — grammar **3 signal blotter**; Read is federated
current signals; **no KPI cards**; anti-pattern list rejects *"uniform KPI-card rows"* and
*"equal-weight card grids"* (`CIP_DESIGN_LANGUAGE.md` §7).

**Demo spine (charter):** *"login → **landing surface with freshness** → plan accuracy…"*

**Tension:** Charter language ("landing surface", "freshness banner") predates the frozen
**Brief** disposition in `CIP_NAV_MAP.md` and still reads like a **dashboard/control-tower**
surface — explicitly **retired** in the nav map (*"Dashboard/Control tower (retired as cards)"*).
Not a direct logical contradiction (freshness can live on Brief), but **implementers following
the charter literally could rebuild KPI-card landing** the design language forbids.

**Steward alignment:** D-023 (metric ownership) and D-024 (design-stage halt) **support** the
freeze — but the charter does not cite `CIP_DESIGN_LANGUAGE.md` as governing UI.

### C2 — Report builder module vs grammar 6 Composer (design language)

**Charter (P3-3):** *"Build, slice, filter, visualise; author + consume modes"* — AMBER, 3 sessions.

**Frozen design (2026-08-30):** Grammar **6 Composer** — three-panel assemble/preview/save;
**no KPI-card composers**; saved views are first-class; preview mandatory (`reports-builder.html`).

**Tension:** Charter describes a generic BI-style builder; frozen spec constrains **interaction
grammar and anti-patterns**. Implementing P3-3 without grammar 6 would be a **design deviation**
requiring SPEC_GAPS adjudication per §8 — charter does not mention this.

### C3 — DB write policy — resolved in steward log, not in charter body alone

**Charter:** GREEN permits unattended import/steward applies; RED for merges; migrations need approval.

**D-026:** Explicitly **supersedes** older dual-agent line *"no cip writes without Warren"* (blanket).

**Assessment:** No contradiction **if** agents read D-026. Charter skills section still bundles
database rules under "Autonomy zones" — consistent when decisions log is in the read set.

### C4 — Commercial semantics vs design packet figures

**Charter:** Metrics must live in `COMMERCIAL_SEMANTICS.md` (via D-025); pre-build audit mandatory.

**Design mockups:** Use `docs/design/PACKET_DATA.md` as canonical **for HTML exemplars only**.

**Tension:** Not a contradiction if scopes are kept separate — but an agent could treat PACKET_DATA
figures as production truth. Charter does not acknowledge the design packet layer.

### C5 — Nav vocabulary

**Charter demo / modules:** Uses legacy phrasing ("promo effectiveness", "plan accuracy",
"landing") in places.

**Nav map (confirmed 2026-08-30):** Brief · Lineup · Stock · Settlement · Response · Steward ·
Reports · Admin.

**Assessment:** Naming drift in charter **demo spine** vs settled spine labels — documentation
debt, not a build blocker if `NAMING.md` / nav map win (charter says semantics/contract win on
conflict — but design language is not in that list).

---

## (d) Requirements that no longer apply post-freeze (or need reframing)

| Charter item | Why stale / needs reframe |
|---|---|
| **P2-4 "landing surface" without Brief grammar** | Superseded by frozen Brief (grammar 3) + nav map container 1 |
| **Demo spine implying dashboard tiles** | KPI-card landing retired; demo should walk **Brief → containers**, not control tower |
| **P3-3 report builder as unconstrained BI** | Reframe to grammar **6 Composer** per design language addendum |
| **Five surface grammars (implicit)** | Design language now defines **six** — charter never counted grammars |
| **WORKFLOW_DUAL_AGENT.md** | Charter says absorbed (stub) — OK; skills point to `cip-dual-agent-fable` |
| **"Freshness banner" as primary landing affordance** | Brief uses tenant stamp + signal ages; filter bar exempt on grammar 3 |
| **Pre-charter nav disposition work** | `CIP_NAV_MAP.md` completeness rule + mechanical route audit — charter predates freeze but goal aligns |

Items that **still apply fully:** autonomy zones, migration approval, clone-proof merges,
contract rows, browser verification, question queue, no-patch rule, VERIFY loop for steward
parity, tenant config discipline, `COMMERCIAL_SEMANTICS` ownership (D-025).

---

## (e) Recommendation

**Accept with named amendments** — do not reject the charter wholesale; its safety spine
(zones, contracts, verification, no-patch, semantics ownership) remains correct and aligns
with locked steward decisions (D-024, D-025, D-026). **Do not accept as-is** for UI work:
it does not reference the **frozen design language** or **nav map** as governing documents,
and its landing/demo language can mis-route implementers toward retired KPI-card patterns.

### Named amendments (for Warren — not applied here)

1. **Add governing-doc line** (charter header): cite `docs/design/CIP_DESIGN_LANGUAGE.md`
   (FROZEN) and `docs/design/CIP_NAV_MAP.md` beside commercial semantics — UI implementation
   defers to design language; metrics still defer to `COMMERCIAL_SEMANTICS.md`.

2. **Rewrite P2-4 exit criterion** to: *"Brief (grammar 3) reachable; spine matches nav map;
   manager reaches any container unaided"* — drop implicit dashboard/freshness-banner wording
   or define freshness as Brief signal ages / tenant stamp.

3. **Rewrite P3-3** to reference **grammar 6 Composer** (source · canvas · output · preview ·
   named saved views) and exemplar `docs/design/reports-builder.html`.

4. **Update demo spine** to: login → **Brief** (signals) → Lineup → Stock → Settlement →
   Response → scheduled report (Reports) — no KPI-card landing.

5. **Clarify design packet scope:** `PACKET_DATA.md` is mockup-canonical only; production
   figures come from loaded facts + semantics reconciliation.

6. **Contract row source:** note that new UI surfaces may need contract rows derived from
   `STEWARD_EXPERIENCE_CONTRACT.md` **and** design-language grammar declarations.

Until those amendments land, agents should treat **design language + nav map as overriding
charter UI hints** on conflict (same precedence pattern charter already uses for semantics vs
roadmap wording) — but that precedence is **not yet explicit in the charter text**.

---

## Headline recommendation

**Accept with named amendments** — keep the autonomy, verification, and domain-governance
core; amend landing/report/demo sections to cite the frozen design language and grammar 6 so
charter-guided builds cannot resurrect retired dashboard patterns or unconstrained report builders.
