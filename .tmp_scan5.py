import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# What did merge #67 change?
code, log, _ = git("log", "--oneline", "-15", "origin/feat/integrate-20261103")
print("LOG\n", log)

code, show, _ = git("show", "--stat", "--format=fuller", "36e9132c")
print("MERGE STAT\n", show[:2500])

# Find propose-related files on tip
code, grepped, _ = git("grep", "-n", "Propose candidates\\|propose_candidates\\|prices/import\\|score_competitor_candidate\\|Import prices", "origin/feat/integrate-20261103", "--", "apps/web", "apps/api")
print("GREP propose/import\n", grepped[:4000])

# MarketSurface full propose/price region
code, ms, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/design-lab/surfaces/MarketSurface.tsx")
lines = ms.splitlines()
for i in range(400, 520):
    if i < len(lines):
        print(f"{i+1}:{lines[i]}")
