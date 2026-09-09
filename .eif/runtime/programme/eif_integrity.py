"""Stdlib-only delivered-runtime checks and cooperative reader/upgrade lock.

The local manifest detects drift, not an attacker replacing code plus manifest.
Callers bootstrap-check this helper before importing it. The installed programme
entry embeds this code so no application import precedes the integrity check.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import time

HOOK_MANIFEST_REL = '.cursor/eif-runtime-manifest.json'
RUNTIME_LOCK_REL = '.eif/runtime-upgrade.lock'
HOOK_NAMES = (
    'eif_guard.py', 'eif_guard.cmd', 'eif_guard.sh', 'eif_guard_crash.json',
    'eif_guard_failclosed.json', 'eif_integrity.py', 'eif_reason_codes.py',
    'eif_session.py', 'eif_state.py',
)
HOOK_INVENTORY = tuple(sorted(['.cursor/hooks.json'] + ['.cursor/hooks/' + name for name in HOOK_NAMES]))


def confined_file(project, relative):
    if not isinstance(relative, str) or not relative or '\\' in relative:
        raise ValueError('manifest path must be a nonempty relative POSIX path')
    path = PurePosixPath(relative)
    if path.is_absolute() or ':' in relative or any(part in {'', '.', '..'} for part in relative.split('/')):
        raise ValueError('manifest path escapes its declared runtime: ' + relative)
    target = (Path(project) / relative).resolve()
    if not target.is_relative_to(Path(project).resolve()):
        raise ValueError('manifest path resolves outside project: ' + relative)
    return target


def verify_manifest(project, manifest_relative, expected_files, *, kind, runtime_root=None, expected_product=None, control_interface=None):
    """Require exact independent inventory, safe paths and valid readable hashes."""
    try:
        project = Path(project).resolve()
        manifest_path = confined_file(project, manifest_relative)
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        if not isinstance(manifest, dict) or manifest.get('eif') != kind:
            return False, 'missing or invalid runtime manifest type'
        if runtime_root is not None and manifest.get('runtime_root') != runtime_root:
            return False, 'unexpected runtime_root in manifest'
        if control_interface is not None and manifest.get('control_interface') != control_interface:
            return False, 'unexpected control_interface in manifest'
        if expected_product is not None and manifest.get('product_version') != expected_product:
            return False, 'runtime manifest product_version does not match expected product'
        files = manifest.get('files')
        if not isinstance(files, dict) or set(files) != set(expected_files):
            return False, 'runtime manifest inventory differs from required shipped inventory'
        scan_root = confined_file(project, runtime_root or '.cursor/hooks')
        cached = [path.relative_to(project).as_posix() for path in scan_root.rglob('*.pyc') if path.is_file()]
        if cached:
            return False, 'unverified cached runtime bytecode: ' + ', '.join(sorted(cached))
        # Unregistered host shell scripts/data do not change this launch chain.
        # Python/native import candidates can shadow a verified module and must
        # be covered by the known inventory before application imports occur.
        executable_files = {path.relative_to(project).as_posix() for path in scan_root.rglob('*')
                            if path.is_file() and '__pycache__' not in path.parts and
                            path.suffix.lower() in {'.py', '.pyd', '.so', '.dll'} and
                            path.relative_to(project).as_posix() != manifest_relative}
        if executable_files - set(expected_files):
            return False, 'unexpected executable runtime files: ' + ', '.join(sorted(executable_files - set(expected_files)))
        for relative, expected in files.items():
            if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
                return False, 'invalid SHA-256 digest for ' + relative
            path = confined_file(project, relative)
            if not path.is_file():
                return False, 'runtime file missing: ' + relative
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                return False, 'runtime digest mismatch (control-plane drift): ' + relative
        return True, ''
    except (OSError, ValueError, TypeError, RecursionError) as error:
        return False, 'runtime manifest unreadable or invalid: ' + str(error)


def verify_hook_runtime(project):
    return verify_manifest(project, HOOK_MANIFEST_REL, HOOK_INVENTORY, kind='hook-runtime-manifest')


@contextmanager
def runtime_lock(project, *, exclusive=False, timeout=2.0):
    """Cooperative OS lock; shared readers, exclusive upgrades, bounded wait.

    Does not contain old runtime versions or processes that ignore this lock.
    Caller must hold it through verification AND use of delivered runtime files.
    """
    path = confined_file(Path(project).resolve(), RUNTIME_LOCK_REL)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+b')
    deadline = time.monotonic() + max(0.0, float(timeout))
    acquired = False
    try:
        if os.name == 'nt':
            import ctypes
            from ctypes import wintypes
            import msvcrt
            class OVERLAPPED(ctypes.Structure):
                _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                            ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                         wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(OVERLAPPED)]
            kernel.LockFileEx.restype = wintypes.BOOL
            kernel.UnlockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                                           wintypes.DWORD, ctypes.POINTER(OVERLAPPED)]
            kernel.UnlockFileEx.restype = wintypes.BOOL
            native = msvcrt.get_osfhandle(handle.fileno())
            overlapped = OVERLAPPED()
            def take():
                if kernel.LockFileEx(native, 1 | (2 if exclusive else 0), 0, 1, 0, ctypes.byref(overlapped)):
                    return True
                code = ctypes.get_last_error()
                if code != 33:  # ERROR_LOCK_VIOLATION
                    raise ctypes.WinError(code)
                return False
            def release():
                if not kernel.UnlockFileEx(native, 0, 1, 0, ctypes.byref(overlapped)):
                    raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl
            def take():
                try:
                    fcntl.flock(handle.fileno(), (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    return True
                except BlockingIOError:
                    return False
            def release():
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        while not acquired:
            acquired = take()
            if not acquired:
                if time.monotonic() >= deadline:
                    raise TimeoutError('runtime upgrade lock busy; retry after upgrade/recovery finishes')
                time.sleep(min(0.025, max(0.0, deadline - time.monotonic())))
        yield
    finally:
        try:
            if acquired:
                release()
        finally:
            handle.close()
