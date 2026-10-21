"""N-0065 round 5: alembic up/down/up/down/up of 0027 on cip_test ONLY, with the catalogue after each step.

Usage (project root, API virtualenv): python <this> [steps...]   default: the five steps below.
Delegates to N0065_r3_alembic_cip_test.py (swaps to cip_test in-process, refuses when the
migrate URL is set, prints current_database()) and N0065_r5_catalogue.py cip_test.
Output appended to N0065_r5_updownup_cip_test.txt.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "apps", "api")
OUT = os.path.join(HERE, "N0065_r5_updownup_cip_test.txt")
STEPS = [("upgrade", "20261009_0027"), ("downgrade", "20261009_0026"), ("upgrade", "20261009_0027"),
         ("downgrade", "20261009_0026"), ("upgrade", "20261009_0027")]
if len(sys.argv) > 1:
    STEPS = [tuple(s.split(":")) for s in sys.argv[1:]]
env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL_SYNC_MIGRATE"}
env["PYTHONPATH"] = API


def run(args, cwd):
    p = subprocess.run([sys.executable, *args], cwd=cwd, capture_output=True, text=True, env=env, timeout=600)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


with open(OUT, "a", encoding="utf-8") as f:
    def say(s):
        print(s, flush=True)
        f.write(s + "\n")

    out, _ = run([os.path.join(HERE, "N0065_r5_catalogue.py"), "cip_test"], API)
    say(out.rstrip())
    for action, rev in STEPS:
        say(f"=== {action} {rev}")
        out, rc = run([os.path.join(HERE, "N0065_r3_alembic_cip_test.py"), action, rev], API)
        say(out.rstrip())
        if rc:
            say(f"exit {rc}; stopping")
            sys.exit(rc)
        out, _ = run([os.path.join(HERE, "N0065_r5_catalogue.py"), "cip_test"], API)
        say(out.rstrip())
