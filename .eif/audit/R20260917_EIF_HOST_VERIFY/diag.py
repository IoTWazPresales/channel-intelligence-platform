"""Host-runtime verification for the 61680aef guard digest. Audit-only; not product source."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
from pathlib import Path

EXPECTED_GUARD = "61680aefae4a1f0dab867b2bd46daacd2e9c6f4d3bf0784e46df30277d1d2c80"
FRAMEWORK = Path(r"C:\AI\engineering-intelligence-framework")

root = Path(__file__).resolve().parents[3]
hook = root / ".cursor" / "hooks" / "eif_guard.py"
hook_dir = hook.parent.resolve()
digest = hashlib.sha256(hook.read_bytes()).hexdigest()

print("project_root_from_script", root)
print("guard_path", hook)
print("guard_sha256", digest)
print("digest_match", digest == EXPECTED_GUARD)
print("hooks_is_symlink", (root / ".cursor" / "hooks").is_symlink())
print("guard_is_symlink", hook.is_symlink())
print("hook_dir_resolved", hook_dir)
print("CURSOR_PROJECT_DIR", os.environ.get("CURSOR_PROJECT_DIR"))
print("CLAUDE_PROJECT_DIR", os.environ.get("CLAUDE_PROJECT_DIR"))
print("cwd", Path.cwd().resolve())
print("--- ancestors compile_cursor.py ---")
for candidate in hook_dir.parents:
    marker = candidate / "tools" / "compile_cursor.py"
    print(f"{candidate} compile_cursor={marker.is_file()}")

print("framework_exists", FRAMEWORK.is_dir())
print("framework_compile_cursor", (FRAMEWORK / "tools" / "compile_cursor.py").is_file())
users_marker = Path(r"C:\Users\tools\compile_cursor.py")
print("users_compile_cursor", users_marker.is_file())

spec = importlib.util.spec_from_file_location("eif_guard_diag", hook)
mod = importlib.util.module_from_spec(spec)
sys.modules["eif_guard_diag"] = mod
spec.loader.exec_module(mod)
src, ref = mod.framework_runtime_locator(hook_dir)
print("source_root", src)
print("reference", ref)
print("_project_root", mod._project_root())
print("host_project_root", mod.host_project_root(hook_dir))
state, pol, p, msg = mod.load_policy(root)
print("policy_state", state)
print("policy_message", msg)
print("policy_path", p)
print("policy_status", (pol or {}).get("policy_status"))
print("policy_id", (pol or {}).get("policy_id"))
print("policy_project_id", (pol or {}).get("project_id"))

integ_path = hook_dir / "eif_integrity.py"
ispec = importlib.util.spec_from_file_location("eif_integrity_diag", integ_path)
imod = importlib.util.module_from_spec(ispec)
sys.modules["eif_integrity_diag"] = imod
ispec.loader.exec_module(imod)
ok, vmsg = imod.verify_hook_runtime(root)
print("verify_hook_runtime_ok", ok)
print("verify_hook_runtime_message", vmsg)

fw_guard = FRAMEWORK / "runtime" / "cursor" / ".cursor" / "hooks" / "eif_guard.py"
print("framework_guard_exists", fw_guard.is_file())
if fw_guard.is_file():
    fw_digest = hashlib.sha256(fw_guard.read_bytes()).hexdigest()
    print("framework_guard_sha256", fw_digest)
    print("framework_guard_matches_host", fw_digest == digest)
backup = hook_dir / "eif_guard.py.disk-backup"
print("disk_backup_exists", backup.is_file())
if backup.is_file():
    print("disk_backup_sha256", hashlib.sha256(backup.read_bytes()).hexdigest())
