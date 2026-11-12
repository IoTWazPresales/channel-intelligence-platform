import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

patterns = [
    "SubstrateOrPlanned",
    "status=\"planned\"",
    "status='planned'",
    "not yet wired",
    "not offered yet",
    "TODO\\(wire",
    "FIXME.*wire",
    "unmounted",
    "dead code",
    "no production caller",
    "built but",
    "unused export",
]
for pat in patterns:
    code, stdout, _ = git("grep", "-n", "-i", pat, "origin/feat/integrate-20261103", "--", "apps/web/src", "apps/api/app", "docs")
    lines = [ln for ln in (stdout or "").splitlines() if "design-lab" not in ln and ".eif/" not in ln][:20]
    print(f"\n==== {pat} ({len((stdout or '').splitlines())} raw, showing {len(lines)}) ====")
    for ln in lines:
        print(ln[:180])

# Check shipment change events API existence vs UI
print("\n==== change.event / change_event ====")
code, stdout, _ = git("grep", "-n", "change_event\\|ChangeEvent\\|shipment_change", "origin/feat/integrate-20261103", "--", "apps")
for ln in (stdout or "").splitlines()[:40]:
    print(ln[:180])
