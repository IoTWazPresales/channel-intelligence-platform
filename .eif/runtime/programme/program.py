#!/usr/bin/env python3
"""EIF host-installed programme mutation CLI. Do not edit."""
from pathlib import Path
import sys

_RUNTIME = Path(__file__).resolve().parent
if str(_RUNTIME) not in sys.path:
    sys.path.insert(0, str(_RUNTIME))

from eif_program.cli import main  # noqa: E402

if __name__ == '__main__':
    raise SystemExit(main())
