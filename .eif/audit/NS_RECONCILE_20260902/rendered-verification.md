# Rendered verification — N-0013 Full-Platform Architecture

**Run:** `NS_RECONCILE_20260902`  
**Actor:** agent  
**Date:** 2026-09-02  
**Node:** N-0013  
**Artifact class:** high_fidelity (isolated audit mockups)

---

## Method

Static high-fidelity HTML mockups rendered in browser at declared viewports. Not product source — proposal evidence for operator approval.

| Viewport | Width | Artifacts inspected |
|---|---|---|
| Desktop | 1280px | `platform-shell-desktop.html`, `channel-cover-desktop.html` |
| Mobile | 390px | `platform-shell-mobile.html` |

Gallery entry: `.eif/audit/NS_RECONCILE_20260902/index.html`

---

## Desktop — platform shell (Brief)

**File:** `platform-shell-desktop.html`

- Spine shows **Brief · Plan · Channel · Settlement · Actions · Data** with mono count badges
- Reports utility shows sub-links: Builder · Dashboards · Inbox (RESTORE per reconciliation)
- Admin utility shows sub-links: Users · Settings · SQL · Ops · Audit (RESTORE)
- Brief grammar-3: Read strip + ranked signal list; no KPI card row
- Slim top strip only — no double AppBar
- Signal row CTAs deep-link to named containers (Data, Channel, Settlement, Plan)

**Verdict:** PASS — proposed IA and naming visible at desktop.

---

## Desktop — Channel container (Cover lens)

**File:** `channel-cover-desktop.html`

- Container labelled **Channel** (not Stock)
- Lenses: Cover · Movement · **Fill vs plan** (renamed from Execution) · Inbound
- Grammar-2: sticky scope bar + WoC histogram instrument + grid
- No legacy KPI card row above instrument
- Read/context references Actions for buy ranking

**Verdict:** PASS — Channel rename and lens vocabulary demonstrated.

---

## Mobile — platform shell

**File:** `platform-shell-mobile.html`

- Hamburger opens drawer spine with all six job containers + utilities
- Brief attention queue readable at 390px
- Slim chrome — no legacy AppBar density toggle
- Grid-heavy Channel surface gated (copy directs to desktop)

**Verdict:** PASS — mobile shell direction demonstrated.

---

## Design language conformance

| Criterion | Result |
|---|---|
| Tokens (--bg, --elev, --ac, IBM Plex Mono) | Match FROZEN v1.1 |
| Grammar 3 Brief blotter | Read strip + ranked signals |
| Grammar 2 Channel | Scope bar + lens switcher + instrument |
| One dominant element per screen | Histogram on Channel; signal list on Brief |
| Severity two-channel | Color + position on signals and WOC |

---

## States covered

- [x] Populated Brief signals
- [x] Populated Channel grid with selection
- [x] Mobile drawer nav
- [x] Utility sub-link expansion
- [ ] Empty states (deferred to implementation waves)
- [ ] Loading/error (deferred to primitive library Phase B)

---

## Summary

High-fidelity rendered evidence produced for proposed full-platform architecture: renamed six job containers, expanded utilities, unified slim chrome, and Channel lens vocabulary. Ready for independent review (gov-008).
