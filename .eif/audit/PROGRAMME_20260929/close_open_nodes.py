"""Close N-0028, N-0044, N-0035, and N-0051 after the 2026-09-29 fixes.

N-0035 gets an implementation baseline and a stage->implement stamp so the
already-recorded GOV-008 passes have provenance. Quality fails are updated
only where this session measured a fix.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROG = REPO / ".eif/runtime/programme/program.py"
HERE = Path(__file__).resolve().parent


def invoke(args: list[str]) -> tuple[int, str]:
    r = subprocess.run(
        [sys.executable, "-B", str(PROG), "--project", str(REPO), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    return r.returncode, ((r.stdout or "") + (r.stderr or "")).strip()


def node(run: str, actor: str, nid: str) -> dict:
    code, text = invoke(["--run", run, "--actor", actor, "status", "--node", nid])
    if code:
        raise SystemExit(text[-1200:])
    return json.loads(text[text.rfind("\n{") + 1 :])


def event(run: str, actor: str, nid: str, name: str, payload: dict) -> tuple[int, str]:
    payload = dict(payload)
    payload["node"] = nid
    payload["expected_revision"] = int(node(run, actor, nid)["revision"])
    path = HERE / f"ev_{nid}_{name.replace('.', '_')}_{payload['expected_revision']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    rel = str(path.relative_to(REPO)).replace("\\", "/")
    return invoke(["--run", run, "--actor", actor, "event", name, "--payload-file", rel])


def must(run: str, actor: str, nid: str, name: str, payload: dict, lines: list[str]) -> bool:
    code, text = event(run, actor, nid, name, payload)
    if code:
        lines.append(f"{nid} {name} FAIL")
        lines.append(text[-800:])
        return False
    lines.append(f"{nid} {name} ok")
    return True


def lease(run: str, actor: str, nid: str, lines: list[str]) -> bool:
    return must(run, actor, nid, "node.lease.acquire", {"ttl_seconds": 7200}, lines)


def release(run: str, actor: str, nid: str) -> None:
    event(run, actor, nid, "node.lease.release", {})


def main() -> None:
    lines: list[str] = []

    run35 = "N0035_LEDGER_20260929"
    act35 = "ledger-n0035"
    if lease(run35, act35, "N-0035", lines):
        ok = must(
            run35,
            act35,
            "N-0035",
            "baseline.add",
            {
                "id": "BLN-N0035",
                "provenance": "implementation-observation",
                "tree_hash": "459f4c9",
                "path": "docs/memory/CURRENT.md",
                "observed_behavior": (
                    "Stage 2.2 a4fe957 sets AG_GRID_FONT_SIZE to 13px in packages/ui. "
                    "Stage 2.3 459f4c9 sets GRID_DENSITY comfortable to 40/40; compact stays 34/36."
                ),
                "latent_capabilities": [],
                "preservation": {},
            },
            lines,
        )
        # baseline.add is not a node event; the helper injected node. That may fail.
        # If it failed, the line above recorded it. Continue only when the id exists.
        if ok:
            ok = must(run35, act35, "N-0035", "node.baseline", {"baseline_ref": "BLN-N0035"}, lines)
        if ok:
            ok = must(
                run35,
                act35,
                "N-0035",
                "node.stage",
                {
                    "to": "implement",
                    "stage_note": (
                        "Provenance stamp for code that already landed: a4fe957 (13px) and "
                        "459f4c9 (40/40). GOV-008 GOV008_N0035_20260924 is a different run."
                    ),
                },
                lines,
            )
        if ok:
            ok = must(
                run35,
                act35,
                "N-0035",
                "node.stage",
                {
                    "to": "validate",
                    "stage_note": (
                        "Warren 2026-09-29 plus this session: close on the recorded GOV-008. "
                        "No type or density edit in this pass."
                    ),
                },
                lines,
            )
        if ok:
            ok = must(
                run35,
                act35,
                "N-0035",
                "node.accept",
                {"note": "Operator asked to close the N-0035 ledger on the recorded validation."},
                lines,
            )
        if ok:
            ok = must(run35, act35, "N-0035", "node.status", {"to": "complete"}, lines)
        release(run35, act35, "N-0035")

    run28 = "N0028_CONTENT_20260929"
    act28 = "content-n0028"
    if lease(run28, act28, "N-0028", lines):
        ok = must(
            run28,
            act28,
            "N-0028",
            "node.quality",
            {
                "dim": "content",
                "state": "pass",
                "evidence": {
                    "path": ".eif/audit/PROGRAMME_20260929/n0028/CONTENT.md",
                    "summary": (
                        "Steward card label is Work the steward queue. The explanation names "
                        "pipeline state grouped by failure type and the resolve workspace. "
                        "Href stays /admin/mappings. Vitest 8 passed."
                    ),
                },
            },
            lines,
        )
        if ok:
            ok = must(
                run28,
                act28,
                "N-0028",
                "node.stage_note",
                {
                    "stage_note": (
                        "AC2 content remediated 2026-09-29. Other quality dims stay the "
                        "2026-09-24 GOV-008 passes."
                    )
                },
                lines,
            )
        if ok:
            must(run28, act28, "N-0028", "node.status", {"to": "complete"}, lines)
        release(run28, act28, "N-0028")

    run44 = "N0044_A11Y_20260929"
    act44 = "a11y-n0044"
    if lease(run44, act44, "N-0044", lines):
        ok = must(
            run44,
            act44,
            "N-0044",
            "node.quality",
            {
                "dim": "a11y",
                "state": "pass",
                "evidence": {
                    "path": ".eif/audit/PROGRAMME_20260929/n0044/A11Y.md",
                    "summary": (
                        "Desk control labels use text.secondary. Composited on #22262e the "
                        "ratio is 5.26:1, above 4.5:1. The muted token that failed was 3.09:1."
                    ),
                },
            },
            lines,
        )
        if ok:
            ok = must(
                run44,
                act44,
                "N-0044",
                "node.stage_note",
                {
                    "stage_note": (
                        "a11y re-measured 2026-09-29 after the text.secondary remediation. "
                        "5.26:1 on the desk surface. Other gates stay the 2026-09-24 passes."
                    )
                },
                lines,
            )
        if ok:
            must(run44, act44, "N-0044", "node.status", {"to": "complete"}, lines)
        release(run44, act44, "N-0044")

    run51 = "N0051_VALIDATE_20260929"
    act51 = "validate-n0051"
    if lease(run51, act51, "N-0051", lines):
        ok = must(
            run51,
            act51,
            "N-0051",
            "node.quality",
            {
                "dim": "testing",
                "state": "pass",
                "evidence": {
                    "path": ".eif/audit/PROGRAMME_20260929/n0051/IMPL.md",
                    "summary": (
                        "test_merged_id_leftover_check.py 3 passed. Zero does not flag. "
                        "Non-zero is severity warning and does not change status. "
                        "A failed scan still fans out."
                    ),
                },
            },
            lines,
        )
        if ok:
            ok = must(
                run51,
                act51,
                "N-0051",
                "node.quality",
                {
                    "dim": "observability",
                    "state": "pass",
                    "evidence": {
                        "path": ".eif/audit/PROGRAMME_20260929/n0051/IMPL.md",
                        "summary": (
                            "Non-zero leftovers stamp staged_metadata.merged_id_leftover and a "
                            "warning row code merged_id_leftover. blocks_apply is false. "
                            "Scan failures are logged. cip_test measure returned total 0."
                        ),
                    },
                },
                lines,
            )
        if ok:
            ok = must(
                run51,
                act51,
                "N-0051",
                "node.stage",
                {
                    "to": "validate",
                    "stage_note": (
                        "Check is on the import-complete rail. Warning flag, not a block. "
                        "Proven read-only on cip_test (total 0) and by unit tests."
                    ),
                },
                lines,
            )
        if ok:
            must(run51, act51, "N-0051", "node.status", {"to": "complete"}, lines)
        release(run51, act51, "N-0051")

    (HERE / "result.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
