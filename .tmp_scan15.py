import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# Receipt view - does it surface change events?
code, recv, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/features/supply-inbound/ShipmentReceiptView.tsx")
hits = []
for i, ln in enumerate(recv.splitlines(), 1):
    low = ln.lower()
    if any(k in low for k in ["change", "event", "cancel", "slip", "timeline", "history"]):
        hits.append(f"{i}:{ln[:160]}")
print("==== Receipt hits ====")
print("\n".join(hits[:40]) or "(none)")

# Brief signals
code, brief, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/features/brief/BriefPageContent.tsx")
print("\n==== Brief head ====")
print("\n".join(brief.splitlines()[:80]))
code, bsr, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/features/brief/BriefSignalRow.tsx")
print("\n==== BriefSignalRow ====")
print(bsr[:2500])

# Search BACKLOG for brief / promo_not / change-event / attention
for term in ["promo_not_activated", "Brief signal", "Attention (Brief)", "change-event UI", "not_activated worklist", "intelligence_v1"]:
    print(f"\n==== BL term {term} ====")
    for m in re.finditer(re.escape(term), bl):
        start = max(0, m.start()-80)
        print(bl[start:m.start()+120].replace("\n"," ")[:200])

# navConfig competition lines
code, nav, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/features/shell/navConfig.ts")
for i, ln in enumerate(nav.splitlines(), 1):
    if "Suggested matches" in ln or "competitor" in ln.lower() and ("not offered" in ln or "price" in ln):
        print(f"NAV {i}:{ln[:160]}")

# Confirm #68 files via gh
code, pr, _ = git("ls-remote", "origin", "pull/68/head")
print("\nPR68 ref", pr.strip())
# use gh if available
r = subprocess.run(["gh","pr","view","68","--json","files,title,baseRefName,headRefName,state"], cwd=cwd, capture_output=True, text=True)
print("gh68", r.stdout[:2000], r.stderr[:500])
