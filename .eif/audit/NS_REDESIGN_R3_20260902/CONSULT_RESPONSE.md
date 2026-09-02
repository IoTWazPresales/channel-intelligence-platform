# CONSULT ÔÇö N-0013 r3 Information Architecture

Independent review. I have **not** rendered anything this session; I'm reasoning from the seed evidence and flagging UNVERIFIED where a claim needs a rendered artifact to settle. No files edited.

**Headline:** The axis that best fits *this* capability set is **capability domains (A)** ÔÇö but only if its overview pages genuinely compose, and only when it absorbs the two good ideas from B and C (entity-context drill, and a composed home + palette). B and C each contain one essential mechanism but fail as the *primary* axis for opposite reasons. I define that hybrid as **H** and rank it first.

---

## Q1 ÔÇö Primary axis

**Recommendation: Domains (A).** It is the only axis where *both* problem populations have a legible home:
- **Orphans** (import / steward / ops / SQL / users ÔÇö "no natural entity") ÔåÆ land cleanly in *Data & Stewardship* and *Administration*, which are themselves legible domains.
- **Cross-entity analytics** (cover, plan-vs-executed, SOH reconciliation, lineup, settlement economics) ÔåÆ land in their domain (cover ÔåÆ Stock & Sell-through; lineup ÔåÆ Planning). These are the product's differentiating value, and they belong to no single entity ÔÇö which is precisely why B strands them.

Domain nouns ("Stock & Sell-through", "Supply & Inbound", "Funding & Settlement") carry high information scent: reading the rail teaches an unfamiliar operator *what the product knows about* and *its breadth* in one pass ÔÇö the first two clauses of the test.

**Strongest counter-argument:** A degrades into the rejected IA-with-nicer-labels if the domain pages are just folders over the existing routes. The operator said the rejection was "not a rename problem" ÔÇö so if *Stock & Sell-through* is merely a container for today's routes, nothing structural changed. A's validity is **conditional** on each domain having a real overview page (headline governed metrics + that domain's attention items with counts + workflow links).

**Evidence that settles it:** A rendered domain-overview at 1280px composing (a) headline metrics, (b) domain attention items, (c) workflow links ÔÇö plus a first-click/tree-test: give unfamiliar users tasks ("find weeks of cover for a distributor") and measure first-click-correct. >~70% settles A; a folder-only mock will fail it.

---

## Q2 ÔÇö First destination & DashboardsÔåöReports

**Recommendation: one composed Overview containing both, as two distinct zones ÔÇö not merged.**
- **Dashboard = the overall business view** (operator says it's strategically important ÔåÆ give it the prime real estate).
- **Brief = operational attention** (counts + deep links).
- Co-locating them, visibly separated, is what makes the test's final clause ÔÇö *distinguish business view from operational work* ÔÇö literally visible on the landing page.

**Dashboards Ôåö Reports are siblings, not parent/child.** Reports = *ask* (governed builder: metric/grain/dimensions, run/save/export/schedule ÔåÆ pull, question-answering). Dashboards = *keep showing me* (persistent 12-col monitoring surface ÔåÆ push, at-a-glance). The clean coupling that honours the operator's rejection of "saved-report-under-Reports": **a saved report can be pinned as a Dashboard widget** ÔÇö Reports authors widget content; Dashboards is not subordinate to it. Reports lives in the analytics/Explore area; the Dashboard is promoted to Home.

**Strongest counter-argument:** Today the Brief renders "four text rows + ~55% empty viewport" with "9.5px" headline strips, and Dashboards is an empty state. Co-locating two under-populated things yields a *worse* first impression than one strong surface ÔÇö and a blank configurable canvas is a hostile first-run experience.

**Evidence that settles it:** rendered Home at 1280px **and** 390px with a **seeded default dashboard** (real governed metrics) + Brief with real counts. Require viewport fill >~85% and KPI numerals at legible size (ÔëÑ24ÔÇô32px, not 9.5px). If real data can't fill it, fall back to **Brief-primary with a prominent Dashboard entry point** rather than shipping two weak zones.

---

## Q3 ÔÇö Thin scaffolds (pricing/promotions/competition/roadmap/budgets/market)

**Recommendation: data-gated visibility, not all-or-nothing.** Group them under one legible domain (*Commercial inputs* / "Plan inputs & evidence"), but **only expose leaves that hold real data.** The seed's data layer lists *price observations* and *promotion/pricing plan inputs* ÔÇö those compute/store something and earn a visible leaf. Pure-scaffold leaves with zero behaviour (competition/roadmap/budgets/market, if empty) should be **hidden or behind a "coming" affordance**, never given equal rail weight.

Empty leaves are corrosive: they teach the user that rail labels *don't* predict content ÔÇö which is the exact scent failure that got the prior IAs rejected.

**Strongest counter-argument:** the operator wants breadth legible; hiding scaffolds hides genuine roadmap signal. And a mostly-empty *Commercial inputs* domain advertises breadth the product can't honour ÔÇö arguably worse for trust than omission.

**UNVERIFIED / evidence that settles it:** the seed both lists these as "scaffolds with thin behaviour" *and* names price-observation / plan-input data ÔÇö so which scaffold actually *renders* real data today is unresolved from the seed. Render each route at 1280px and apply the rule mechanically: real data ÔåÆ visible leaf; zero data ÔåÆ hidden.

---

## Q4 ÔÇö Cross-job mapping/resolution queue

**Recommendation: durable home + push signal (two channels).**
- **Home:** a first-class *Mapping & Resolution* destination inside *Data & Stewardship*, beside Stewarding / Masters / Import Center ÔÇö discoverable by browsing, independent of the retire/replace decision.
- **Push:** surface pending items as a Brief attention signal (count + deep link) so it's *reachable* the moment it needs action.

Mapping is cross-job and entity-adjacent (tokenÔåÆdimension); it belongs with stewarding, not scattered per-import-job.

**Strongest counter-argument:** the *per-job* resolution workspace is already a rich benchmark surface. A relocated cross-job queue could fragment a working flow; better may be a cross-job **aggregation view layered on top of** the existing per-job workspaces, not a move.

**UNVERIFIED / evidence that settles it:** whether a cross-job queue exists today or only per-job; and whether stewards work job-by-job or need a backlog across jobs. Render current per-job vs. a proposed cross-job aggregate and count clicks-to-resolve.

---

## Q5 ÔÇö Does role change the rail?

**Recommendation: role changes defaults, landing, and leaf-visibility ÔÇö not top-level structure.** Keep the domain set **stable across roles** so breadth stays consistently legible, one mental model is learnable, and cross-role conversations reference the same map. Within domains, hide leaves a role can't access (admin, steward audit, SQL) ÔÇö consistent with the existing role model that already "controls visibility of admin/steward leaves." Tune landing + default dashboard/queues per role (planner ÔåÆ planning attention; steward ÔåÆ resolution queue).

**Strongest counter-argument:** viewers/planners seeing domains they can never act in (Administration; Data they can't steward) is noise; a role-pruned rail might test better for single-role users.

**Evidence that settles it:** per-role tree-tests, stable-rail-with-hidden-leaves vs. role-pruned-rail, measuring whether viewers are confused by visible-but-empty domains. Absent that, stable structure is the safer default ÔÇö it preserves the "recognise major areas / understand breadth" clause for *every* user, which the operator prioritised.

---

## Q6 ÔÇö 390px workflows & dense grids

**Genuinely mobile (away-from-desk) = attention / approval / lookup, not authoring:**
- Brief attention triage (read signal ÔåÆ tap through)
- Steward/mapping approve-reject (discrete decisions ÔÇö mobile-native)
- Entity lookup via context panel (scan a distributor/product: cover, recent shipments, open funding)
- Settlement/CPOR status checks, possibly blocked-item approval

**Desktop-first (degrade to read-only, defer only the authoring action ÔÇö not a generic "open on desktop"):** report builder, dashboard editor, lineup planning grid, import mapping setup.

**Dense grids at 390px ÔÇö rule by grid *purpose*:**
- **Decision/lookup grids** (steward queue, masters) ÔåÆ transform each row into a stacked **record card** (entity name as title + 2ÔÇô3 primary/governed fields, rest tap-to-expand). Steward queue = vertical stack of one decision each. **No horizontal scroll of a 12-col grid.**
- **Comparison/ranking grids** (lineup rankings, cover across distributors) ÔåÆ cards *lose the comparison that is the point*; use a **frozen-first-column mini-grid** or a purpose-built mobile ranking view.

**Strongest counter-argument:** a blanket card transform destroys cross-row comparison; the transform must branch on whether the grid's job is decision/lookup (cards win) or comparison/ranking (frozen-column wins).

**UNVERIFIED / evidence that settles it:** the seed asserts "mobile must be useful" but does **not enumerate the mobile tasks.** That field-workflow list is the missing evidence. Render 390px states of Brief, steward queue, one master grid, and lineup rankings with real data to confirm the branch.

---

## Q7 ÔÇö What was structurally wrong before; who repeats it?

The rejected IAs were **process-stage / cadence sequences** (Plan┬ÀPosition┬ÀSettlement┬ÀActions┬ÀResponse┬ÀSteward). Structural (not label) faults:
1. **Low scent** ÔÇö stage verbs describe abstract *doing*, not the *nouns* operators recognise; can't map "weeks of cover" ÔåÆ "Position" without training.
2. **Hides breadth** ÔÇö a linear pipeline reads as one flow, masking that CIP is a multi-domain analytical platform; under-sells the product.
3. **Ambiguous placement** ÔÇö cross-cutting capabilities (reports, dashboards, search) belong to no stage, so they're assigned arbitrarily ÔåÆ can't "predict where it lives."
4. **Can't separate business-view from operational-work** ÔÇö one sequence collapses both.

**Who repeats it:**
- **C (Home/Work/Explore) repeats faults 1 & 3 directly** ÔÇö "Work"/"Explore" are cadence buckets with the same low scent and placement ambiguity (is a report Work or Explore? is the steward queue Work or Data?). Its command-palette patch is a *tell*: needing a search crutch to find things **is** the symptom of the rejected structure.
- **B (entities) repeats fault 2 in mirror** ÔÇö reveals *object* breadth but hides *analytical/capability* breadth; under-sells what the product computes.
- **A (domains) structurally avoids all four** ÔÇö domain nouns carry scent (1), the domain set reveals analytical breadth (2), every capability has a home domain (3), and a distinct Overview separates business-view from operational domains (4) ÔÇö **conditional** on overview pages composing rather than foldering.

**Live disagreement to flag:** one could argue the prior failure was *lexical* (bad labels) and a well-labelled cadence IA could pass ÔÇö but the operator's "not a rename problem" points to structure, and cadence axes carry intrinsic placement ambiguity that labels can't fix.

**Decisive experiment:** tree-test A vs. B vs. C rails on real capability-finding tasks. If C with strong labels matches A on first-click success ÔåÆ the fault was lexical. If C still trails ÔåÆ structural. This single test resolves Q1 and Q7 together.

---

## Ranked alternatives

**Rank 1 ÔÇö H (recommended hybrid): Domains-primary + composed Overview + entity-context panel + command palette.**
Rail = capability domains (A). First destination = composed Overview (configurable Dashboard as business view + attention Brief as operational, distinct zones, seeded per role). Every number drills to an **entity context panel** (B's essential mechanism, as slide-in). **Command palette + capability directory** (C's essential mechanism) as a findability accelerator, not a crutch. Reports and Dashboards are siblings; a saved report feeds a widget.
*Risks:* (a) overview pages become empty folders ÔåÆ re-triggers the rejection ÔÇö **gate: no domain ships without composed metrics+attention+links**; (b) two-weak-things landing ÔåÆ **gate: seed dashboards, only ship composed home at >85% viewport fill**; (c) real scope beyond a rename (panel + palette + overviews); (d) domain-boundary disputes (plan-vs-executed ÔåÆ Stock or Planning?) ÔåÆ **needs a documented placement rule: assign by the primary governed metric/entity.**

**Rank 2 ÔÇö A pure (domain rail + simple overviews, Brief as landing).**
Lower build cost, still passes breadth/scent. *Risk:* loses B's drill-to-object and C's palette; under-places the strategically-important Dashboard ÔåÆ partially re-triggers the "Dashboards subordinated" objection the operator rejected.

**Rank 3 ÔÇö B (entities) primary.**
Concrete object model; masters/steward fit; drill-to-object native. *Why not higher:* strands the orphan capabilities and, worse, hides the cross-entity analytical value (cover, lineup, reconciliation, settlement economics) that differentiates the product ÔåÆ fails "understand what CIP does" on the analytics dimension. **Best used as the drill layer inside Rank 1, not the rail.**

**Rank 4 ÔÇö C (Home/Work/Explore) primary.**
Matches operator cadence; Home-as-dashboard aligns with the strategic dashboard goal; role queues match steward/planner behaviour. *Why last:* lowest scent; structurally repeats the rejected cadence axis (faults 1 & 3); command-palette dependency concedes the rail fails findability. **Its good ideas (composed Home, palette) are fully salvageable as components of Rank 1 without adopting its rail.**

---

**Bottom line:** Adopt **H** ÔÇö domains as the legible primary axis, with a composed Overview as the first destination, entity drill as a panel, and a palette as accelerator. The whole recommendation hinges on one non-negotiable: **domain overview pages and the Home must compose real data before shipping** ÔÇö otherwise A is just the rejected IA with better labels, which the operator already refused.

Want me to record this verdict as a one-line memory entry (matching your existing consult-log convention), or leave it unsaved?
