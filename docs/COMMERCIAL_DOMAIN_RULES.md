# Commercial Domain Rules

**Owner:** Warren (domain ground truth) · **Version:** 1.0 · 2026-07-31
**Status:** authoritative. Agents never override these; changes require Warren's written
correction and a version bump.

These are commercial facts about how the business actually works, captured from Warren
directly. They govern the budget, forecasting, lineup and CST modules. Where a rule is marked
**TENANT-VARIABLE**, it must be implemented as configuration — the ASUS South Africa answer is
an example of the shape, never the definition.

---

## 1. Budget and support

**1.1 Budget is derived, not allocated.** There is no separately handed-down funding pot. The
reservation is **embedded in the lineup's profit line**: PM bottom sets the floor, planned
profit carries the reserved support inside it. The "pot" is the aggregate of what PMs reserved
when they planned. This is why the split flexes with profit expectation.

**1.2 Budget attaches to the quarter the stock LANDED** — not the quarter it shipped, and not
the quarter it was planned. Landing quarter is a first-class axis, not a deferred lens.

**1.3 Fill rate remains shipped-basis.** Two axes coexist and must not be conflated:
- Fill rate / plan execution → **shipped** (`line_state='shipped'`)
- Budget consumption → **landed** (`pod_date` derived quarter)

**1.4 Currency: USD, derived backwards from Rand.** Local operating currency is ZAR; support
is denominated USD. **TENANT-VARIABLE** — the pairing must be configurable, not hardcoded.

**1.5 FX rate handling varies by customer and channel.** A rate may be **booked** (fixed at a
point and held) or **left floating**. Both must be supported per case; the mode is an attribute
of the case, not a global setting.

**1.6 Unspent support returns.** Approved-but-under-delivered support is released back for
potential reuse. Cancelled cases free their budget immediately.

**1.7 Pot grain: per sales model, per customer — movable.** Allocation is not rigid; support
can be moved between grains. The model must permit reallocation with an audit trail rather
than enforcing hard partitions.

**1.8 Constraint type: undetermined.** Whether the binding constraint is total money or a
support-% ceiling per unit is not settled. Implement spend tracking against both views; do not
hard-enforce either until Warren confirms.

**1.9 PM bottom is fixed per quarter** — not negotiated per deal. A per-SKU floor held for the
quarter.

**1.10 The 50/50 split is a volume split, not a cost split.** A lineup line divides into
**stock to be sold at normal price** and **stock to be sold at discount**. The nominal plan is
50/50 but the actual split follows profit expectation.

**Data-model consequence:** a lineup line carries two commercial treatments. Today this is
implicit in the PM workbook via PM bottom and the profit line. At P1 lineup load, discovery
must handle both cases: capture an explicit reservation/split column if present, otherwise
derive it from PM bottom versus planned price. This affects lineup schema, CPOR linkage,
budget consumption and fill-rate attribution — settle it before A1 ships.

---

## 2. Forecasting

**2.1 Grain and rollup.** Forecast computes at the finest available grain
(product × customer × period) and **rolls up by summing**. Quarter re-derivation is available
as a *comparison view*, never as the primary number — summing is explainable when a PM
challenges it.

**2.2 History is plentiful.** Seasonality may be trusted as soon as confidence supports it;
there is no artificial minimum-history bar. Confidence banding must be explicit.

**2.3 New products with no sell-out history** are forecast by analogue: spec, segment, price
band, GPU, and predecessor model. The analogue chosen must be recorded as provenance on the
forecast row.

**2.4 Forecast is never merged into actuals.** It is a separate, explicitly labelled layer. A
missing actual is never gap-filled with a prediction.

---

## 3. Lineup planning — net requirement, not raw forecast

**3.1 The lineup quantity is a net requirement**, not the demand forecast:

```
Lineup qty = forecast demand
           − channel stock on hand
           − in-transit
           + target cover
```

**3.2 Target cover is expressed in weeks of stock, set per product.**
**TENANT-VARIABLE** — grain (per product / BU / customer) and unit (weeks vs units) must be
configurable.

**3.3 In-transit means:** shipped-not-landed **plus** open POs where a PO exists. No PO, no
in-transit contribution — consistent with the existing hard rule that PO is required for
lineup linking.

**3.4 Consequence:** the lineup builder consumes A3 (channel stock, cover) as well as B1
(forecast) and A1 (bias correction). B2 cannot be built before A3.

---

## 4. Module consequences

**4.1 B2 and B3 merge.** A lineup builder that does not compute profit-with-reservation is not
usable by a PM. Budget is not a separate downstream module; it is part of authoring a lineup.

**4.2 A1 gains a support-bias metric.** Planned reservation versus actual CPOR spend, sitting
alongside volume bias. ("PMs reserve 12% and spend 19%.") This requires landing-quarter
derivation in A1/A2 core.

**4.3 BACKLOG-068 is superseded.** Landing-quarter derivation and `pod_date` completeness move
from deferred to **A1/A2 core scope**. Fill rate stays shipped-basis; budget consumption is
landed-basis.

---

## 5. CST — sell-through

**5.1 Not a single pilot.** Multiple customers send weekly files directly: Takealot, Evetech,
Computer Mania, Incredible Connection, Amazon, HiFi Corp, Makro, Game.

**5.2 Consequence:** P4 is a multi-format ingest problem from day one, not a single-format
pilot. Expect a distinct layout family per customer. The header-vocabulary config work
(D-022) is a hard prerequisite, and per-customer layout profiles are the shape.

**5.3 Forward-only still holds.** Start from current files; historical backfill remains an
optional later job.

**5.4 Branch/location detail** (e.g. "Computer Mania Centurion") models as account + location,
never as an alias to the parent. Deferred by design; blocks tagged-customer sell-through
reporting until built.

---

## 6. Operating context

**6.1 Deployment deferred.** The application is being completed to run **locally** for now.
Hosting, environments and remote access are out of scope until Warren sets a hosting target.
Multi-user readiness (auth, roles, user management, app shell) remains in scope and is
buildable locally.

**6.2 User management is admin-driven.** An admin adds users and assigns roles; no
self-registration.

**6.3 Reporting audience is everyone.** Any user may build reports, not only Warren. Both
Excel and PDF export required. Email delivery mechanism is unconstrained.

**6.4 No external deadline.** Accuracy and optimisation over speed. This does not license
unbounded polish — module exit criteria and time budgets still apply.

**6.5 Sole contributor.** No other person touches the repository.

**6.6 IP ownership: Warren.** The platform is Warren's to commercialise. Multi-tenant
productisation (P6) is a legitimate objective, and no ASUS-specific assumption may be baked
into application code.

---

## Still open

| # | Question | Blocks | Owner |
|---|----------|--------|-------|
| 1 | Constraint type — money ceiling or support-% ceiling per unit? (1.8) | Budget enforcement | Warren |
| 2 | Is the lineup reservation an explicit column in the PM workbook, or purely derived from PM bottom vs planned price? | Lineup schema | **P1 discovery** |
| 3 | Hosting target, budget, data residency | Deployment | Warren, deferred |
| 4 | Per-customer CST file formats | P4 | Discovered at first load |
