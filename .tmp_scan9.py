from pathlib import Path
import re, subprocess
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")

ids = [6,8,31,60,64,79,84,85,91,106,113,117,148,149,156,158,161,181,182,192,194,195,196,197,199,200,201,202,209,221]
parts = re.split(r'(?m)^## BACKLOG-', bl)
by_id = {}
for part in parts[1:]:
    m = re.match(r'(\d+)', part)
    if m:
        by_id[int(m.group(1))] = part

def status_of(body):
    m = re.search(r'(?i)\|\s*\*\*?Status[^*|]*\*\*?\s*\|\s*([^|]+)\|', body)
    if m: return m.group(1).strip()[:120]
    m = re.search(r'(?i)\*\*Status[^*]*\*\*[:\s]+([^\n]+)', body)
    if m: return m.group(1).strip()[:120]
    return "?"

for n in ids:
    body = by_id.get(n)
    if not body:
        print(f"MISSING {n}")
        continue
    title = body.splitlines()[0][:100]
    st = status_of(body)
    print(f"\n===== BACKLOG-{n:03d} | {st}")
    print(title)
    # print key lines: Status, Files, Size, Why, Scope, Out of scope, Resume
    for ln in body.splitlines()[:35]:
        if re.search(r'(?i)status|file|path|size|touch|scope|resume|safe|overlap|depends|blocked|warren|migration|park', ln):
            print(ln[:160])
