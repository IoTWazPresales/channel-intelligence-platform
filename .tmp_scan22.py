import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# page.tsx around 374 - still full mapping-candidates?
code, page, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/app/(app)/admin/shipment-evidence/page.tsx")
for i in range(360, 400):
    print(f"PAGE {i+1}:{page.splitlines()[i][:160]}")

# listing intelligence route + web consumers
code, stdout, _ = git("grep", "-n", "intelligence\\|not_activated_worklist", "origin/feat/integrate-20261103", "--", "apps/web/src")
print("\n==== web intelligence ====")
for ln in stdout.splitlines()[:40]:
    if "design-lab" in ln: continue
    print(ln[:180])

# listing_capture endpoint path for intelligence
code, lc, _ = git("show", "origin/feat/integrate-20261103:apps/api/app/api/v1/endpoints/listing_capture.py")
for i, ln in enumerate(lc.splitlines(), 1):
    if "intelligence" in ln.lower() or "@router" in ln and i > 450 and i < 500:
        print(f"LC {i}:{ln[:160]}")
for i in range(455, 495):
    print(f"LC {i+1}:{lc.splitlines()[i][:160]}")

# BACKLOG-051
bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")
parts = re.split(r'(?m)^## BACKLOG-', bl)
by_id = {int(re.match(r'(\d+)', p).group(1)): p for p in parts[1:] if re.match(r'(\d+)', p)}
print("\n==== 051 ====")
print("\n".join(by_id.get(51,"missing").splitlines()[:35]))
print("\n==== 157 ====")
print("\n".join(by_id.get(157,"missing").splitlines()[:30]))
