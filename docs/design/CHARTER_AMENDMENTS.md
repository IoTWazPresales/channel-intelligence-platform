# Proposed amendments — `docs/AUTONOMOUS_BUILD_CHARTER.md` v1.2

**Date:** 2026-08-30  
**Status:** draft for Warren adjudication — **do not apply to the charter until accepted.**  
**Source review:** `docs/design/CHARTER_REVIEW.md` §(e), plus amendment 7 (VERIFY fallback).

These amendments are **targeted** corrections where the charter predates the frozen design
language or has proven unenforceable in practice. They do **not** loosen the safety spine
listed under [Gates kept as-is](#gates-kept-as-is) below.

---

## Gates kept as-is

The following charter gates remain **unchanged** by this amendment set:

| Gate | Charter anchor | Why keep |
|---|---|---|
| **Migration approval** | Database policy — *"Alembic migrations against `cip` — **Explicit approval only.** Never unattended"* | Irreversible schema risk |
| **Clone-proof destructive paths** | RED zone; merges/supersessions/destructive bulk | Physically irreversible pointer rewrites |
| **NEVER PATCH** | *"A fix must name the root cause"* — prohibited symptom suppressions | Prevents debt disguised as done |
| **Contract rows before build** | *"every module carries enumerated contract rows **written before implementation**"* | Prevents verifying only what was built |
| **AMBER domain sign-off** | Design-stage halt for new semantics; post-build data-load sign-off | Agent cannot judge commercial plausibility |
| **Question queue** | Mandatory append; empty queue after module is a finding | Surfaces unknowns the agent did not notice |

Amendments 1–6 align UI work with frozen design docs. Amendment 7 adds a **tracked fallback**
for VERIFY unavailability — it does **not** remove VERIFY, self-PASS prohibition, or
contract-row requirements.

---

## Amendment 1 — Governing design documents (charter header)

**Current (lines 6–14):**

> This governs how Cursor builds the remainder of CIP with bounded autonomy — zones, gates,
> verification, and the Cursor ↔ CLI dual-agent loop. It sits **under** `docs/ROADMAP.md`
> (what to build, in what order), is bound by `docs/COMMERCIAL_DOMAIN_RULES.md` (**domain
> ground truth — never overridden**), and sits **beside**
> `docs/STEWARD_EXPERIENCE_CONTRACT.md` (what done means),
> `docs/STEWARD_ENGINE_DECISIONS.md` (why it's built this way), and
> `docs/COMMERCIAL_SEMANTICS.md` (metrics, grains, owning surfaces — **authoritative**).
> A metric mattering to a phase does not make that phase's screen its home. Where they
> conflict, the contract, decisions log, and commercial semantics win.

**Proposed replacement:**

> This governs how Cursor builds the remainder of CIP with bounded autonomy — zones, gates,
> verification, and the Cursor ↔ CLI dual-agent loop. It sits **under** `docs/ROADMAP.md`
> (what to build, in what order), is bound by `docs/COMMERCIAL_DOMAIN_RULES.md` (**domain
> ground truth — never overridden**), and sits **beside**
> `docs/STEWARD_EXPERIENCE_CONTRACT.md` (what done means),
> `docs/STEWARD_ENGINE_DECISIONS.md` (why it's built this way),
> `docs/COMMERCIAL_SEMANTICS.md` (metrics, grains, owning surfaces — **authoritative**),
> `docs/design/CIP_DESIGN_LANGUAGE.md` (**FROZEN — UI grammar, components, anti-patterns**),
> and `docs/design/CIP_NAV_MAP.md` (job containers, spine labels, disposition).
> A metric mattering to a phase does not make that phase's screen its home. Where they
> conflict, the contract, decisions log, and commercial semantics win for **metrics and
> domain rules**; for **UI implementation**, the frozen design language and nav map win.

**Prevents:** implementers following the charter alone rebuilding retired KPI-card landing or
off-spine surfaces the design freeze already disposed.

---

## Amendment 2 — P2-4 app shell exit criterion

**Current (module table, P2-4 row):**

> | **P2-4 App shell + landing** | Navigation, IA, landing surface, freshness banner | A manager reaches any surface unaided | AMBER | 2 sessions |

**Proposed replacement:**

> | **P2-4 App shell + landing** | Navigation, IA, Brief (grammar 3 signal blotter), spine per nav map | Brief (grammar 3) reachable; spine matches `CIP_NAV_MAP.md`; manager reaches any container unaided | AMBER | 2 sessions |

**Prevents:** P2-4 scope creep into dashboard/control-tower KPI cards retired by the nav map.

---

## Amendment 3 — P3-3 report builder

**Current (module table, P3-3 row):**

> | **P3-3 Report builder** | Build, slice, filter, visualise; author + consume modes | A governed report built end-to-end in UI | AMBER | 3 sessions |

**Proposed replacement:**

> | **P3-3 Report builder** | Grammar 6 Composer (source/scope · artifact canvas · output panel); preview before save; named saved views; scheduled delivery | A country-manager pack assembled end-to-end per `reports-builder.html`; preview step exercised; test send does not substitute for preview | AMBER | 3 sessions |

**Prevents:** an unconstrained BI-style builder that violates grammar 6 (KPI-card composers, filter-memory-as-saved-view).

---

## Amendment 4 — Demo spine

**Current (The demo artifact):**

> **Minimum demo spine:** login → landing surface with freshness → plan accuracy and PM bias
> across years → promo effectiveness → author next quarter's lineup → scheduled report landing
> in an inbox.

**Proposed replacement:**

> **Minimum demo spine:** login → **Brief** (signal blotter) → **Lineup** (plan origination) →
> **Stock** (cover lens) → **Settlement** (case book) → **Response** (ranked actions) →
> **Reports** (scheduled country-manager pack in inbox). No KPI-card landing.

**Prevents:** demo scripts and AMBER gates that still walk a retired control-tower landing.

---

## Amendment 5 — Design packet scope

**Current:** *(no charter text — `PACKET_DATA.md` is absent from governing-doc list.)*

**Proposed addition** (new subsection after Scalability constraint, or footnote in Browser verification):

> **Design packet (`docs/design/PACKET_DATA.md`):** canonical figures for `docs/design/*.html`
> mockups only. Production surfaces reconcile to loaded facts and `COMMERCIAL_SEMANTICS.md`;
> mockup packet figures are not production truth.

**Prevents:** agents treating design mockup numbers as reconciliation targets on live `cip` data.

---

## Amendment 6 — Contract row sources for UI surfaces

**Current (Scope lock / contract scoping):**

> Greenfield → interview (max 5 questions/round). Complete BACKLOG → short scope lock.
> Steward/import: CONSULT enumerates S-rows of `STEWARD_EXPERIENCE_CONTRACT.md`; exclude only
> with Warren waiver line. Reduced "lean/chrome-only" scope without waiver → defective prompt.

**Proposed replacement:**

> Greenfield → interview (max 5 questions/round). Complete BACKLOG → short scope lock.
> Steward/import: CONSULT enumerates S-rows of `STEWARD_EXPERIENCE_CONTRACT.md`; exclude only
> with Warren waiver line. **New UI surfaces:** contract rows must cite the declared grammar
> from `CIP_DESIGN_LANGUAGE.md` §4 and the owning container from `CIP_NAV_MAP.md` in addition
> to any steward S-rows. Reduced "lean/chrome-only" scope without waiver → defective prompt.

**Prevents:** UI modules shipping without grammar/container contract coverage while steward rows alone claim completeness.

---

## Amendment 7 — VERIFY availability fallback

**Current (Dual-agent quality bar):**

> | **Cursor must not self-PASS** | After clone/parity units, seed CLI VERIFY; only `VERDICT: PASS` closes. |

**Current (Hard gate):**

> **Hard gate:** no next-unit implementation until `VERDICT: PASS` (or Warren written waiver
> in CURRENT).

**Evidence of failure mode:** seven consecutive units (6f–B4) shipped without VERIFY when the
consultant was unavailable, with the debt untracked — the gate eroded silently because it was
unenforceable in practice.

**Proposed replacement (quality bar row):**

> | **Cursor must not self-PASS** | After clone/parity units, seed CLI VERIFY; only `VERDICT: PASS` closes. When VERIFY cannot run (consultant unavailable), record a **VERIFY-debt** entry in `docs/BACKLOG.md` naming the unit and what VERIFY would check; unit may close; debt must be cleared before promotion to `main`. |

**Proposed replacement (hard gate paragraph):**

> **Hard gate:** steward/import parity units require `VERDICT: PASS` (or Warren written waiver
> in CURRENT) before promotion to `main`. When VERIFY cannot run, a VERIFY-debt BACKLOG entry
> is mandatory; **outstanding VERIFY debt blocks promotion to `main`, not the next unit.**
> Cursor must not self-PASS without PASS, waiver, or recorded debt.

**Prevents:** a safety gate eroding silently because it is unenforceable in practice, while
preserving VERIFY as a merge blocker rather than a serialisation stop.

---

## Summary table

| # | Target | Action |
|---|---|---|
| 1 | Charter header | Add frozen design language + nav map to governing docs |
| 2 | P2-4 module row | Brief grammar 3 + nav-map spine |
| 3 | P3-3 module row | Grammar 6 Composer + preview exemplar |
| 4 | Demo spine | Brief → containers → Reports (no KPI landing) |
| 5 | New subsection | `PACKET_DATA.md` mockup-only scope |
| 6 | Scope lock | UI contract rows include grammar + container |
| 7 | VERIFY gate | BACKLOG VERIFY-debt fallback; blocks main, not next unit |

**Headline:** accept charter v1.2 **with amendments 1–7** — targeted UI alignment and VERIFY
debt tracking; all listed KEEP-AS-IS gates unchanged.
