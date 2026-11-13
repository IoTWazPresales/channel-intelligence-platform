#!/usr/bin/env python3
"""BACKLOG-225 decision B: LF-stable EIF digests + Linux /workspace identity anchor.

Does not connect to or mutate database ``cip``. Mutates EIF control plane only.
Run from an operator shell when the agent is blocked on lean B4:

  python apps/api/scripts/ops/apply_backlog_225_eif_decision_b.py --project <repo-root>

Default ``--project`` is the git toplevel containing this file.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

EIF_FRAMEWORK = Path(r"C:\AI\engineering-intelligence-framework")
CMD_DISPATCH = ':; exec /bin/sh "$(dirname -- "$0")/eif_guard.sh" "$@"; exit 126 #\n'
GITATTR_SNIPPET = """
# BACKLOG-225 decision B: digest-stable on Linux cloud checkouts (LF everywhere).
.eif/PROJECT_MANIFEST.md text eol=lf
.eif/ENVIRONMENT_POLICY.md text eol=lf
"""
RENORMALIZE = [
    ".gitattributes",
    ".eif/PROJECT_MANIFEST.md",
    ".eif/ENVIRONMENT_POLICY.md",
    ".cursor/hooks/eif_guard.py",
    ".cursor/hooks/eif_session.py",
]


def _run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd), file=sys.stderr)
    subprocess.check_call(cmd, cwd=cwd)


def _ensure_gitattributes(project: Path) -> None:
    path = project / ".gitattributes"
    text = path.read_text(encoding="utf-8")
    if "BACKLOG-225 decision B" not in text:
        if not text.endswith("\n"):
            text += "\n"
        path.write_text(text + GITATTR_SNIPPET.lstrip("\n"), encoding="utf-8", newline="\n")


def _ensure_manifest_workspace(project: Path) -> None:
    path = project / ".eif" / "PROJECT_MANIFEST.md"
    text = path.read_text(encoding="utf-8")
    if "path: /workspace" in text:
        return
    text = text.replace("  additional_repositories: []", "  additional_repositories:\n  - path: /workspace")
    if "path: /workspace" not in text:
        raise SystemExit("could not patch PROJECT_MANIFEST.md additional_repositories")
    path.write_text(text, encoding="utf-8", newline="\n")


def _ensure_workspace_junction(project: Path) -> None:
    link = Path(r"C:\workspace")
    if link.exists():
        return
    try:
        _run(["cmd", "/c", "mklink", "/J", str(link), str(project.resolve())], cwd=project)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "create junction C:\\workspace -> project root (mklink /J) failed; "
            "run an elevated shell once, then re-run this script"
        ) from exc


def _renormalize(project: Path) -> None:
    _run(["git", "add", "--renormalize", *RENORMALIZE], cwd=project)


def _upgrade(project: Path) -> None:
    installer = EIF_FRAMEWORK / "tools" / "install_project.py"
    if not installer.is_file():
        raise SystemExit(f"missing EIF framework checkout: {installer}")
    _run([sys.executable, str(installer), "upgrade", str(project)], cwd=EIF_FRAMEWORK)


def _ensure_cmd_dispatch(project: Path) -> None:
    cmd = project / ".cursor" / "hooks" / "eif_guard.cmd"
    text = cmd.read_text(encoding="utf-8")
    if CMD_DISPATCH.strip() in text.splitlines()[0:2]:
        return
    if text.startswith("@echo off"):
        text = CMD_DISPATCH + text
    elif not text.startswith(":; exec"):
        text = CMD_DISPATCH + text
    cmd.write_text(text, encoding="utf-8", newline="\r\n")
    manifest_path = project / ".cursor" / "eif-runtime-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    from hashlib import sha256

    digest = sha256(cmd.read_bytes()).hexdigest()
    manifest.setdefault("files", {})[".cursor/hooks/eif_guard.cmd"] = digest
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _patch_linux_anchor(project: Path) -> None:
    policy_path = project / ".cursor" / "eif-runtime-policy.json"
    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    ident = policy.setdefault("identity", {})
    anchors = [
        a
        for a in (ident.get("repository_anchors") or [])
        if ".worktrees/" not in (a.get("allowed_root") or "").replace("\\", "/")
    ]
    if not anchors:
        raise SystemExit("compiled policy has no repository_anchors")
    primary = anchors[0]
    root_commit = primary.get("root_commit") or ident.get("root_commit")
    remotes = primary.get("expected_remotes") or ident.get("expected_remotes") or []
    linux = {
        "allowed_root": "/workspace",
        "expected_vcs_root": "/workspace",
        "root_commit": root_commit,
        "expected_remotes": remotes,
    }
    if not any(a.get("expected_vcs_root") == "/workspace" for a in anchors):
        anchors.append(linux)
    ident["repository_anchors"] = anchors
    roots = [
        r
        for r in (policy.get("allowed_roots") or [])
        if ".worktrees/" not in r.replace("\\", "/")
    ]
    if "/workspace" not in roots:
        roots.append("/workspace")
    policy["allowed_roots"] = roots
    policy.setdefault(
        "enforcement",
        {
            "profile": "lean",
            "protected_databases": ["cip"],
            "protected_branches": ["main"],
            "protected_database_flags": ["ALLOW_TESTS_ON_DEV_DB"],
        },
    )
    policy_path.write_text(json.dumps(policy, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--project",
        type=Path,
        default=None,
        help="EIF project root (default: git toplevel for this script)",
    )
    ap.add_argument("--skip-junction", action="store_true", help="skip C:\\workspace mklink (compile may fail)")
    ap.add_argument("--skip-upgrade", action="store_true", help="patch only; no install_project.py upgrade")
    args = ap.parse_args()
    project = (args.project or Path(__file__).resolve()).resolve()
    while project != project.parent and not (project / ".eif" / "PROJECT_MANIFEST.md").is_file():
        project = project.parent
    if not (project / ".eif" / "PROJECT_MANIFEST.md").is_file():
        raise SystemExit("could not locate EIF project root; pass --project")

    _ensure_gitattributes(project)
    _ensure_manifest_workspace(project)
    if not args.skip_junction:
        _ensure_workspace_junction(project)
    _renormalize(project)
    if not args.skip_upgrade:
        _upgrade(project)
    _ensure_cmd_dispatch(project)
    _patch_linux_anchor(project)
    print("OK:", project, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
