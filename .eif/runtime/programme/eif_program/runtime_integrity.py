"""Verify installed host programme runtime integrity from manifest."""
from __future__ import annotations

import json
from pathlib import Path

from eiflib import read_utf8, sha256_path

from .runtime_paths import PROGRAMME_CONTROL_CMD, PROGRAMME_MANIFEST_REL, manifest_path


def repair_hint(project: Path) -> str:
    return (
        f'run `python tools/install_project.py upgrade {project}` from the EIF framework checkout '
        f'to refresh {PROGRAMME_CONTROL_CMD}'
    )


def verify_runtime(project: Path, *, expected_product: str | None = None) -> tuple[bool, str]:
    """Return (ok, diagnostic). Fails closed on any integrity defect."""
    project = Path(project).resolve()
    mpath = manifest_path(project)
    if not mpath.is_file():
        return False, (
            f'missing programme runtime manifest at {PROGRAMME_MANIFEST_REL}; '
            f'{repair_hint(project)}'
        )
    try:
        manifest = json.loads(read_utf8(mpath))
    except Exception as e:
        return False, f'unreadable programme runtime manifest: {e}; {repair_hint(project)}'
    if manifest.get('eif') != 'programme-runtime-manifest':
        return False, f'unknown manifest type {manifest.get("eif")!r}; {repair_hint(project)}'
    declared_cmd = manifest.get('control_interface')
    if declared_cmd and declared_cmd != PROGRAMME_CONTROL_CMD:
        return False, (
            f'stale control_interface {declared_cmd!r}; expected {PROGRAMME_CONTROL_CMD!r}; '
            f'{repair_hint(project)}'
        )
    product = manifest.get('product_version')
    if expected_product and product and product != expected_product:
        return False, (
            f'programme runtime product_version {product!r} != expected {expected_product!r}; '
            f'{repair_hint(project)}'
        )
    files = manifest.get('files') or {}
    if not files:
        return False, f'empty programme runtime manifest files map; {repair_hint(project)}'
    missing = []
    mismatched = []
    for rel, digest in files.items():
        path = project / rel.replace('/', '\\') if '\\' in str(project) else project / rel
        path = project / rel
        if not path.is_file():
            missing.append(rel)
            continue
        if sha256_path(path) != digest:
            mismatched.append(rel)
    if missing:
        return False, (
            'programme runtime incomplete (partial install/upgrade): ' + ', '.join(missing) + '; '
            + repair_hint(project)
        )
    if mismatched:
        return False, (
            'programme runtime digest mismatch (control-plane drift): ' + ', '.join(mismatched) + '; '
            + repair_hint(project)
        )
    return True, ''
