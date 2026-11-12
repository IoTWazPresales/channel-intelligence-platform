"""Confirm the profile imports the worktree cover handler."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

API = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(API))

from app.api.v1.endpoints import channel_ops
from app.services import brief_signals

print(channel_ops.__file__)
print("gather" in inspect.getsource(channel_ops.channel_ops_cover_distribution))
print(brief_signals.__file__)
print("gather_reads" in inspect.getsource(brief_signals.build_brief_payload))
