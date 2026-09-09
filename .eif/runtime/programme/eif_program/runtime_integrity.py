"""Verify installed host programme runtime integrity from manifest."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .runtime_paths import PROGRAMME_CONTROL_CMD, PROGRAMME_MANIFEST_REL, PROGRAMME_RUNTIME_REL

PACKAGE_NAMES = (
    '__init__.py', 'cli.py', 'clock.py', 'design_artifacts.py', 'engine.py',
    'errors.py', 'facet_map.yaml', 'facets.py', 'findings.py', 'independence.py',
    'journeys.py', 'migrate.py', 'retroactive.py', 'runtime_integrity.py',
    'runtime_paths.py', 'store.py', 'views.py',
)
EXPECTED_FILES = tuple(sorted(
    [PROGRAMME_RUNTIME_REL + '/eif_program/' + name for name in PACKAGE_NAMES] +
    [PROGRAMME_RUNTIME_REL + '/' + name for name in
     ('program.py', 'eiflib.py', 'eif_constants.py', 'eif_integrity.py', 'eif_reason_codes.py')]
))


def _helper():
    # Installed callers have already passed the embedded program.py bootstrap.
    runtime = Path(__file__).resolve().parents[1]
    path = runtime / 'eif_integrity.py'
    if not path.is_file():
        path = runtime.parent / 'runtime/cursor/.cursor/hooks/eif_integrity.py'
    spec = importlib.util.spec_from_file_location('eif_program_integrity_core', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def repair_hint(project: Path) -> str:
    return (
        f'run `python tools/install_project.py upgrade {project}` from the EIF framework checkout '
        f'to refresh {PROGRAMME_CONTROL_CMD}'
    )


def verify_runtime(project: Path, *, expected_product: str | None = None) -> tuple[bool, str]:
    """Return (ok, diagnostic). Fails closed on any integrity defect."""
    try:
        ok, message = _helper().verify_manifest(project, PROGRAMME_MANIFEST_REL, EXPECTED_FILES,
            kind='programme-runtime-manifest', runtime_root=PROGRAMME_RUNTIME_REL,
            expected_product=expected_product, control_interface=PROGRAMME_CONTROL_CMD)
        return (True, '') if ok else (False, message + '; ' + repair_hint(project))
    except (OSError, ValueError, TypeError) as error:
        return False, 'runtime integrity verifier unavailable: ' + str(error)
