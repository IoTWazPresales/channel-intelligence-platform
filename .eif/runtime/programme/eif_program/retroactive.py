"""Append-only retroactive charter/complete, independence disclaimer, and caveat resolve.

Handlers are registered into apply_event. They never rewrite history. They never
stamp implementation_run. Independence-required gates stay currently invalid
unless real (non-disclaimed) implementation provenance exists.
"""
from __future__ import annotations

from .errors import ProgramError
from .independence import node_requires_independence

EVENT_TYPES = (
    'node.retroactive_charter',
    'node.retroactive_complete',
    'node.independence.disclaim',
    'caveat.resolve',
)


def require_evidence_ids(state: dict, payload: dict) -> list[str]:
    raw = payload.get('evidence_ids')
    if raw is None:
        raw = payload.get('evidence')
    if raw is None:
        ids: list[str] = []
    elif isinstance(raw, list):
        ids = [str(x) for x in raw if x]
    else:
        ids = [str(raw)] if raw else []
    if not ids:
        raise ProgramError(
            'EVIDENCE_REQUIRED',
            'retroactive/caveat/disclaim events require evidence id(s) already in the ledger',
        )
    missing = [i for i in ids if i not in (state.get('evidence') or {})]
    if missing:
        raise ProgramError('EVIDENCE_UNKNOWN', ','.join(missing))
    return ids


def node_is_retroactive(node: dict | None) -> bool:
    r = (node or {}).get('retroactive') or {}
    return bool(
        r.get('chartered') or r.get('completed') or r.get('independence_disclaimed')
    )


def ensure_retro(node: dict) -> dict:
    r = node.get('retroactive')
    if not isinstance(r, dict):
        r = {}
        node['retroactive'] = r
    r.setdefault('chartered', False)
    r.setdefault('completed', False)
    r.setdefault('independence_disclaimed', False)
    r.setdefault('independence_unrecoverable', False)
    r.setdefault('as_of', None)
    r.setdefault('evidence', [])
    r.setdefault('recording_runs', [])
    r.setdefault('disclaimed_pass_runs', [])
    r.setdefault('disclaimed_impl_runs', [])
    r.setdefault('chartered_seq', None)
    r.setdefault('completed_seq', None)
    r.setdefault('disclaimed_seq', None)
    return r


def _note_run(retro: dict, run: str) -> None:
    if not run:
        return
    runs = list(retro.get('recording_runs') or [])
    if run not in runs:
        runs.append(run)
    retro['recording_runs'] = runs


def _merge_evidence(retro: dict, ids: list[str]) -> None:
    have = [str(x) for x in (retro.get('evidence') or [])]
    for i in ids:
        if i not in have:
            have.append(i)
    retro['evidence'] = have


def tree_support(state: dict, nid: str) -> str:
    """Worst support under nid: clean | retroactive | invalid_gates."""
    from .engine import descendants, gates_ok, is_leaf

    order = {'clean': 0, 'retroactive': 1, 'invalid_gates': 2}
    worst = 'clean'

    def consider(oid: str) -> None:
        nonlocal worst
        node = state['nodes'][oid]
        kind = 'clean'
        if is_leaf(state, oid) and node.get('status') == 'complete' and not gates_ok(state, oid):
            kind = 'invalid_gates'
        elif node_is_retroactive(node):
            kind = 'retroactive'
        if order[kind] > order[worst]:
            worst = kind

    consider(nid)
    for d in descendants(state, nid):
        consider(d)
    return worst


def h_retro_charter(s, p, run, actor='', replay=False, seq=None):
    from .engine import bump, mutable_node

    node = mutable_node(s, p, run, replay=replay)
    ids = require_evidence_ids(s, p)
    retro = ensure_retro(node)
    retro['chartered'] = True
    retro['chartered_seq'] = seq
    retro['as_of'] = p.get('as_of') or retro.get('as_of')
    if p.get('note') is not None:
        retro['charter_note'] = p.get('note')
    _merge_evidence(retro, ids)
    _note_run(retro, run)
    if node.get('origin') in {None, '', 'decomposition'}:
        node['origin'] = 'retroactive'
    bump(node)


def h_retro_complete(s, p, run, actor='', replay=False, seq=None):
    from .engine import bump, is_leaf, mutable_node

    node = mutable_node(s, p, run, replay=replay)
    if not is_leaf(s, node['id']):
        raise ProgramError('DERIVED_COMPLETE', 'non-leaf complete is derived; do not assert it')
    ids = require_evidence_ids(s, p)
    if node_requires_independence(node) and not p.get('independence_unrecoverable'):
        raise ProgramError(
            'RETROACTIVE_INDEPENDENCE',
            f'{node["id"]} has an independence burden; retroactive complete requires '
            'independence_unrecoverable=true (charter-only plus later real complete is preferred)',
        )
    retro = ensure_retro(node)
    retro['completed'] = True
    retro['chartered'] = True
    retro['completed_seq'] = seq
    retro['as_of'] = p.get('as_of') or retro.get('as_of')
    if p.get('note') is not None:
        retro['complete_note'] = p.get('note')
    if p.get('independence_unrecoverable'):
        retro['independence_unrecoverable'] = True
    _merge_evidence(retro, ids)
    _note_run(retro, run)
    node['status'] = 'complete'
    node['lease'] = None
    node['stage'] = None
    if node.get('origin') in {None, '', 'decomposition'}:
        node['origin'] = 'retroactive'
    bump(node)


def h_independence_disclaim(s, p, run, actor='', replay=False, seq=None):
    from .engine import bump, mutable_node
    from .independence import quality_dim_requires_independence, verification_requires_independence

    node = mutable_node(s, p, run, replay=replay)
    ids = require_evidence_ids(s, p)
    reason = p.get('reason') or p.get('note')
    if not reason:
        raise ProgramError('DISCLAIM_REASON', 'independence disclaimer requires reason')
    retro = ensure_retro(node)
    retro['independence_disclaimed'] = True
    retro['disclaimed_seq'] = seq
    retro['disclaim_reason'] = reason
    _merge_evidence(retro, ids)
    _note_run(retro, run)
    impl = node.get('implementation_run')
    if impl:
        dis = list(retro.get('disclaimed_impl_runs') or [])
        if impl not in dis:
            dis.append(impl)
        retro['disclaimed_impl_runs'] = dis
    passes = list(retro.get('disclaimed_pass_runs') or [])
    for dim, rec in (node.get('quality') or {}).items():
        if not quality_dim_requires_independence(node, dim):
            continue
        pr = rec.get('pass_run')
        if pr and pr not in passes:
            passes.append(pr)
    for kind in ('referent', 'rendered'):
        if not verification_requires_independence(node, kind):
            continue
        rec = (node.get('verification') or {}).get(kind) or {}
        pr = rec.get('pass_run')
        if pr and pr not in passes:
            passes.append(pr)
    retro['disclaimed_pass_runs'] = passes
    bump(node)


def h_caveat_resolve(s, p, run, actor='', replay=False, seq=None):
    from .engine import bump, mutable_node

    prior = p.get('prior_seq')
    if prior is None:
        raise ProgramError('CAVEAT_SEQ', 'prior_seq required')
    try:
        prior_i = int(prior)
    except (TypeError, ValueError):
        raise ProgramError('CAVEAT_SEQ', str(prior))
    head = int((s.get('programme') or {}).get('snapshot_revision') or 0)
    if prior_i < 1 or prior_i > head:
        raise ProgramError('CAVEAT_SEQ', f'prior_seq {prior_i} not in 1..{head}')
    ids = require_evidence_ids(s, p)
    resolution = p.get('resolution')
    if not resolution:
        raise ProgramError('CAVEAT_RESOLUTION', 'resolution required')
    node = None
    if p.get('node'):
        node = mutable_node(s, p, run, replay=replay)
    key = str(p.get('key') or f'seq-{prior_i}')
    s.setdefault('caveats', {})[key] = {
        'key': key,
        'prior_seq': prior_i,
        'resolved_seq': seq,
        'resolution': resolution,
        'evidence': ids,
        'status': 'resolved',
        'node': p.get('node'),
        'provenance': 'asserted',
        'unverified_open': True,
        'run': run,
        'actor': actor,
    }
    if node is not None:
        bump(node)


HANDLERS = {
    'node.retroactive_charter': h_retro_charter,
    'node.retroactive_complete': h_retro_complete,
    'node.independence.disclaim': h_independence_disclaim,
    'caveat.resolve': h_caveat_resolve,
}
