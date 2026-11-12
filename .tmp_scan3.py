import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# MarketSurface around Propose
code, stdout, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/design-lab/surfaces/MarketSurface.tsx")
lines = stdout.splitlines()
print("MarketSurface lines", len(lines))
for i, ln in enumerate(lines, 1):
    if "Propose" in ln or "price" in ln.lower() and ("import" in ln.lower() or "Import" in ln) or "disabled" in ln:
        if 350 <= i <= 550 or "Propose" in ln:
            print(f"{i}:{ln}")

print("\n==== BACKLOG open SAFE-ish extract ====")
code, bl, _ = git("show", "origin/feat/integrate-20261103:docs/BACKLOG.md")
(out/"BACKLOG-tip.md").write_text(bl, encoding="utf-8")
# Parse items: look for BACKLOG-NNN and nearby Status
items = []
# Split by ## BACKLOG- or ### BACKLOG- or | BACKLOG-
# Prefer section headers
for m in re.finditer(r'(?m)^(#{2,3})\s*(BACKLOG-(\d+)|N-\d+|B-\d+)[^\n]*', bl):
    start = m.start()
    hdr = m.group(0)
    # take next 40 lines as body
    body = bl[start:start+2500]
    status_m = re.search(r'(?i)Status[:\s|*]+([^\n|]+)', body)
    status = (status_m.group(1).strip() if status_m else "?")
    items.append((m.group(2), hdr.strip(), status[:80]))

print("section count", len(items))
# Also table rows
for m in re.finditer(r'(?m)^\|\s*(BACKLOG-(\d+)|N-\d+)\s*\|([^|]*)\|([^|]*)\|', bl):
    print("TABLE", m.group(1), "|", m.group(3).strip()[:60], "|", m.group(4).strip()[:40])

# Print open-looking sections
print("\n==== Non-Done sections (status sample) ====")
for id_, hdr, st in items:
    if re.search(r'(?i)done|merged|shipped|closed', st):
        continue
    print(f"{id_} | {st} | {hdr[:100]}")
