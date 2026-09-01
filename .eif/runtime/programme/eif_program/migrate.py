"""Import v0.4 ROADMAP.md / WORK_ITEM.md as proposed nodes. Additive only."""
from __future__ import annotations

import re
from pathlib import Path

from .errors import ProgramError
from .store import ProgramStore


def _headings(text: str) -> list[str]:
    return [m.group(1).strip() for m in re.finditer(r'(?m)^#{1,3}\s+(.+)$', text or '')]


def migrate(store: ProgramStore) -> dict:
    project = store.project
    eif = project / '.eif'
    roadmap = eif / 'ROADMAP.md'
    work = eif / 'WORK_ITEM.md'
    if not roadmap.exists() and not work.exists():
        # also accept repo-root copies
        roadmap = project / 'ROADMAP.md' if (project / 'ROADMAP.md').exists() else roadmap
        work = project / 'WORK_ITEM.md' if (project / 'WORK_ITEM.md').exists() else work
    if not store.exists():
        store.append('programme.init', {
            'outcome_statement': 'Imported from v0.4 ROADMAP/WORK_ITEM',
            'conservation_nouns': [],
            'identity_form': 'pre_history',
        })
        # Import is not charter acceptance. Nodes remain proposed/unverified until
        # an operator charters the programme through the canonical writer.
    def _generated(path: Path) -> bool:
        if not path.is_file():
            return False
        try:
            return path.read_text(encoding='utf-8').lstrip().startswith('<!-- GENERATED')
        except Exception:
            return False

    headings = []
    # Compatibility views overwrite ROADMAP/WORK_ITEM after a first migrate.
    # Do not re-import those generated headings as new proposed work.
    if roadmap.exists() and not _generated(roadmap):
        headings.extend(_headings(roadmap.read_text(encoding='utf-8')))
    if work.exists() and not _generated(work):
        body = work.read_text(encoding='utf-8')
        title = None
        m = re.search(r'(?m)^#\s+(.+)$', body)
        if m:
            title = m.group(1).strip()
        headings.append(title or 'Imported work item')
    # skip generic template and generated-view headings
    skip = {
        'roadmap', 'work item', 'now', 'next', 'later / hypotheses', 'explicit non-goals',
        'roadmap (node tree)', 'current frontier', 'escalation / decision queue',
    }
    seen = set()
    state = store.load()
    for node in (state.get('nodes') or {}).values():
        title = str(node.get('title') or '').lower()
        if title:
            seen.add(title)
    for h in headings:
        key = h.lower()
        if key in skip or key in seen:
            continue
        seen.add(key)
        state = store.append('node.add', {
            'title': h,
            'class': 'feature',
            'origin': 'operator',
            'status': 'proposed',
            'conservation_tags': [h],
        })
    return state
