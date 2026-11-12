import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# Confirm tip sha
code, tip, _ = git("rev-parse", "origin/feat/integrate-20261103")
print("TIP", tip.strip())

# Read classification + orphan from PC paths (not git)
for p in [
    r"C:\AI\cip-run-logs\verify-b200\CLASSIFICATION_AND_PRS_20261109.txt",
    # also try warren path
]:
    pp = Path(p)
    print("CLASS exists", pp.exists(), p)

# Find classification file
from pathlib import Path
cands = list(Path(r"C:\AI\cip-run-logs").rglob("CLASSIFICATION_AND_PRS_20261109.txt"))
cands += list(Path(r"C:\Users\warren_eliason\cip-run-logs").rglob("CLASSIFICATION_AND_PRS_20261109.txt"))
print("found class files", cands)
for c in cands[:2]:
    t = c.read_text(encoding="utf-8", errors="replace")
    print("====", c, "len", len(t))
    print(t[:6000])

print("\n==== ORPHAN audit tip ====")
code, oa, _ = git("show", "origin/feat/integrate-20261103:docs/audits/ORPHAN_AND_STAGE_STATUS_20261109.md")
(out/"ORPHAN-tip.md").write_text(oa, encoding="utf-8")
print(oa[:5000])
