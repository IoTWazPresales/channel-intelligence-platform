from pathlib import Path
import re, subprocess
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")
parts = re.split(r'(?m)^## BACKLOG-', bl)
by_id = {}
for part in parts[1:]:
    m = re.match(r'(\d+)', part)
    if m:
        by_id[int(m.group(1))] = part

def status_of(body):
    m = re.search(r'(?i)\|\s*\*\*?Status[^*|]*\*\*?\s*\|\s*([^|]+)\|', body)
    if m: return m.group(1).strip()
    return "?"

# List all OPEN / Partial / Parked that look SAFE (exclude Done/Closed/Shipped/Resolved/Removed)
openish = []
for n, body in sorted(by_id.items()):
    st = status_of(body)
    title = body.splitlines()[0][:110]
    low = st.lower()
    if re.search(r'\b(done|closed|shipped|removed|not needed|retired|resolved for)\b', low) and not re.search(r'not resolved|correction.*not', low):
        continue
    # skip EIF / migration / warren-heavy markers in status
    openish.append((n, st[:100], title))

print(f"OPENISH count {len(openish)}")
for n, st, title in openish:
    print(f"{n:03d} | {st[:90]}")
    print(f"     {title}")
