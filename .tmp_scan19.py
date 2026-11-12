import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# #68 files via merge-base diff against tip
code, stdout, _ = git("fetch", "origin", "pull/68/head:refs/tmp/pr68")
code, stdout, _ = git("diff", "--name-only", "origin/feat/integrate-20261103...refs/tmp/pr68")
print("==== #68 files ====")
print(stdout)

# BulkLineupBackfillDialog apply/onClose
code, dlg, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/app/(app)/admin/imports/BulkLineupBackfillDialog.tsx")
(out/"BulkLineupBackfillDialog.tsx").write_text(dlg, encoding="utf-8")
for i, ln in enumerate(dlg.splitlines(), 1):
    if any(k in ln for k in ["onClose", "Apply", "registerClient", "complete", "success", "progress", "status"]):
        if i < 400:
            print(f"DLG {i}:{ln[:160]}")

# listing intelligence endpoint path + whether brief imports it
code, stdout, _ = git("grep", "-n", "intelligence_v1\\|not_activated_worklist\\|build_listing_intelligence", "origin/feat/integrate-20261103", "--", "apps/api")
print("\n==== intelligence ====")
for ln in stdout.splitlines()[:25]:
    print(ln[:180])

# Does page.tsx shipment evidence still hit non-paginated?
code, stdout, _ = git("grep", "-n", "mapping-candidates", "origin/feat/integrate-20261103", "--", "apps/web/src/app/(app)/admin/shipment-evidence", "apps/web/src/features/import-steward")
print("\n==== steward mapping-candidates URLs ====")
for ln in stdout.splitlines():
    print(ln[:180])
