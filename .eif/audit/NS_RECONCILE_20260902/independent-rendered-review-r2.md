# Independent rendered review — N-0013 amendment (r2)

**Run:** `NS_RECONCILE_INDEPENDENT_R2_20260902`  
**Actor:** gov-008  
**Date:** 2026-09-02  
**Supersedes:** `independent-rendered-review.md` (r1)

---

## r1 failure analysis

| r1 finding | Actual evidence | Classification |
|---|---|---|
| Mobile drawer "improvement" / full spine PASS | r1 `platform-shell-mobile.html` + `cip.css` row-nav at ≤767px caused clipped horizontal nav | **Reviewer execution failure** — PASS recorded without viewport inspection |
| "Focus-visible inherited from cip.css" | r1 `cip.css` contained no `:focus-visible` rule | **Insufficient evidence inspection** — same run |

**EIF framework defect?** **No.** N-0013 already requires rendered evidence and independent review. Failure mode is **agent did not inspect artifacts at declared viewport** before recording PASS. No missing compile-time gate identified; optional future hardening: verification checklist artifact path + viewport dimensions in evidence JSON (programme hygiene, not EIF code change).

---

## Architecture challenge (amended)

| Question | r2 finding |
|---|---|
| Six job boundaries still valid? | **Yes** — job sequence unchanged; only labels and utility demonstration amended |
| **Channel** as spine label? | **Reject** — collides with product name "Channel Intelligence" and `/channel-intelligence` context route |
| Recommended spine label for stock/execution job? | **Position** — operator job is "where we stand" vs plan; distinct from CST intelligence context |
| **Data** as spine label? | **Reject** — subject area, not job |
| Recommended spine label for imports/steward job? | **Imports** — matches Import Center vocabulary; masters/worklists are sub-areas |
| Reports/Admin only as text sub-links? | **Insufficient** — r2 utility hub mockups required and **PASS** |
| Container count justified by nav ceiling? | **Removed** — count stands on job boundaries only |

---

## Rendered comparison (r2)

| Artifact | Verdict |
|---|---|
| `platform-shell-mobile.html` @ 390px | **PASS** (after amendment) |
| `position-cover-desktop.html` | **PASS** |
| `reports-utility-desktop.html` | **PASS** — Build/Dashboards/Inbox separation credible |
| `admin-utility-desktop.html` | **PASS** — platform vs Imports boundary clear |
| r1 `channel-cover-desktop.html` | **Superseded** by Position mockup |

---

## Capability decisions — not bundled in architecture PASS

| ID | Topic | EIF recommendation | Operator required |
|---|---|---|---|
| **D-0002** | Mapping queue UI (`/admin/mappings`) | **RESTORE** nav under Imports → worklists until steward engine proves parity; do not RETIRE UI in architecture package | **Yes** |
| **D-0003** | Control tower KPI vs Brief landing | Separate **landing job** (Brief) from **KPI analytical capability** (propose Reports → Dashboards); do not silently equate | **Yes** |

---

## Verdict

**AMENDED PASS** — Architecture package (Brief · Plan · Position · Settlement · Actions · Imports + Reports · Admin utilities) is fit for operator review **together with** explicit decisions D-0002 and D-0003.

**Do not accept D-0001 in r1 form** — superseded by amended D-0001 statement in proposal §9.

**Do not begin Phase A** until Warren accepts amended D-0001 and records D-0002/D-0003 choices.

---

## Accessibility (r2)

- `:focus-visible` present in `cip-base.css` (verified in source)
- Mobile drawer focus trap deferred to implementation — noted, not blocking approval-gate mockups
