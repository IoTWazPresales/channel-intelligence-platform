"""Run N0065_r5_apply_cip.py with the owner URL built from the user-level PG_OWNER setting.

Same as N0065_r4_apply_cip_wrapper.py: the password is read from HKCU\\Environment (set by
Warren with SetEnvironmentVariable(..., 'User')), URL-encoded, and passed to the child only
through DATABASE_URL_SYNC_MIGRATE. Nothing is printed.
"""
import os
import subprocess
import sys
import winreg
from pathlib import Path
from urllib.parse import quote

HERE = Path(__file__).resolve().parent

with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
    owner_pw, _ = winreg.QueryValueEx(key, "PG_OWNER")
if not owner_pw:
    raise SystemExit("PG_OWNER is empty in the user environment")

env = dict(os.environ)
env["DATABASE_URL_SYNC_MIGRATE"] = f"postgresql://postgres:{quote(owner_pw, safe='')}@localhost:5432/cip"
del owner_pw

args = [sys.executable, str(HERE / "N0065_r5_apply_cip.py"), *sys.argv[1:]]
sys.exit(subprocess.call(args, env=env))
