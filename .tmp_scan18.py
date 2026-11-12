import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
bl_parts = re.split(r'(?m)^## BACKLOG-', (out/"BACKLOG-tip.md").read_text(encoding="utf-8"))
by_id = {int(re.match(r'(\d+)', p).group(1)): p for p in bl_parts[1:] if re.match(r'(\d+)', p)}

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# shipmentCandidatesQuery - which endpoint?
code, q, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/app/(app)/admin/shipment-evidence/shipmentCandidatesQuery.ts")
print("==== shipmentCandidatesQuery ====")
print(q)

# brief_signals build_brief_payload - what signals
bs = (out/"brief_signals.py").read_text(encoding="utf-8")
# find build_brief_payload and list signal constructors
idx = bs.find("async def build_brief_payload")
print("\n==== build_brief_payload ====")
print(bs[idx:idx+3500])

# Find BulkLineupBackfillDialog path
code, stdout, _ = git("ls-tree", "-r", "--name-only", "origin/feat/integrate-20261103", "--", "apps/web")
for ln in stdout.splitlines():
    if "BulkLineup" in ln or "bulk-backfill" in ln.lower() or "BulkBackfill" in ln:
        print("FILE", ln)

# Also search BACKLOG items mentioning honesty / stale copy / residual after wire
for n, body in by_id.items():
    if re.search(r'(?i)honesty|stale copy|capability copy|navConfig|not offered yet', body):
        st = re.search(r'(?i)\|\s*\*\*?Status[^*|]*\*\*?\s*\|\s*([^|]+)\|', body)
        print(f"HIT {n}: {(st.group(1) if st else '?')[:80]} | {body.splitlines()[0][:90]}")
