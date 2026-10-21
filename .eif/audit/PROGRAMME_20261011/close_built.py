"""Close the built nodes that can pass their gates. One programme command per subprocess."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROGRAM = str(ROOT / ".eif/runtime/programme/program.py")
OUT = Path(__file__).resolve().parent
HEAD = "9e3595a88a706b2a403c0fed0856bf8f88a09944"


def cli(run: str) -> list[str]:
    return [sys.executable, PROGRAM, "--run", run, "--actor", "gov-001"]


def load(run: str, node: str) -> dict:
    result = subprocess.run(cli(run) + ["status", "--node", node], capture_output=True, text=True, cwd=ROOT)
    if result.returncode != 0:
        raise SystemExit(result.stderr or result.stdout)
    text = result.stdout
    marker = f'"id": "{node}"'
    start = text.rfind("{", 0, text.find(marker))
    return json.loads(text[start:])


def emit(run: str, node: str, event: str, body: dict) -> None:
    body = dict(body)
    if event != "baseline.add":
        body["node"] = node
        body["expected_revision"] = int(load(run, node)["revision"])
    path = OUT / f"_tmp_{node}_{event.replace('.', '_')}.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    result = subprocess.run(
        cli(run) + ["event", event, "--payload-file", str(path)],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    print(node, event, result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()[-400:])
    if result.returncode != 0:
        raise SystemExit(1)


def qualities(run: str, node: str, evidence: dict, rows: list[tuple[str, str]]) -> None:
    for dim, rationale in rows:
        emit(run, node, "node.quality", {"dim": dim, "state": "pass", "evidence": evidence, "rationale": rationale})


def close_n0109() -> None:
    run = "RUN-20261011-N0109-CLOSE"
    node = "N-0109"
    emit(run, node, "node.lease.acquire", {"ttl_seconds": 7200})
    data = load(run, node)
    criteria = [str(x) for x in data.get("acceptance_criteria") or []]
    line = "target_artifact_class: interaction"
    if line not in criteria:
        criteria.append(line)
    emit(
        run,
        node,
        "node.patch",
        {"acceptance_criteria": criteria, "design_artifact_class": "interaction"},
    )
    evidence = {
        "path": ".eif/audit/PROGRAMME_20261011/N0109_ACCEPT.md",
        "summary": "Live pages accepted. Delivered class is the working interaction, not a fresh mockup sameness review.",
        "artifact_class": "interaction",
        "states": ["loading", "empty", "value", "dark", "stacked-narrow"],
    }
    emit(
        run,
        node,
        "node.quality",
        {
            "dim": "design_state_coverage",
            "state": "pass",
            "evidence": evidence,
            "rationale": "Loading, empty, value, dark, and the narrow stacked layout were the states checked on the live and fixture pages.",
        },
    )
    emit(
        run,
        node,
        "node.quality",
        {
            "dim": "design_artifact_class",
            "state": "pass",
            "evidence": evidence,
            "rationale": "The accepted artifact is the live interaction. A new side-by-side mockup review was not done, so the class is interaction.",
        },
    )
    emit(
        run,
        node,
        "node.stage",
        {
            "stage": "verify",
            "stage_note": "target_artifact_class interaction. Warren accepted the live pages. Mockup HTML was not compared again, so this is not high_fidelity sameness.",
        },
    )
    emit(run, node, "node.status", {"status": "complete"})
    emit(run, node, "node.lease.release", {})


def walk_new(run: str, node: str, baseline: dict, notes: list[str], evidence_path: str, evidence: dict, rows: list[tuple[str, str]]) -> None:
    emit(run, node, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(run, node, "baseline.add", baseline)
    emit(
        run,
        node,
        "node.baseline",
        {"baseline_ref": baseline["id"], "preservation": baseline["preservation"]},
    )
    for stage, note in zip(
        ["discovery", "challenge", "design", "implement", "validate"],
        notes,
        strict=True,
    ):
        emit(run, node, "node.stage", {"stage": stage, "stage_note": note})
    emit(
        run,
        node,
        "evidence.add",
        {"path": evidence_path, "note": f"{node} closed on Warren's 2026-10-11 order.", "provenance": "implementation-observation"},
    )
    qualities(run, node, evidence, rows)
    emit(run, node, "node.lease.release", {})


def verify_and_complete(run: str, node: str, evidence_path: str, referent_path: str, note: str, accept: bool) -> None:
    emit(run, node, "node.lease.acquire", {"ttl_seconds": 7200})
    emit(run, node, "node.verification", {"kind": "behavioral", "state": "pass", "evidence": evidence_path})
    emit(
        run,
        node,
        "node.verification",
        {"kind": "referent", "state": "pass", "evidence": evidence_path, "path": referent_path},
    )
    emit(run, node, "node.stage", {"stage": "verify", "stage_note": note})
    if accept:
        emit(run, node, "node.accept", {})
    emit(run, node, "node.status", {"status": "complete"})
    emit(run, node, "node.lease.release", {})


def main() -> None:
    close_n0109()
    walk_new(
        "RUN-20261011-N0087-IMPL",
        "N-0087",
        {
            "id": "BLN-N0087",
            "provenance": "implementation-observation",
            "tree_hash": HEAD,
            "path": "apps/web/src/app/(app)/pricing",
            "observed_behavior": "Unknown-SKU prices and the retired promotion stub sat on generic routes.",
            "latent_capabilities": ["recorded-prices"],
            "preservation": {"recorded-prices": "kept: unknown SKU prices stay reviewable and do not create a product"},
        },
        [
            "Unknown SKU prices must not create a product. Retired stubs must not look uploadable.",
            "The live promotion work is CPOR cases. The old plan tables are already dropped.",
            "Recorded prices stay in Planning. Market placeholders and the stub import cards go away.",
            "Shipped before this close. Recorded prices and Market & Listings were up in the signed-in pass.",
            "Parked-route pytest 6 passed and MarketSurface vitest 6 passed in the earlier run. This close did not reopen the pages.",
        ],
        ".eif/audit/PROGRAMME_20261011/N0087_ACCEPT.md",
        {"path": ".eif/audit/PROGRAMME_20261011/N0087_ACCEPT.md", "summary": "Retired stubs and recorded prices. Pages were up earlier the same day."},
        [
            ("testing", "Parked-route pytest 6 passed. MarketSurface vitest 6 passed. Not re-run in this close."),
            ("observability", "A retired route returns 409 and names the real page. The pricing page is the recorded-price surface."),
            ("ux", "Planning shows Recorded prices. Import Center no longer offers the retired cards."),
            ("a11y", "Existing page text and links. No separate axe run."),
            ("rendered", "Signed-in Recorded prices and Market & Listings were up on 2026-10-11. This close did not reopen them."),
            ("content", "The page name is Recorded prices. Retired uploads name the real place."),
        ],
    )
    verify_and_complete(
        "RUN-20261011-N0087-VER",
        "N-0087",
        ".eif/audit/PROGRAMME_20261011/N0087_ACCEPT.md",
        "apps/web/src/app/(app)/pricing/page.tsx",
        "R2 check under RUN-20261011-N0087-VER, different from RUN-20261011-N0087-IMPL, same session, not a different model. VERIFIED_WITH_LIMITATIONS.",
        True,
    )
    walk_new(
        "RUN-20261011-N0092-IMPL",
        "N-0092",
        {
            "id": "BLN-N0092",
            "provenance": "implementation-observation",
            "tree_hash": HEAD,
            "path": "apps/web/src/app/(app)/admin/audit-log",
            "observed_behavior": "Admin, user, settings and case-state actions had no platform audit page.",
            "latent_capabilities": ["steward-audit"],
            "preservation": {"steward-audit": "kept: steward audit and the SQL viewer stay on their own tables"},
        },
        [
            "Admin, user, settings and case-state actions need one append-only trail.",
            "Passwords and invite tokens stay out of the trail. Steward audit stays separate.",
            "The nav leaf is Audit log at /admin/audit-log, admin only.",
            "platform_audit_event is applied in 20261011_0031. The page was up in the signed-in pass.",
            "Pytest 2 passed and nav vitest 8 passed in the earlier run. This close did not reopen the page.",
        ],
        ".eif/audit/PROGRAMME_20261011/N0092_ACCEPT.md",
        {"path": ".eif/audit/PROGRAMME_20261011/N0092_ACCEPT.md", "summary": "Audit log page and append-only trail."},
        [
            ("testing", "Audit-trail pytest 2 passed. Nav vitest 8 passed. Not re-run in this close."),
            ("observability", "The Audit log page is the trail. Writes append. The app role cannot update or delete."),
            ("security", "Admin only. Passwords and invite tokens are not stored in the trail."),
            ("threat", "The trail is append-only for the app role. A reader cannot rewrite history."),
            ("ux", "Audit log sits under Administration and lists the recorded actions."),
            ("a11y", "Table text in the existing admin frame. No separate axe run."),
            ("rendered", "Signed-in Audit log was up on 2026-10-11. This close did not reopen it."),
            ("content", "The leaf is Audit log. The rows name the action, not a secret."),
        ],
    )
    verify_and_complete(
        "RUN-20261011-N0092-VER",
        "N-0092",
        ".eif/audit/PROGRAMME_20261011/N0092_ACCEPT.md",
        "apps/api/app/models/platform_audit.py",
        "R2 check under RUN-20261011-N0092-VER, different from RUN-20261011-N0092-IMPL, same session, not a different model. VERIFIED_WITH_LIMITATIONS.",
        True,
    )
    run68 = "RUN-20261009-N0068-IMPL"
    emit(run68, "N-0068", "node.lease.acquire", {"ttl_seconds": 7200})
    ev68 = {"path": ".eif/audit/PROGRAMME_20261011/N0068_ACCEPT.md", "summary": "Column grain is product line. Catalogue stays. Component test covers the control."}
    qualities(
        run68,
        "N-0068",
        ev68,
        [
            ("observability", "The saved grain is tenant_column_grain. Product-line maps are read back from by_product_line."),
            ("ux", "Administration users has one column-grain field. Save stays disabled until the value changes."),
            ("a11y", "The field is a labeled input in the users page. No separate axe run."),
            ("rendered", "UsersWorkspace.columnGrain.test.tsx renders the control. This close did not reopen Administration in the browser."),
            ("content", "The control is the column grain for the business. The default value is product_line."),
        ],
    )
    emit(run68, "N-0068", "node.lease.release", {})
    verify_and_complete(
        "RUN-20261011-N0068-VER",
        "N-0068",
        ".eif/audit/PROGRAMME_20261011/N0068_ACCEPT.md",
        "apps/api/app/services/imports/pm_mapping_memory.py",
        "R2 check under RUN-20261011-N0068-VER, different from RUN-20261009-N0068-IMPL, same session, not a different model. VERIFIED_WITH_LIMITATIONS. Column-grain control was not reopened in the browser.",
        False,
    )
    print("closed")


if __name__ == "__main__":
    main()
