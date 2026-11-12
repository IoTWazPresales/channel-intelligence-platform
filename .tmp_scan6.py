import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")

ids = [6,60,79,84,91,148,156,158,161,181,182,192,194,195,196,197,199,201,202,209,221,200,8,31,64,85,117,113,106,149]
# Extract each BACKLOG section
for n in ids:
    pat = rf'(?m)^## BACKLOG-{n:03d}\b.*?(?=^## BACKLOG-|\Z)'
    # also allow BACKLOG-6 without zero pad
    m = re.search(rf'(?m)^## BACKLOG-{n}\b.*?(?=^## |\Z)', bl)
    if not m:
        m = re.search(rf'(?m)^## BACKLOG-{n:03d}\b.*?(?=^## |\Z)', bl)
    if not m:
        print(f"MISSING {n}")
        continue
    body = m.group(0)
    # first 25 lines
    lines = body.splitlines()[:28]
    print(f"\n===== BACKLOG-{n} =====")
    print("\n".join(lines))
