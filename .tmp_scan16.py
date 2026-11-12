import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# Where is receipt mounted / how events loaded?
code, stdout, _ = git("grep", "-n", "ShipmentReceiptView\\|receipt/\\|shipment-receipt\\|change-events", "origin/feat/integrate-20261103", "--", "apps/web")
Path(out/"scan16a.txt").write_text(stdout or "(none)", encoding="utf-8")

# brief signals API
code, stdout, _ = git("grep", "-n", "brief/signals\\|promo_not\\|not_activated\\|def .*signal", "origin/feat/integrate-20261103", "--", "apps/api/app")
Path(out/"scan16b.txt").write_text(stdout or "(none)", encoding="utf-8")

# list brief service files
code, stdout, _ = git("ls-tree", "-r", "--name-only", "origin/feat/integrate-20261103", "--", "apps/api/app/services/brief", "apps/api/app/api/v1/endpoints")
briefish = [ln for ln in stdout.splitlines() if "brief" in ln.lower() or "signal" in ln.lower()]
Path(out/"scan16c.txt").write_text("\n".join(briefish + ["---"] + stdout.splitlines()[:30]), encoding="utf-8")

# Read brief endpoint / signals builder
code, stdout, _ = git("grep", "-l", "brief", "origin/feat/integrate-20261103", "--", "apps/api/app/api/v1/endpoints/*.py")
Path(out/"scan16d.txt").write_text(stdout or "(none)", encoding="utf-8")

# gh pr 68 with shell encoding fix
r = subprocess.run(["gh","pr","view","68","--json","files,title,state,baseRefName"], cwd=cwd, capture_output=True)
Path(out/"pr68.json").write_bytes(r.stdout or r.stderr)
print("done")
