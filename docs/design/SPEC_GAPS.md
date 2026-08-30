# CIP design language — spec gaps

Add-only log of places a surface needed something `CIP_DESIGN_LANGUAGE.md`
does not specify. Implementers build the closest conforming version and record
the gap here; they do not improvise a new visual language.

Fable / Warren may fold entries back into the spec (spec §8.3).

---

## GAP-001 — Histogram instrument (grammar 2)

**Found:** Cover mockup, 2026-08-30, `docs/design/stock-cover.html`.

**Spec says:** §4 grammar 2 names “population instrument (histogram / trend
panel with metric switcher / shape strip)”. §3 inventory specifies shape
bars, concentration lists, case-pane tabs, and the funding spark micro-viz —
not histogram construction (bucket width, mean marker, selected-range
treatment, switcher placement relative to the Read).

**Closest conforming version:** WOC-bucket columns using funding spark-bar
craft (solid `--ok/--wn/--st` fills, mono caps, no gradient-as-identity);
mean as an 11px provenance caption on the tail bucket; selected `<4w` range
as a 2px `--st` underline (color + position, two channels); metric switcher
as the case `.tabs` component placed on the instrument, not a second lens
row.

## GAP-002 — One visual form vs Cover as distribution

**Found:** Cover mockup, 2026-08-30.

**Spec says:** §5 “A metric switcher is allowed only when one visual form
serves several metrics (the Channel trend instrument: sell-out / fill /
cover / inbound by week).”

**Tension:** Cover’s decision question is mean-vs-tail (24.3w vs 119 pairs
under 4w), which a weekly trend does not answer. This mockup renders **Cover
as a distribution histogram**. Sell-out / Fill vs plan / Inbound tabs are
present and unselected; they are not given a second visual form in this
file.

**Ask of the spec:** either (a) allow Cover to use a distribution form while
the other three metrics share a weekly trend, or (b) require one form and
name it.

## GAP-003 — Book-level blocked / stale on grammar 2

**Found:** Cover mockup, 2026-08-30 (SOH reconciliation not run).

**Spec says:** §6 “blocked (reason inline, e.g. FX undeclared)” — the
reference artifact shows this as a **row** badge plus a hatched book-shape
segment.

**Closest conforming version:** book-level condition as an inline
`.badge.blocked` on the Read line (same badge component), restated in the
grid footer provenance. No invented recon column (would be a sixth severity
channel).

## GAP-004 — Lens names vs instrument switcher labels

**Found:** `CIP_NAV_MAP.md` §3 vs spec §5 vs Task 3 brief.

**Map lenses:** Cover · Movement · Execution · Inbound.

**Spec / brief switcher:** Sell-out · Fill vs plan · Cover · Inbound.

This mockup uses the spec/brief switcher only (one control, not a lens row
plus a switcher). Map lens names remain proposals.
