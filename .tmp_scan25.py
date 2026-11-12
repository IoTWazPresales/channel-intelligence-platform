import subprocess
cwd = r"C:\AI\cip-b221"
r = subprocess.run(["git","grep","-n","mapping-candidates","origin/feat/integrate-20261103","--","apps/web"], cwd=cwd, capture_output=True, text=True)
for ln in r.stdout.splitlines():
    if "/mapping-candidates" in ln:
        print(ln[:200])
