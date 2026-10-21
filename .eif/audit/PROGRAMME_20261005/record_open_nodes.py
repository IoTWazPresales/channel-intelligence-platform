"""Record operator decisions. Do not mark any node complete."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
HERE = Path(__file__).resolve().parent
RUN = "N0064_DECISION_20261005"
ACTOR = "gov-001"


def invoke(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def node(nid: str) -> dict:
    code, text = invoke(["--run", RUN, "--actor", ACTOR, "status", "--node", nid])
    if code:
        raise SystemExit(text[-1500:])
    return json.loads(text[text.rfind("\n{") + 1 :])


def event(name: str, payload: dict, nid: str | None) -> tuple[int, str]:
    payload = dict(payload)
    if nid:
        payload["node"] = nid
        payload["expected_revision"] = int(node(nid)["revision"])
    tag = nid or "programme"
    path = HERE / f"ev_{tag}_{name.replace('.', '_')}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    return invoke(["--run", RUN, "--actor", ACTOR, "event", name, "--payload-file", rel])


def must(name: str, payload: dict, nid: str | None, lines: list[str]) -> bool:
    code, text = event(name, payload, nid)
    if code:
        lines.append(f"{nid or '-'} {name} FAIL")
        lines.append(text[-900:])
        return False
    lines.append(f"{nid or '-'} {name} ok rev-after pending")
    return True


def main() -> None:
    lines: list[str] = []
    ok = must(
        "decision.add",
        {
            "scope": "N-0064",
            "origin": "operator",
            "status": "accepted",
            "statement": (
                "Warren 2026-10-05, overrides the old WAPE charter: group bias by product line; "
                "a late shipment scores in the quarter it shipped; show bias after 6 closed quarters; "
                "it may change a buy plan after 8; a quarter is closed one quarter after it ends. "
                "Buy-plan writers do not consume applies_to_buy_plan yet. "
                "Node acceptance stays pending until Warren accepts N-0064."
            ),
        },
        None,
        lines,
    )
    if not ok:
        print("\n".join(lines))
        return

    notes = {
        "N-0061": (
            "Not complete. Promo-plan evidence is proven in Python on seed case 309 (3 lines) "
            "and is not painted in the grid. The planner still says listings are not joined onto case lines. "
            "Competitor prices stay an honest empty while that fact table is empty. "
            "cpor_case_line.window_start is absent on cip (alembic 20260906_0022). "
            "Role cip is not the table owner and cannot ALTER. Do not Apply or Create draft until the column exists."
        ),
        "N-0066": (
            "Not complete. Buyer copy is on case book, lineup, pricing, competition, stock cover, supply, and overview. "
            "Widget captions still name tables. Admin overview still says import_job.status. "
            "Not every container."
        ),
        "N-0067": (
            "Not complete. Light theme is readable on case book, lineup, pricing, competition, stock cover, supply, and overview. "
            "Dark was restored. Not every production surface in both modes."
        ),
    }
    for nid, note in notes.items():
        if not must("node.lease.acquire", {"ttl_seconds": 1800}, nid, lines):
            break
        if not must("node.stage_note", {"note": note}, nid, lines):
            must("node.lease.release", {}, nid, lines)
            break
        if not must("node.lease.release", {}, nid, lines):
            break

    if not must("node.lease.acquire", {"ttl_seconds": 1800}, "N-0062", lines):
        print("\n".join(lines))
        return
    ok = must(
        "node.patch",
        {
            "acceptance_criteria": [
                "Arrived is line_state arrived with no proof-of-delivery date: its own bucket, leaves the open pipeline, counted once. A proof-of-delivery date stays landed. It is not a new stored column.",
                "Plan-unit PO coverage is a derived read, not a stored fact. A line is covered when its case has any commercial_lineup_case_po row; the whole line quantity counts. Shown by distributor.",
                "Nothing writes to cip; read-only SQL prints current_database() first",
                "Tests green on touched areas, tsc exit 0, eslint clean on changed files",
            ]
        },
        "N-0062",
        lines,
    )
    if ok:
        ok = must(
            "node.stage_note",
            {
                "note": (
                    "Acceptance text now matches the operator decision: derived Arrived bucket and derived plan-unit coverage. "
                    "Supply page already signed in. pytest 41 passed on supply coverage, inbound quarter, and plan-vs-executed (2026-10-05). "
                    "tsc and eslint not confirmed. Quality gates not stamped. Not complete."
                )
            },
            "N-0062",
            lines,
        )
    must("node.lease.release", {}, "N-0062", lines)

    if not must("node.lease.acquire", {"ttl_seconds": 1800}, "N-0064", lines):
        print("\n".join(lines))
        return
    ok = must(
        "node.patch",
        {
            "acceptance_criteria": [
                "Extends /plan-vs-executed. No new module.",
                "Bias is grouped by product line. A late shipment scores in the quarter it shipped and does not fill the plan quarter.",
                "Show bias after 6 closed quarters. It may change a buy plan after 8. A quarter is closed one quarter after it ends.",
                "Buy-plan writers do not consume applies_to_buy_plan yet.",
                "Open quarters and lines with pipeline remaining are excluded from accuracy and shown as pending.",
                "Malformed period labels and NULL product_line are counted and reported, never silently dropped.",
                "Landing rate uses proof of delivery or Arrived only, and is labelled distinctly from over-plan intake.",
                "Operator accepts this node.",
            ]
        },
        "N-0064",
        lines,
    )
    if ok:
        must(
            "node.stage_note",
            {
                "note": (
                    "Operator decision recorded 2026-10-05 and overrides the WAPE charter. "
                    "acceptance_state stays pending. Do not complete until Warren accepts."
                )
            },
            "N-0064",
            lines,
        )
    must("node.lease.release", {}, "N-0064", lines)
    (HERE / "result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
