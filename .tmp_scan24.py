import subprocess
cwd = r"C:\AI\cip-b221"
r = subprocess.run(["git","ls-tree","-r","--name-only","origin/feat/integrate-20261103","--","apps/api/tests"], cwd=cwd, capture_output=True, text=True)
for ln in r.stdout.splitlines():
    if "brief" in ln.lower():
        print(ln)
r = subprocess.run(["git","grep","-l","build_brief_payload\\|brief_signals","origin/feat/integrate-20261103","--","apps/api/tests"], cwd=cwd, capture_output=True, text=True)
print("grep", r.stdout)
# listing activation late capability substrate - also capabilities LISTING late activation
# Confirm page.tsx is only remaining full mapping-candidates web caller
r = subprocess.run(["git","grep","-n","mapping-candidates\"","origin/feat/integrate-20261103","--","apps/web"], cwd=cwd, capture_output=True, text=True)
print("full endpoint callers:")
print(r.stdout)
r = subprocess.run(["git","grep","-n","/mapping-candidates'","origin/feat/integrate-20261103","--","apps/web"], cwd=cwd, capture_output=True, text=True)
print(r.stdout)
r = subprocess.run(["git","grep","-n","mapping-candidates[^\`]","origin/feat/integrate-20261103","--","apps/web"], cwd=cwd, capture_output=True, text=True)
for ln in r.stdout.splitlines():
    if "paginated" not in ln and "tab-counts" not in ln:
        print("NONPAG", ln[:180])
