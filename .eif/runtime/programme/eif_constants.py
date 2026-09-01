"""Canonical EIF host-runtime constants shared by installer, compiler, and guard."""
from __future__ import annotations

PROGRAMME_RUNTIME_REL = '.eif/runtime/programme'
PROGRAMME_MANIFEST_REL = f'{PROGRAMME_RUNTIME_REL}/manifest.json'
PROGRAMME_CONTROL_CMD = f'python {PROGRAMME_RUNTIME_REL}/program.py'
PROGRAMME_RUNTIME_GLOB = f'{PROGRAMME_RUNTIME_REL}/**'
