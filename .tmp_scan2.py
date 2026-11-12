import subprocess
from pathlib import Path
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
cwd = r"C:\AI\cip-b221"

def show(path):
    return subprocess.check_output(["git","show", f"origin/feat/integrate-20261103:{path}"], cwd=cwd)

current = show("docs/memory/CURRENT.md").decode("utf-8")
(out/"CURRENT-tip-36e9132c.md").write_text(current, encoding="utf-8")
print("CURRENT_BYTES", len(current))
print(current[:3500])
print("---ENDHEAD---")

# Grep-like scans via git grep
patterns = [
    "Deal-stock landing",
    "Over-plan intake",
    "require_roles(Role.ADMIN)",
    "not offered",
    "not imported yet",
    "disabled={true}",
    "disabled>",
]
for pat in patterns:
    r = subprocess.run(["git","grep","-n",pat,"origin/feat/integrate-20261103","--","apps/web","apps/api"], cwd=cwd, capture_output=True, text=True)
    print(f"==== {pat} exit={r.returncode} ====")
    lines = (r.stdout or "").splitlines()[:25]
    for ln in lines:
        print(ln)
