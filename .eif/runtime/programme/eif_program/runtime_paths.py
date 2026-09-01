"""Installed programme runtime location and control interface."""
from __future__ import annotations

from pathlib import Path

PROGRAMME_RUNTIME_REL = '.eif/runtime/programme'
PROGRAMME_MANIFEST_REL = f'{PROGRAMME_RUNTIME_REL}/manifest.json'
PROGRAMME_CONTROL_CMD = f'python {PROGRAMME_RUNTIME_REL}/program.py'


def control_command() -> str:
    return PROGRAMME_CONTROL_CMD


def runtime_dir(project: Path) -> Path:
    return Path(project) / '.eif' / 'runtime' / 'programme'


def manifest_path(project: Path) -> Path:
    return Path(project) / '.eif' / 'runtime' / 'programme' / 'manifest.json'
