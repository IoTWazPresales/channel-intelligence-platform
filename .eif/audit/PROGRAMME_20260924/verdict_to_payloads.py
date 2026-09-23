"""Turn a reviewer verdict.json into ordered ledger payload files.

Usage: python verdict_to_payloads.py <review_folder> <current_node_revision>
Writes <review_folder>/payloads/NN_<kind>.json, each with expected_revision in sequence.
The orchestrator runs each file with the reviewer's --run/--actor, one bare CLI call per file.
Only records what the reviewer wrote; never upgrades a state.
"""
import json
import pathlib
import sys

folder = pathlib.Path(sys.argv[1])
rev = int(sys.argv[2])
v = json.loads((folder / "verdict.json").read_text(encoding="utf-8"))
node = v["node"]
review_path = str((folder / "REVIEW.md").as_posix())
if ".eif/" in review_path:
    review_path = ".eif/" + review_path.split(".eif/", 1)[1]
out = folder / "payloads"
out.mkdir(exist_ok=True)
for old in out.glob("*.json"):
    old.unlink()
n = 0
for key, rec in v.get("dims", {}).items():
    kind, dim = key.split(".", 1)
    state = rec["state"]
    evidence = {"path": review_path, "verdict": v["verdict"], "summary": rec.get("summary", "")}
    if kind == "quality":
        p = {"node": node, "expected_revision": rev, "dim": dim, "state": state, "evidence": evidence}
        if rec.get("rationale"):
            p["rationale"] = rec["rationale"]
        et = "node.quality"
    else:
        p = {"node": node, "expected_revision": rev, "kind": dim, "state": state, "evidence": evidence}
        et = "node.verification"
    n += 1
    (out / f"{n:02d}_{et}.json").write_text(json.dumps(p, indent=1), encoding="utf-8")
    rev += 1
print(f"{n} payloads, next expected_revision {rev}")
