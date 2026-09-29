"""Close shipped nodes on recorded validation. Warren 2026-09-29: no Opus; secondary validation is backlog.

Does not flip a fail to a pass. Does not complete proposed or blocked nodes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
PROG = REPO / ".eif/runtime/programme/program.py"
RUN = "CLOSE_SEQ_20260929"
ACTOR = "close-seq"
HERE = Path(__file__).resolve().parent
NOTE = (
    "Warren 2026-09-29: close on the validation already recorded. "
    "Opus consult is not this gate. A second validation when usage is back is BACKLOG-211. "
    "This run is the close, not an independent review."
)


def run(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def node(nid: str) -> dict:
    code, text = run(["--run", RUN, "--actor", ACTOR, "status", "--node", nid])
    if code:
        raise SystemExit(text[-1000:])
    return json.loads(text[text.rfind("\n{") + 1 :])


def event(nid: str, name: str, payload: dict) -> tuple[int, str]:
    payload = dict(payload)
    payload["node"] = nid
    payload["expected_revision"] = int(node(nid)["revision"])
    path = HERE / f"ev_{nid}_{name.replace('.', '_')}_{payload['expected_revision']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    return run(["--run", RUN, "--actor", ACTOR, "event", name, "--payload-file", rel])


def quality(nid: str, dim: str, summary: str, path: str) -> None:
    code, text = event(
        nid,
        "node.quality",
        {"dim": dim, "state": "pass", "evidence": {"path": path, "summary": summary}},
    )
    if code:
        raise SystemExit(f"{nid} quality {dim} failed\n{text[-800:]}")


def na(nid: str, dim: str, rationale: str) -> None:
    code, text = event(
        nid,
        "node.quality",
        {"dim": dim, "state": "na", "rationale": rationale, "evidence": {"path": ".eif/audit/PROGRAMME_20260924/n0035"}},
    )
    if code:
        raise SystemExit(f"{nid} na {dim} failed\n{text[-800:]}")


def lease(nid: str) -> None:
    code, text = event(nid, "node.lease.acquire", {"ttl_seconds": 7200})
    if code:
        raise SystemExit(f"{nid} LEASE FAIL\n{text[-800:]}")


def finish(nid: str, lines: list[str]) -> None:
    code, text = event(nid, "node.stage_note", {"stage_note": NOTE})
    if code:
        lines.append(f"{nid} NOTE FAIL {text[-400:]}")
    code, text = event(nid, "node.status", {"to": "complete"})
    if code:
        lines.append(f"{nid} COMPLETE REFUSED")
        lines.append(text[-700:])
        event(nid, "node.lease.release", {})
        return
    lines.append(f"{nid} COMPLETE")


def main() -> None:
    lines: list[str] = []

    # N-0035 retro charter. Content is na; give the rationale if it is still missing.
    lease("N-0035")
    n = node("N-0035")
    content = (n.get("quality") or {}).get("content") or {}
    if content.get("state") == "na" and not content.get("rationale"):
        na(
            "N-0035",
            "content",
            "Density and type token are visual measurements, not copy. Retro charter of a4fe957 and 459f4c9.",
        )
    finish("N-0035", lines)

    # N-0049 implemented and tested. Pending dims are the testing/observability pair.
    lease("N-0049")
    quality(
        "N-0049",
        "testing",
        "test_cpor_customer_soh_check.py 5 tests; broader pytest 274 passed on cip_test. prove_cip_ro read-only, current_database=cip.",
        ".eif/audit/PROGRAMME_20260924/n0049/IMPL.md",
    )
    quality(
        "N-0049",
        "observability",
        "Missing CST SOH returns status unavailable with a reason. It does not report zero stock. Flags zero_soh and no_soh_cost are on the cost-suggest payload.",
        ".eif/audit/PROGRAMME_20260924/n0049/IMPL.md",
    )
    finish("N-0049", lines)

    # N-0034 implemented in two passes; browser checks recorded 2026-09-29. Operator acceptance is this instruction.
    lease("N-0034")
    evidence = ".eif/audit/PROGRAMME_20260924/n0034/IMPL_PASS2.md"
    for dim, summary in (
        ("ux", "Column picker sits in the Scope bar on the Tier A hosts checked 2026-09-29. Picker was not rebuilt."),
        ("a11y", "Picker remains the existing FactColumnPicker checkbox dialog. No separate control was added."),
        ("rendered", "Browser on the rebuilt next start: Columns inside the Scope toolbar on forecasts, pricing, shipments, roadmap, cover, sell-out, channel-ops, execution, terms, listings."),
        ("content", "Labels stay Columns / Additional columns. Identity stays name-only. Codes stay their own columns."),
    ):
        quality("N-0034", dim, summary, evidence)
    code, text = event("N-0034", "node.accept", {"note": NOTE})
    if code:
        lines.append(f"N-0034 ACCEPT FAIL {text[-400:]}")
    else:
        lines.append("N-0034 ACCEPT")
    finish("N-0034", lines)

    (HERE / "result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
