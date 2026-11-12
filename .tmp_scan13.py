import subprocess, re
from pathlib import Path
cwd = r"C:\AI\cip-b221"
out = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200")
bl = (out/"BACKLOG-tip.md").read_text(encoding="utf-8")
parts = re.split(r'(?m)^## BACKLOG-', bl)
by_id = {int(re.match(r'(\d+)', p).group(1)): p for p in parts[1:] if re.match(r'(\d+)', p)}

def git(*args):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

# 1) Does web call change-events?
code, stdout, _ = git("grep", "-n", "change-events\\|change_events\\|ChangeEvent", "origin/feat/integrate-20261103", "--", "apps/web")
print("==== web change-events ====")
print(stdout[:2500] or "(none)")

# 2) MarketSurface promo_not_activated + SubstrateOrPlanned region
code, ms, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/features/market-listings/MarketSurface.tsx")
for i, ln in enumerate(ms.splitlines(), 1):
    if "promo_not_activated" in ln or "SubstrateOrPlanned" in ln or "not offered" in ln or "Import prices" in ln or "Propose candidates" in ln or "competitor-prices" in ln:
        print(f"MS {i}:{ln[:160]}")
print("--- around 1230-1260 ---")
for i in range(1230, 1265):
    print(f"{i}:{ms.splitlines()[i-1][:160]}")
print("--- around 1535-1570 ---")
for i in range(1535, 1580):
    if i <= len(ms.splitlines()):
        print(f"{i}:{ms.splitlines()[i-1][:160]}")

# 3) capabilities.ts
code, cap, _ = git("show", "origin/feat/integrate-20261103:apps/web/src/features/market-listings/capabilities.ts")
print("\n==== capabilities ====")
print(cap)

# 4) BACKLOG-064 fuller + BACKLOG-063
print("\n==== BACKLOG-063 ====")
print("\n".join(by_id.get(63, "missing").splitlines()[:40]))
print("\n==== BACKLOG-064 full ====")
print("\n".join(by_id.get(64, "missing").splitlines()[:40]))
print("\n==== BACKLOG-189 ====")
print("\n".join(by_id.get(189, "missing").splitlines()[:40]))
print("\n==== BACKLOG-186 ====")
print("\n".join(by_id.get(186, "missing").splitlines()[:40]))
print("\n==== BACKLOG-130 ====")
print("\n".join(by_id.get(130, "missing").splitlines()[:45]))
