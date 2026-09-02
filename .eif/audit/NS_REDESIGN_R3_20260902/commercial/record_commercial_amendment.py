#!/usr/bin/env python3
"""Record the N-0013 r3.1 commercial amendment on the programme ledger.

Truthful state, not PASS:
- D-0008 (agent, proposed, supersedes D-0007): D-0007 + the commercial delta (Promotions & Funding owns the
  whole cpor_case lifecycle; Commercial inputs removed; Market & Listings evidence domain; four-state leaf
  vocabulary replaces data-gating; canonical <-> per-customer template profile; cross-domain links).
  D-0007 -> superseded (it was never accepted; history preserved).
- D-0009 (agent, proposed, scope N-0010): N-0010 disposition proposal — retire rejected framing, charter
  three post-N-0013 nodes after D-0008 acceptance. No nodes are chartered here (operator decision).
- N-0013 quality dims re-pointed to the amended evidence, still 'authored_unverified' (independence NONE).
- N-0010 stage note recording the reconciliation and the doc/code contradiction in its ACs. BL-0001 stays open.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PROG = REPO / ".eif/runtime/programme/program.py"
AUDIT = ".eif/audit/NS_REDESIGN_R3_20260902"
COM = f"{AUDIT}/commercial"
RUN = "NS_REDESIGN_R3_20260902"
N13 = "N-0013"
N10 = "N-0010"
INDEP = {
    "independence": "NONE — author-rendered, same session, same model (Fable 5.1); CONSULT used other model (claude opus CLI, separate process) for IA/template questions only",
    "reviewer_required": "separate GOV-008 session, other model where available",
}


def evt(actor: str, typ: str, payload: dict) -> None:
    r = subprocess.run(
        [sys.executable, str(PROG), "--run", RUN, "--actor", actor, "event", typ, "--payload", json.dumps(payload)],
        cwd=REPO, capture_output=True, text=True,
    )
    print(f"{typ} -> {(r.stdout or r.stderr).strip()[:200]}")
    if r.returncode:
        raise SystemExit(r.returncode)


def rev(nid: str) -> int:
    r = subprocess.run([sys.executable, str(PROG), "status", "--node", nid], cwd=REPO, capture_output=True, text=True)
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"no revision for {nid}")
    return int(m.group(1))


def main() -> None:
    evt("agent", "decision.add", {
        "id": "D-0008", "scope": N13, "origin": "agent", "status": "proposed", "supersedes": "D-0007",
        "statement": (
            "PROPOSED 2026-09-02 (r3.1): D-0007 as amended for the commercial capability. Δ1 Funding & Settlement → "
            "'Promotions & Funding' owning the whole cpor_case lifecycle (Promotion planner · Case book · Claims evidence · "
            "Payments · Plan templates · Terms & assumptions · Budget ledger). Δ2 'Commercial inputs' removed (its fixture "
            "tables promotion_plan/price_observations do not exist; promotion object is the same cpor_case row). Δ3 new "
            "evidence domain 'Market & Listings' (Monitored listings · Price history · Promotion activation · Feed proposals · "
            "Competitor mappings[partial] · Competitor prices[substrate] · Competitor listings[planned] · Listing quality/SEO"
            "[planned]). Δ4 binary data-gating withdrawn → four-state leaf vocabulary live/partial/substrate/planned; rail = "
            "live+partial (marked), directory = all four labelled. Δ5 export = canonical cpor_case model ↔ per-customer "
            "direction-aware template profile learned once via CanonicalColumnMappingPanel (supersedes "
            "CporHistoricalMappingProfile; retires RESELLER_HEADERS; round-trip diff = 0 is the certification). Δ6 cross-domain "
            "links: product panel → listings/competitors; case panel → LifecycleRail + activation. Δ7 proposed attention "
            "signals promo_not_activated / listing_price_change / competitor_mapping_pending shown as proposed, not live. "
            "Everything else in D-0007 unchanged; D-0002 remains deferred. "
            f"Evidence: {COM}/COMMERCIAL_DIRECTION.md, CAPABILITY_ACCOUNTING.md, CONSULT_SEED.md, CONSULT_RESPONSE.md, "
            "rendered-verification.md (27 captures @1280/@390); prototype apps/web/src/design-lab (FundingSurface, "
            "PromotionPlannerSurface, PlanTemplatesSurface, MarketSurface, labNav LeafStatus)."
        ),
    })
    evt("agent", "decision.status", {"id": "D-0007", "status": "superseded"})

    evt("agent", "decision.add", {
        "id": "D-0009", "scope": N10, "origin": "agent", "status": "proposed",
        "statement": (
            "PROPOSED 2026-09-02: N-0010 disposition. N-0010 ('NS-6 Actions container', blocked) is not the Promotion "
            "Planner and its acceptance criteria cite rejected design input (CIP_DESIGN_LANGUAGE.md FROZEN v1.1 / container "
            "Response). Recommend: retire that framing; after D-0008 acceptance charter (a) Promotions & Funding surface "
            "(B4 planner becomes the authoring surface of a draft case; from-scratch entry + entity pickers; retire /promotions "
            "scaffold notice), (b) Market & Listings surface (re-home /listing-capture + /competition under honest status; wire "
            "score_competitor_candidate behind 'Propose candidates'; promo_not_activated Brief signal; fix market.py readiness "
            "claim), (c) promotion-plan template profile (map once; same profile parses + renders; RESELLER_HEADERS removed; "
            "round-trip diff = 0); (d) keep 'ranked commercial actions' only as a slimmed re-chartered planned node if it "
            "retains product value. ACs must forbid hard-coded template law and fabricated uplift/elasticity/causality/impact/"
            f"confidence. Operator decision required; no nodes chartered by this run. Evidence: {COM}/COMMERCIAL_DIRECTION.md §5."
        ),
    })

    # N-0013: re-point quality dims to the amended evidence (still authored_unverified).
    r = rev(N13)
    evt("agent", "node.lease.acquire", {"node": N13, "expected_revision": r})
    dims = {
        "design_artifact_class": {"class": "react_prototype_in_repo", "paths": ["apps/web/src/design-lab/", "apps/web/src/app/(design-lab)/"], "note": "r3.1 adds PromotionPlannerSurface, PlanTemplatesSurface (mounts production CanonicalColumnMappingPanel), MarketSurface, LifecycleRail, CapabilityLedger, CapabilityStatus"},
        "design_divergence": {"paths": [f"{AUDIT}/CONCEPTS.md", f"{COM}/CONSULT_SEED.md", f"{COM}/CONSULT_RESPONSE.md"], "consult_model": "claude opus (CLI, separate process)", "note": "commercial IA: planner placement (3 options), evidence-domain placement (3), template architecture (3), status vocabulary, N-0010, naming"},
        "rendered_comparison": {"paths": [f"{AUDIT}/rendered-verification.md", f"{COM}/rendered-verification.md", f"{COM}/renders/manifest.json"], "viewports": ["1280x800", "390x844"], "captures": 34 + 27},
        "rendered": {"paths": [f"{AUDIT}/rendered-verification.md", f"{COM}/rendered-verification.md"], "viewports": ["1280x800", "390x844"]},
        "design_sameness_review": {"paths": [f"{AUDIT}/FAULT_FINDINGS.md", f"{COM}/COMMERCIAL_DIRECTION.md#2"], "note": "r3.1 delta table vs D-0007; binary data-gating rule withdrawn"},
        "content": {"paths": [f"{COM}/COMMERCIAL_DIRECTION.md#3", "apps/web/src/design-lab/shell/labNav.ts"], "note": "Promotions & Funding / Market & Listings nouns; four-state labels 'Partly built / Data only / Planned'"},
        "interaction_spec": {"paths": [f"{COM}/rendered-verification.md"], "note": "inline cell edit → waterfall recompute; evidence panel from non-editable cells; export dialog; template mapping with blocking error; approve/reject mapping; confirm/reject feed proposal"},
        "state_coverage": {"paths": [f"{COM}/rendered-verification.md"], "note": "partial / substrate / planned lenses rendered honestly (budget ledger, competitor prices, listing quality); needs-mapping template; draft plan blocked by template"},
        "accessibility": {"paths": ["apps/web/src/design-lab/primitives/LifecycleRail.tsx", "apps/web/src/design-lab/primitives/Panel.tsx"], "note": "LifecycleRail stages are buttons with aria-current; NOT audited by axe — UNVERIFIED"},
    }
    for dim, ev in dims.items():
        r = rev(N13)
        evt("agent", "node.quality", {
            "node": N13, "expected_revision": r, "dim": dim, "state": "authored_unverified",
            "evidence": {**ev, **INDEP, "dim": dim},
            "rationale": "r3.1 commercial amendment authored 2026-09-02; not PASS — independence none, awaiting separate GOV-008 and operator acceptance of D-0008.",
        })
    r = rev(N13)
    evt("agent", "node.verification", {
        "node": N13, "expected_revision": r, "kind": "rendered", "state": "authored_unverified",
        "evidence": {"paths": [f"{COM}/rendered-verification.md", f"{COM}/renders/"], **INDEP},
        "rationale": "27 additional captures (22 @1280, 5 @390), author-rendered; scrollWidth = viewport on all; 0 console errors; UNVERIFIED for independence.",
    })
    r = rev(N13)
    evt("agent", "node.stage_note", {
        "node": N13, "expected_revision": r,
        "note": (
            "r3.1 commercial amendment (2026-09-02): operator truths on Promotion Planner / listing intelligence / product "
            "competition applied. Source+roadmap discovery (CAPABILITY_ACCOUNTING), CONSULT (opus, separate process) on 6 "
            "questions, COMMERCIAL_DIRECTION (D-0007→D-0008 delta, IA, template architecture, N-0010 disposition, "
            "cross-domain links, remaining operator decisions). Design-lab: Funding & Settlement → Promotions & Funding with "
            "planner/templates/budgets lenses; Commercial inputs removed; Market & Listings added; four-state LeafStatus; "
            "27 renders. D-0007 superseded by D-0008 (proposed); D-0009 proposed for N-0010. Node remains blocked on operator "
            "acceptance; production implementation not started."
        ),
    })
    r = rev(N13)
    evt("agent", "node.lease.release", {"node": N13, "expected_revision": r})

    # N-0010: record the reconciliation (blocker BL-0001 stays open; no AC change without operator decision).
    r = rev(N10)
    evt("agent", "node.lease.acquire", {"node": N10, "expected_revision": r})
    r = rev(N10)
    evt("agent", "node.stage_note", {
        "node": N10, "expected_revision": r,
        "note": (
            "2026-09-02 reconciliation into post-N-0013 programme: this node is the 'Actions container', not the Promotion "
            "Planner (B4, partly shipped). Its acceptance criteria cite rejected design input (FROZEN v1.1 / container "
            "Response) — recorded as a doc/code contradiction. Disposition proposal D-0009 (retire framing; charter "
            "Promotions & Funding surface, Market & Listings surface, promotion-plan template profile after D-0008). "
            f"Evidence: {COM}/COMMERCIAL_DIRECTION.md §5, CAPABILITY_ACCOUNTING.md. Remains blocked on N-0013."
        ),
    })
    r = rev(N10)
    evt("agent", "node.lease.release", {"node": N10, "expected_revision": r})
    print("DONE record commercial amendment")


if __name__ == "__main__":
    main()
