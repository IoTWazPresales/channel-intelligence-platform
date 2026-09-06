"""Session deferral records: something did not fit; do not halt the rest of the run."""
from __future__ import annotations

from .errors import ProgramError

EVENT_TYPES = ('finding.defer',)


def h_finding_defer(s, p, run, actor='', replay=False, seq=None):
    note = p.get('note') or p.get('finding')
    if not str(note or '').strip():
        raise ProgramError('FINDING_NOTE', 'finding.defer requires note')
    rec = {
        'seq': seq,
        'code': str(p.get('code') or p.get('kind') or 'DOES_NOT_FIT'),
        'note': str(note).strip(),
        'node': p.get('node'),
        'run': run,
        'actor': actor,
        'status': 'deferred',
    }
    s.setdefault('deferred_findings', []).append(rec)


HANDLERS = {
    'finding.defer': h_finding_defer,
}
