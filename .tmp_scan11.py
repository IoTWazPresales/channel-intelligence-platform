from pathlib import Path
import re, subprocess
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")
parts = re.split(r'(?m)^## BACKLOG-', bl)
by_id = {}
for part in parts[1:]:
    m = re.match(r'(\d+)', part)
    if m: by_id[int(m.group(1))] = part

# Full bodies for promising candidates
for n in [6,8,11,31,60,64,80,179,183,186,187,188,189,198,206,213,217]:
    body = by_id.get(n)
    if not body:
        print("MISSING", n); continue
    print("\n" + "="*20 + f" BACKLOG-{n} " + "="*20)
    print("\n".join(body.splitlines()[:55]))

# Also search N- open items in tip CURRENT/BACKLOG
print("\n==== N- items in BACKLOG headers ====")
for m in re.finditer(r'(?m)^## (N-\d+)[^\n]*', bl):
    print(m.group(0)[:140])
