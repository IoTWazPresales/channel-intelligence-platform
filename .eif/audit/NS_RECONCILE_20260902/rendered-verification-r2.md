# Rendered verification — N-0013 amendment (r2)

**Run:** `NS_RECONCILE_AMEND_20260902`  
**Actor:** agent  
**Date:** 2026-09-02  
**Supersedes:** `rendered-verification.md` (r1 — mobile PASS **withdrawn**)

---

## Method

Static HTML opened at declared viewports. r1 mobile PASS retracted after operator challenge; mockups amended before re-verification.

| Viewport | Width | Artifacts |
|---|---|---|
| Desktop | 1280px | shell, Position/Cover, Reports utility, Admin utility |
| Mobile | 390px | `platform-shell-mobile.html` (uses `cip-base.css`, not `cip.css` row-nav breakpoint) |

---

## r1 correction

| r1 claim | Finding | r2 status |
|---|---|---|
| Mobile drawer PASS | `cip.css` `@media (max-width:767px)` forced `.nav { flex-direction: row }` inside drawer; spine clipped | **FAIL (r1)** → **PASS (r2)** after isolated mobile stylesheet |
| Independent review focus-visible | `cip.css` had no `:focus-visible` rule; claim unsupported | **Corrected** — `cip-base.css` includes explicit rule |

---

## Desktop — Brief shell (`platform-shell-desktop.html`)

- Spine: **Brief · Plan · Position · Settlement · Actions · Imports**
- Utilities link to demonstrated hubs (not text-only sub-bullets)
- Footnote references D-0003 for KPI placement (not pre-decided)

**Verdict:** PASS

---

## Desktop — Position / Cover (`position-cover-desktop.html`)

- Job label **Position** avoids collision with product name and `/channel-intelligence` context route
- Lenses: Cover · Movement · Fill vs plan · Inbound
- Context route called out in filter-note

**Verdict:** PASS

---

## Desktop — Reports utility (`reports-utility-desktop.html`)

- Three tiles: **Build**, **Dashboards**, **Inbox** — distinct jobs demonstrated
- Dashboards explicitly separated from Brief attention queue
- Routes proposed under `/reports/*` namespace

**Verdict:** PASS

---

## Desktop — Admin utility (`admin-utility-desktop.html`)

- Grouped: Access · Settings · Operations · Trust (audit + SQL)
- Boundary vs Imports container stated

**Verdict:** PASS

---

## Mobile — drawer shell (`platform-shell-mobile.html` @ 390px)

- Vertical nav in drawer panel; all six jobs visible without horizontal clip
- Utility sub-labels: Build/Dashboards/Inbox; Access/Platform/Trust
- Brief content column below scrim (drawer-open state for evidence)

**Verdict:** PASS (honest at 390px)

---

## States not yet mocked (acceptable deferral)

- Imports container interior
- Actions container interior
- Reports Build composer canvas (reference: `docs/design/reports-builder.html`)
- Mobile Position grid (desktop-first per design language)

---

## Summary

Amended evidence set supports architecture **structure** and contested **utility boundaries**. Capability decisions D-0002 and D-0003 remain operator-owned and are not proven by mockups alone.
