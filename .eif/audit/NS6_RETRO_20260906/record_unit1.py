"""Append-only UNIT 1: out-of-order work. Does not stamp implementation_run."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "NS6_RETRO_20260906"
ACTOR = "gov-001"


def run_prog(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROG), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def _integrity_issues(issues: list[str]) -> list[str]:
    expected = (
        "IMPLEMENTATION_PROVENANCE_REQUIRED",
        "recorded complete but gates invalid",
    )
    return [i for i in issues if not any(tok in i for tok in expected)]


def verify() -> dict:
    r = run_prog(["verify"])
    raw = (r.stdout or r.stderr).strip()
    print(raw)
    data = json.loads(r.stdout)
    bad = _integrity_issues(data.get("issues") or [])
    if bad:
        raise SystemExit(f"verify integrity failed: {bad}")
    return data


def frontier() -> str:
    r = run_prog(["frontier"])
    print("FRONTIER:", (r.stdout or "").strip() or "-")
    if r.returncode:
        raise SystemExit(r.returncode)
    return (r.stdout or "").strip()


def evt(typ: str, payload: dict) -> str:
    r = run_prog(
        ["--run", RUN, "--actor", ACTOR, "event", typ, "--payload", json.dumps(payload)]
    )
    out = (r.stdout or r.stderr).strip()
    print(f"{typ} -> {out}")
    if r.returncode:
        print(r.stderr)
        raise SystemExit(r.returncode)
    return out


def node_rev(nid: str) -> int:
    r = run_prog(["status", "--node", nid])
    if r.returncode:
        print(r.stdout or r.stderr)
        raise SystemExit(r.returncode)
    m = re.search(r'"revision":\s*(\d+)', r.stdout or "")
    if not m:
        raise SystemExit(f"no revision for {nid}")
    return int(m.group(1))


def add_node(**kwargs) -> None:
    args = ["--run", RUN, "--actor", ACTOR, "add-node"]
    mapping = {
        "id": "--id",
        "title": "--title",
        "klass": "--class",
        "parent": "--parent",
        "origin": "--origin",
        "status": "--status",
        "facets": "--facets",
        "risk": "--risk",
        "criteria": "--criteria",
    }
    for key, flag in mapping.items():
        if key in kwargs and kwargs[key] is not None:
            args.extend([flag, str(kwargs[key])])
    if kwargs.get("touches_existing"):
        args.append("--touches-existing")
    r = run_prog(args)
    print("add-node", kwargs.get("id"), "->", (r.stdout or r.stderr).strip())
    if r.returncode:
        raise SystemExit(r.returncode)


def main() -> None:
    print("=== BEFORE ===")
    before = frontier()
    verify()

    evidence = [
        {
            "id": "EV-GOV008-REVIEW",
            "provenance": "implementation-observation",
            "path": ".eif/audit/NS6_GOV008_R3_20260903/independent-rendered-review.md",
            "note": (
                "GOV-008 review plus 2026-09-04 addendum. Records synthetic "
                "implementation_run NS6_N0013_IMPL_BOUNDARY_20260903 and CONSULT "
                "cli session evidence (claude-opus-4-8, sdk-cli, 2026-09-02T16:49:43Z "
                "and 2026-09-02T21:34:04Z). Session logs live outside the repo."
            ),
        },
        {
            "id": "EV-N0013-SYNTHETIC-SCRIPT",
            "provenance": "implementation-observation",
            "path": ".eif/audit/NS6_GOV008_R3_20260903/complete_n0013.py",
            "note": "Script that stamped synthetic implement so independence gates could evaluate.",
        },
        {
            "id": "EV-NS1B-92F8EDB",
            "provenance": "implementation-observation",
            "tree_hash": "92f8edb21cd907e59bb406eecac674e486b3708b",
            "note": "cpor: NS-1b FX mode columns, blocked-settle enforcement, and case declare UI",
        },
        {
            "id": "EV-NS1B-736B089",
            "provenance": "implementation-observation",
            "tree_hash": "736b08977958c0af8e94c23559e292a2d80d2c20",
            "note": "feat(cpor): declare booked FX mode and find cases by entity",
        },
        {
            "id": "EV-PF-4FD05C4",
            "provenance": "implementation-observation",
            "tree_hash": "4fd05c4e223cf09ded897365cca3a8521850b3c2",
            "note": "promotions: migrate funding lab onto production cpor_case paths",
        },
        {
            "id": "EV-PF-5E3EB5A",
            "provenance": "implementation-observation",
            "tree_hash": "5e3eb5ad9dfebba0590d61738cfbb20feb05fd2b",
            "note": "feat(web): close out Promotions & Funding against the design lab",
        },
        {
            "id": "EV-PF-8C6AEF8",
            "provenance": "implementation-observation",
            "tree_hash": "8c6aef8cf8cbcdee5c0863598c2ce2f66df6121a",
            "note": "feat(web): migrate lab desktop dimensions into shared funding chrome",
        },
        {
            "id": "EV-PF-96E35B7",
            "provenance": "implementation-observation",
            "tree_hash": "96e35b72d372691fe0d12eb59e45b0ef168a7e85",
            "note": "promotions: restore domain chrome, number scope, remaining funding lenses",
        },
        {
            "id": "EV-MKT-A853A4E",
            "provenance": "implementation-observation",
            "tree_hash": "a853a4e5dd5b3a11061c58ced8e2ab82d642edd7",
            "note": "market: mount Market & Listings chrome on listing-capture and competition",
        },
        {
            "id": "EV-MKT-82013B3",
            "provenance": "implementation-observation",
            "tree_hash": "82013b38c44af4982699482c64e4a96641c3c758",
            "note": "market: land remaining Market MIGRATE (proposals Source cell, reject, snackbar)",
        },
        {
            "id": "EV-STK-EB37AD5",
            "provenance": "implementation-observation",
            "tree_hash": "eb37ad530f91991b2ee62688b49573a33581268e",
            "note": "stock: mount lab DomainHeader and five Stock lenses on production routes",
        },
        {
            "id": "EV-STK-31712DF",
            "provenance": "implementation-observation",
            "tree_hash": "31712dff3dfb1c050d3aa216310e023fa533887c",
            "note": "stock: migrate Cover lens to lab headlines and pair grid",
        },
        {
            "id": "EV-STK-21A11D1",
            "provenance": "implementation-observation",
            "tree_hash": "21a11d13000e098317f658d9e0c1583645068731",
            "note": "stock: migrate Movement lens to lab headlines and relocate Channel Ops",
        },
    ]
    for ev in evidence:
        evt("evidence.add", ev)
        verify()

    print("=== a. N-0013 independence.disclaim ===")
    evt(
        "node.independence.disclaim",
        {
            "node": "N-0013",
            "expected_revision": node_rev("N-0013"),
            "reason": (
                "Independence was constructed, not earned. Synthetic implementation_run "
                "NS6_N0013_IMPL_BOUNDARY_20260903 stays in the log so that GOV-008 pass "
                "provenance could evaluate a discovery node whose implement stage was not "
                "the product change. This disclaimer records that construction; it does "
                "not rewrite seq 274–294."
            ),
            "evidence_ids": ["EV-GOV008-REVIEW", "EV-N0013-SYNTHETIC-SCRIPT"],
        },
    )
    verify()
    frontier()

    print("=== b. caveat.resolve seq 287 consult_model_logged ===")
    evt(
        "caveat.resolve",
        {
            "node": "N-0013",
            "expected_revision": node_rev("N-0013"),
            "prior_seq": 287,
            "key": "consult_model_logged",
            "resolution": (
                "Seq 287 node.quality/design_divergence remains UNVERIFIED in the "
                "append-only log. Later GOV-008 addendum (2026-09-04) resolves the "
                "consult model from Claude Code CLI session logs: model claude-opus-4-8, "
                "entrypoint sdk-cli, 2026-09-02T16:49:43Z (IA) and 2026-09-02T21:34:04Z "
                "(commercial). Logs are outside the repo and are not durable."
            ),
            "evidence_ids": ["EV-GOV008-REVIEW"],
        },
    )
    verify()
    frontier()

    print("=== c. N-0006 retroactive_complete ===")
    evt(
        "node.retroactive_complete",
        {
            "node": "N-0006",
            "expected_revision": node_rev("N-0006"),
            "independence_unrecoverable": True,
            "note": (
                "NS-1b FX mode / fx_settle_allowed shipped in product commits 92f8edb "
                "and 736b089 ahead of this node. This recording run is not the "
                "implementer and does not stamp implementation_run. R3 referent/rendered "
                "independence cannot be satisfied after the fact."
            ),
            "evidence_ids": ["EV-NS1B-92F8EDB", "EV-NS1B-736B089"],
        },
    )
    verify()
    frontier()

    print("=== d. three migrated containers ===")
    containers = [
        {
            "id": "N-0014",
            "title": "Promotions & Funding production migration from design-lab",
            "criteria": (
                "Lab Promotions & Funding desktop experience on production cpor_case "
                "paths; Partly built / Planned markers retained; no invented design language"
            ),
            "charter_note": "Shipped on feat/ns-2-brief-nav-collapse ahead of a covering node (BACKLOG-171 instance 4).",
            "complete_note": "Close-out commit 5e3eb5a against the design lab. Independence unrecoverable: no GOV-008 of this node.",
            "evidence_ids": ["EV-PF-4FD05C4", "EV-PF-5E3EB5A", "EV-PF-8C6AEF8", "EV-PF-96E35B7"],
            "complete": True,
        },
        {
            "id": "N-0015",
            "title": "Market & Listings production migration from design-lab",
            "criteria": (
                "Lab Market & Listings chrome on /listing-capture and /competition; "
                "planned leaves stay Planned; leftover /market stub is not this container"
            ),
            "charter_note": "Shipped on feat/ns-2-brief-nav-collapse ahead of a covering node (BACKLOG-171 instance 4).",
            "complete_note": "Chrome + remaining MIGRATE landed (a853a4e, 82013b3). Independence unrecoverable: no GOV-008 of this node. /market stub deferred separately.",
            "evidence_ids": ["EV-MKT-A853A4E", "EV-MKT-82013B3"],
            "complete": True,
        },
        {
            "id": "N-0016",
            "title": "Stock & Sell-through Cover and Movement lenses from design-lab",
            "criteria": (
                "Lab Cover and Movement structure on production /stock with numbers from "
                "cip; Execution vs plan is a later node; relocate rather than delete Channel Ops"
            ),
            "charter_note": "Cover 31712df and Movement 21a11d1 shipped ahead of a covering node (BACKLOG-171 instance 4).",
            "complete_note": "Cover and Movement migrated. Execution vs plan is not in this node. Independence unrecoverable: no GOV-008 of this node.",
            "evidence_ids": ["EV-STK-EB37AD5", "EV-STK-31712DF", "EV-STK-21A11D1"],
            "complete": True,
        },
    ]
    for c in containers:
        add_node(
            id=c["id"],
            title=c["title"],
            klass="redesign",
            origin="decomposition",
            facets="ui",
            risk="R2",
            touches_existing=True,
            criteria=c["criteria"],
        )
        verify()
        frontier()
        evt(
            "node.retroactive_charter",
            {
                "node": c["id"],
                "expected_revision": node_rev(c["id"]),
                "note": c["charter_note"],
                "evidence_ids": c["evidence_ids"],
            },
        )
        verify()
        frontier()
        if c["complete"]:
            evt(
                "node.retroactive_complete",
                {
                    "node": c["id"],
                    "expected_revision": node_rev(c["id"]),
                    "independence_unrecoverable": True,
                    "note": c["complete_note"],
                    "evidence_ids": c["evidence_ids"],
                },
            )
            verify()
            frontier()

    print("=== finding.defer leftover /market stub ===")
    evt(
        "finding.defer",
        {
            "code": "DOES_NOT_FIT",
            "node": "N-0015",
            "note": (
                "apps/web/src/app/(app)/market/page.tsx remains a static JSON stub. "
                "Market & Listings production container is /listing-capture and "
                "/competition (MarketSurface), not /market. Do not treat the stub as "
                "the container; do not delete it in this recording."
            ),
        },
    )
    verify()

    print("=== AFTER ===")
    after = frontier()
    print("BEFORE_FRONTIER", before)
    print("AFTER_FRONTIER", after or "-")


def resume_after_disclaim() -> None:
    print("=== RESUME after disclaim rev 309 ===")
    verify()
    frontier()

    print("=== b. caveat.resolve seq 287 consult_model_logged ===")
    evt(
        "caveat.resolve",
        {
            "node": "N-0013",
            "expected_revision": node_rev("N-0013"),
            "prior_seq": 287,
            "key": "consult_model_logged",
            "resolution": (
                "Seq 287 node.quality/design_divergence remains UNVERIFIED in the "
                "append-only log. Later GOV-008 addendum (2026-09-04) resolves the "
                "consult model from Claude Code CLI session logs: model claude-opus-4-8, "
                "entrypoint sdk-cli, 2026-09-02T16:49:43Z (IA) and 2026-09-02T21:34:04Z "
                "(commercial). Logs are outside the repo and are not durable."
            ),
            "evidence_ids": ["EV-GOV008-REVIEW"],
        },
    )
    verify()
    frontier()

    print("=== c. N-0006 retroactive_complete ===")
    evt(
        "node.retroactive_complete",
        {
            "node": "N-0006",
            "expected_revision": node_rev("N-0006"),
            "independence_unrecoverable": True,
            "note": (
                "NS-1b FX mode / fx_settle_allowed shipped in product commits 92f8edb "
                "and 736b089 ahead of this node. This recording run is not the "
                "implementer and does not stamp implementation_run. R3 referent/rendered "
                "independence cannot be satisfied after the fact."
            ),
            "evidence_ids": ["EV-NS1B-92F8EDB", "EV-NS1B-736B089"],
        },
    )
    verify()
    frontier()

    print("=== d. three migrated containers ===")
    containers = [
        {
            "id": "N-0014",
            "title": "Promotions & Funding production migration from design-lab",
            "criteria": (
                "Lab Promotions & Funding desktop experience on production cpor_case "
                "paths; Partly built / Planned markers retained; no invented design language"
            ),
            "charter_note": "Shipped on feat/ns-2-brief-nav-collapse ahead of a covering node (BACKLOG-171 instance 4).",
            "complete_note": "Close-out commit 5e3eb5a against the design lab. Independence unrecoverable: no GOV-008 of this node.",
            "evidence_ids": ["EV-PF-4FD05C4", "EV-PF-5E3EB5A", "EV-PF-8C6AEF8", "EV-PF-96E35B7"],
            "complete": True,
        },
        {
            "id": "N-0015",
            "title": "Market & Listings production migration from design-lab",
            "criteria": (
                "Lab Market & Listings chrome on /listing-capture and /competition; "
                "planned leaves stay Planned; leftover /market stub is not this container"
            ),
            "charter_note": "Shipped on feat/ns-2-brief-nav-collapse ahead of a covering node (BACKLOG-171 instance 4).",
            "complete_note": "Chrome + remaining MIGRATE landed (a853a4e, 82013b3). Independence unrecoverable: no GOV-008 of this node. /market stub deferred separately.",
            "evidence_ids": ["EV-MKT-A853A4E", "EV-MKT-82013B3"],
            "complete": True,
        },
        {
            "id": "N-0016",
            "title": "Stock & Sell-through Cover and Movement lenses from design-lab",
            "criteria": (
                "Lab Cover and Movement structure on production /stock with numbers from "
                "cip; Execution vs plan is a later node; relocate rather than delete Channel Ops"
            ),
            "charter_note": "Cover 31712df and Movement 21a11d1 shipped ahead of a covering node (BACKLOG-171 instance 4).",
            "complete_note": "Cover and Movement migrated. Execution vs plan is not in this node. Independence unrecoverable: no GOV-008 of this node.",
            "evidence_ids": ["EV-STK-EB37AD5", "EV-STK-31712DF", "EV-STK-21A11D1"],
            "complete": True,
        },
    ]
    for c in containers:
        add_node(
            id=c["id"],
            title=c["title"],
            klass="redesign",
            origin="decomposition",
            facets="ui",
            risk="R2",
            touches_existing=True,
            criteria=c["criteria"],
        )
        verify()
        frontier()
        evt(
            "node.retroactive_charter",
            {
                "node": c["id"],
                "expected_revision": node_rev(c["id"]),
                "note": c["charter_note"],
                "evidence_ids": c["evidence_ids"],
            },
        )
        verify()
        frontier()
        if c["complete"]:
            evt(
                "node.retroactive_complete",
                {
                    "node": c["id"],
                    "expected_revision": node_rev(c["id"]),
                    "independence_unrecoverable": True,
                    "note": c["complete_note"],
                    "evidence_ids": c["evidence_ids"],
                },
            )
            verify()
            frontier()

    print("=== finding.defer leftover /market stub ===")
    evt(
        "finding.defer",
        {
            "code": "DOES_NOT_FIT",
            "node": "N-0015",
            "note": (
                "apps/web/src/app/(app)/market/page.tsx remains a static JSON stub. "
                "Market & Listings production container is /listing-capture and "
                "/competition (MarketSurface), not /market. Do not treat the stub as "
                "the container; do not delete it in this recording."
            ),
        },
    )
    verify()
    print("=== AFTER ===")
    frontier()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "resume":
        resume_after_disclaim()
    else:
        main()
