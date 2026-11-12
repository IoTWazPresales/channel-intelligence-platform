import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# change events on receipt / shipping UI
for pat in ["change.event", "change-event", "change_event", "cancelled.candidate", "date_slip", "qty_change"]:
    code, stdout, _ = git("grep", "-n", "-i", pat, "origin/feat/integrate-20261103", "--", "apps/web")
    print(f"==== web {pat} ====")
    print((stdout or "(none)")[:1500])

# promo_not_activated
code, stdout, _ = git("grep", "-n", "promo_not_activated\\|not_activated", "origin/feat/integrate-20261103", "--", "apps")
print("==== promo_not_activated ====")
for ln in (stdout or "").splitlines()[:50]:
    print(ln[:180])

# Brief attention signals
code, stdout, _ = git("grep", "-n", "Attention\\|attention_signal\\|proposed signal", "origin/feat/integrate-20261103", "--", "apps/web/src/features", "apps/api/app")
print("==== Attention ====")
for ln in (stdout or "").splitlines()[:40]:
    if "design-lab" in ln: continue
    print(ln[:180])

# shipment change events endpoint path
code, se, _ = git("show", "origin/feat/integrate-20261103:apps/api/app/api/v1/endpoints/shipment_evidence.py")
for i, ln in enumerate(se.splitlines(), 1):
    if "change" in ln.lower() and ("router" in ln or "@router" in ln or "def list_shipment" in ln or "/change" in ln):
        print(f"SE {i}:{ln[:160]}")

# Check if shipping detail already embeds events
code, stdout, _ = git("grep", "-n", "derive_change_events\\|change.events\\|events", "origin/feat/integrate-20261103", "--", "apps/web/src/features/shipping", "apps/web/src/app")
print("==== shipping features events ====")
print((stdout or "(none)")[:2000])

# list shipping feature files
code, stdout, _ = git("ls-tree", "-r", "--name-only", "origin/feat/integrate-20261103", "--", "apps/web/src/features")
feats = [ln for ln in stdout.splitlines() if "ship" in ln.lower() or "change" in ln.lower() or "brief" in ln.lower() or "overview" in ln.lower()]
print("==== feat files ship/brief ====")
for ln in feats[:60]:
    print(ln)
