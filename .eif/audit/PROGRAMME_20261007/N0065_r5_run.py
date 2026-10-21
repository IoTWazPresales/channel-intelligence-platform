"""N-0065 round 5 cip_test runner. From the project root with the API virtualenv:

    python <this> <outfile-stem> all|parity|n0065 [pytest args]

Runs N0065_r5_final_run.py (which swaps to cip_test in-process, asserts the name and prints
current_database()) from apps/api; output goes to <outfile-stem>.txt in this folder, exit code
printed. The parity JSON goes to N0065_r5_parity.json.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "apps", "api")
stem, rest = sys.argv[1], sys.argv[2:]
code = ("import runpy,os,sys; sys.argv=['N0065_r5_final_run.py'] + " + repr(rest) + "; "
        "runpy.run_path(" + repr(os.path.join(HERE, "N0065_r5_final_run.py")) + ", run_name='__main__')")
env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL_SYNC_MIGRATE"}
env["PYTHONPATH"] = API
out_path = os.path.join(HERE, stem + ".txt")
with open(out_path, "w", encoding="utf-8") as f:
    p = subprocess.run([sys.executable, "-c", code], cwd=API, stdout=f, stderr=subprocess.STDOUT, env=env,
                       timeout=7200)
text = open(out_path, encoding="utf-8").read().splitlines()
print("exit", p.returncode, "| output", out_path)
for ln in text:
    if ln.startswith(("current_database()", "role =", "test files:", "FAILED", "ERROR")) or " passed" in ln or " failed" in ln:
        print(ln[:300])
