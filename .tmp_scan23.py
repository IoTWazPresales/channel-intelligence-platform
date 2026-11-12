import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

code, stdout, _ = git("grep", "-n", "listing.*intelligence\\|/intelligence\\|not_activated_worklist\\|build_listing_intelligence", "origin/feat/integrate-20261103", "--", "apps/web")
Path(out/"scan23a.txt").write_text(stdout or "(none)", encoding="utf-8")

code, lc, _ = git("show", "origin/feat/integrate-20261103:apps/api/app/api/v1/endpoints/listing_capture.py")
# find router get intelligence
chunks = []
for i, ln in enumerate(lc.splitlines(), 1):
    if "intelligence" in ln.lower() or (460 <= i <= 490):
        chunks.append(f"{i}:{ln}")
Path(out/"scan23b.txt").write_text("\n".join(chunks), encoding="utf-8")

bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")
parts = re.split(r'(?m)^## BACKLOG-', bl)
by_id = {int(re.match(r'(\d+)', p).group(1)): p for p in parts[1:] if re.match(r'(\d+)', p)}
Path(out/"scan23-051.txt").write_text("\n".join(by_id.get(51,"missing").splitlines()[:40]), encoding="utf-8")
Path(out/"scan23-031.txt").write_text("\n".join(by_id.get(31,"missing").splitlines()[:40]), encoding="utf-8")

# Also check I2 BACKLOG-164 - score explanation - Closed?
Path(out/"scan23-164.txt").write_text("\n".join(by_id.get(164,"missing").splitlines()[:35]), encoding="utf-8")

# Late activation capability says substrate - capabilities listing
# Any BACKLOG for Brief listing activation?
for n, body in sorted(by_id.items()):
    if re.search(r'(?i)brief.*(listing|activat|promo_not)|listing.*brief|attention.*activat|promo_not_activated|not_activated.*brief', body):
        Path(out/f"scan23-bl{n}.txt").write_text("\n".join(body.splitlines()[:40]), encoding="utf-8")

print("ok")
