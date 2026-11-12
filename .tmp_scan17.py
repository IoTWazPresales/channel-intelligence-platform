import subprocess
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

code, bs, _ = git("show", "origin/feat/integrate-20261103:apps/api/app/services/brief_signals.py")
(out/"brief_signals.py").write_text(bs, encoding="utf-8")
print("brief_signals len", len(bs.splitlines()))
# print function names and signal ids
for i, ln in enumerate(bs.splitlines(), 1):
    if ln.startswith("def ") or '"id"' in ln or "id=" in ln and "signal" in ln.lower() or "promo" in ln.lower() or "listing" in ln.lower() or "activat" in ln.lower():
        print(f"{i}:{ln[:160]}")

code, be, _ = git("show", "origin/feat/integrate-20261103:apps/api/app/api/v1/endpoints/brief.py")
print("\n==== brief endpoint ====")
print(be[:3000])

# mapping-candidates endpoint location
code, stdout, _ = git("grep", "-n", "mapping-candidates\\|list_shipment_import_job_mapping_candidates", "origin/feat/integrate-20261103", "--", "apps/api", "apps/web")
(out/"mapping-candidates-hits.txt").write_text(stdout, encoding="utf-8")
print("\n==== mapping-candidates (first 30) ====")
for ln in stdout.splitlines()[:30]:
    print(ln[:180])

# BulkLineupBackfillDialog onClose
code, stdout, _ = git("grep", "-n", "onClose\\|registerClientBackgroundTask\\|BulkLineupBackfill", "origin/feat/integrate-20261103", "--", "apps/web/src/features")
print("\n==== bulk backfill hits ====")
for ln in stdout.splitlines():
    if "BulkLineup" in ln or "bulk-backfill" in ln or "bulk_backfill" in ln:
        print(ln[:180])
