# CIP design language — spec gaps

Add-only log of places a surface needed something `CIP_DESIGN_LANGUAGE.md`
does not specify. Implementers build the closest conforming version and record
the gap here; they do not improvise a new visual language.

Fable / Warren may fold entries back into the spec (spec §8.3).

---

## GAP-001 — Histogram instrument (grammar 2) — **RESOLVED 2026-08-30**

**Disposition:** Folded into spec §3 (histogram instrument: bucket columns,
mean caption on tail bucket, selected-range underline, switcher as `.tabs` on
the instrument). Reference: `stock-cover.html`.

## GAP-002 — One visual form vs Cover as distribution — **RESOLVED 2026-08-30**

**Disposition:** Option (a) adopted in spec §5 — Cover uses distribution;
Sell-out / Fill vs plan / Inbound share weekly-trend form; one lens control.

## GAP-003 — Book-level blocked / stale on grammar 2 — **RESOLVED 2026-08-30**

**Disposition:** Folded into spec §6 — inline `.badge.blocked` on Read line +
grid footer provenance; no recon column.

## GAP-004 — Lens names vs instrument switcher labels — **RESOLVED 2026-08-30**

**Disposition:** Instrument switcher = lens control; labels Sell-out · Fill vs
plan · Cover · Inbound per confirmed Stock surface; map lens names aligned in
`CIP_NAV_MAP.md`.

## GAP-005 — Grammar-3 filter bar — **RESOLVED 2026-08-30**

**Disposition:** Brief exempt; period from tenant stamp (spec §3/§4).

## GAP-006 — Nav badge vs row count — **RESOLVED 2026-08-30**

**Disposition:** Badge = on-surface row count (spec §3); canonical figures in
`PACKET_DATA.md`.

## GAP-007 — Fill vs plan vs Pipeline fill % — **RESOLVED 2026-08-30**

**Disposition:** Lens-scoped names in spec §4/§5; canonical values in
`PACKET_DATA.md`.

## GAP-008 — Not received grain — **RESOLVED 2026-08-30**

**Disposition:** Open lines; partial receipt does not reduce count (spec §4;
`PACKET_DATA.md`).

## GAP-009 — Drill filter bar additive — **RESOLVED 2026-08-30**

**Disposition:** From/To/BU + saved view always present on drill (spec §3).

## GAP-010 — Lens control class name — **RESOLVED 2026-08-30**

**Disposition:** Behavior normative, class name not (spec §3).

## GAP-011 — Brief federated Read — **RESOLVED 2026-08-30**

**Disposition:** Federated by design; figures trace to signals/PACKET_DATA
(spec §5).

## GAP-012 — Concentration Read basis — **RESOLVED 2026-08-30**

**Disposition:** One basis; footer restates same basis (spec §5).

## GAP-013 — Lineup plan-owner affordances — **RESOLVED 2026-08-30**

**Disposition:** Folded into spec §4 grammar 2 — pending rows: Approve/Reject; Planned
column inline-edit cue; plan action bar (Net requirement · Calc · Export ·
Apply); decided rows keep badges only. Reference: `lineup.html`,
`lineup-pending.html`.

## GAP-014 — State-frame shell parity — **RESOLVED 2026-08-30**

**Disposition:** Folded into spec §6 — state frames (loading, empty, blocked,
filtered cut) keep full shell; only work area differs. Reference:
`lineup-pending.html`, `response-blocked.html`, `stock-cover-empty.html`.

## GAP-015 — SUGGESTED hint casing — **RESOLVED 2026-08-30**

**Disposition:** Folded into spec §3 — `.hint` class renders uppercase via CSS;
markup casing not normative. Reference: `brief.html`, `response.html`,
`funding-settlement-r3.html`.
