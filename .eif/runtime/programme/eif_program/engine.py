"""Pure programme reducer. PROGRAM_LOG events in; snapshot dict out."""
from __future__ import annotations

import copy
import hashlib
from datetime import timedelta
from typing import Any

import yaml

from .clock import iso, now, parse_iso
from .design_artifacts import design_experience_ok, materialize_artifact_classes
from .errors import ProgramError
from .facets import resolve_facets
from .independence import independence_issues, independence_ok
from .journeys import journeys_gate_ok, required_journey_ids

NODE_CLASSES = {
    'feature', 'redesign', 'refactor', 'discovery', 'inception', 'skeleton',
    'parity', 'cutover', 'observation', 'human', 'milestone',
}
STATUSES = {
    'proposed', 'accepted', 'ready', 'in_progress', 'blocked',
    'complete', 'deferred', 'rejected', 'split',
}
TERMINAL = {'complete', 'deferred', 'rejected', 'split'}
STAGE_ORDER = ['discovery', 'challenge', 'design', 'implement', 'validate', 'verify']
QUALITY_DONE = {'pass', 'resolved', 'na'}
BROWNFIELD = {'redesign', 'refactor', 'parity'}

_FACET_CACHE = None


def facet_map() -> dict:
    global _FACET_CACHE
    if _FACET_CACHE is None:
        from pathlib import Path
        p = Path(__file__).resolve().parent / 'facet_map.yaml'
        if not p.is_file():
            # EIF framework checkout layout (legacy path during development).
            p = Path(__file__).resolve().parents[2] / 'program' / 'facet_map.yaml'
        _FACET_CACHE = yaml.safe_load(p.read_text(encoding='utf-8')) or {}
    return _FACET_CACHE


def risk_rank(r: str) -> int:
    try:
        return int(str(r).upper().replace('R', ''))
    except Exception:
        return 0


def empty_state() -> dict:
    return {
        'schema': 'eif.program/1',
        'programme': {
            'id': None,
            'outcome_statement': None,
            'conservation_nouns': [],
            'charter': {
                'status': 'pending', 'by': None, 'at': None,
                'workstreams': [], 'assumptions': [],
                'inclusions': [], 'exclusions': [],
                'root_interpretation': None,
            },
            'status': 'active',
            'identity': {'form': 'pre_history', 'project_id': None, 'root_commit': None},
            'snapshot_revision': 0,
            'log_sha256': None,
            'acceptance_policy': {
                'milestone': 'operator', 'root': 'operator',
                'r3_plus': 'operator', 'default': 'auto',
            },
            'debug_budget': 5,
        },
        'nodes': {},
        'decisions': {},
        'evidence': {},
        'baselines': {},
        'ids': {'node': 0, 'decision': 0, 'blocker': 0, 'evidence': 0, 'baseline': 0},
    }


def next_id(state: dict, kind: str, prefix: str) -> str:
    state['ids'][kind] = int(state['ids'].get(kind) or 0) + 1
    return f'{prefix}-{state["ids"][kind]:04d}'


def children_of(state: dict, nid: str) -> list[str]:
    return [i for i, n in state['nodes'].items() if n.get('parent') == nid]


def descendants(state: dict, nid: str) -> list[str]:
    out: list[str] = []
    stack = children_of(state, nid)
    while stack:
        cur = stack.pop()
        out.append(cur)
        stack.extend(children_of(state, cur))
    return out


def is_leaf(state: dict, nid: str) -> bool:
    return len(children_of(state, nid)) == 0


def is_terminal(status: str) -> bool:
    return status in TERMINAL


def is_ancestor(state: dict, maybe_anc: str, node: str) -> bool:
    cur = state['nodes'].get(node, {}).get('parent')
    while cur:
        if cur == maybe_anc:
            return True
        cur = state['nodes'].get(cur, {}).get('parent')
    return False


def live_lease(node: dict) -> bool:
    lease = node.get('lease') or {}
    exp = lease.get('expires_at')
    if not exp:
        return False
    try:
        return parse_iso(exp) > now()
    except Exception:
        return False


def needs_baseline(node: dict) -> bool:
    if node.get('class') in BROWNFIELD:
        return True
    if node.get('class') == 'feature' and node.get('touches_existing') and risk_rank(node.get('risk', 'R0')) >= 2:
        return True
    return False


def valid_baseline(state: dict, node: dict) -> bool:
    ref = node.get('baseline_ref')
    if not ref:
        return False
    bl = state['baselines'].get(ref)
    if not bl:
        return False
    if bl.get('provenance') == 'design-direction':
        return False
    return True


def rebuild_quality(node: dict) -> None:
    fmap = facet_map()
    required: dict[str, bool] = {}
    risk = node.get('risk') or 'R0'
    for f in node.get('facets') or []:
        spec = fmap.get(f) or {}
        for dim, rules in spec.items():
            if risk_rank(risk) >= risk_rank((rules or {}).get('min_risk', 'R0')):
                required[dim] = True
    if node.get('class') == 'milestone':
        for dim, rules in (fmap.get('milestone') or {}).items():
            if risk_rank(risk) >= risk_rank((rules or {}).get('min_risk', 'R0')):
                required[dim] = True
    q = node.setdefault('quality', {})
    for dim in list(q):
        if dim not in required:
            q[dim]['required'] = False
    for dim in required:
        rec = q.setdefault(dim, {'required': True, 'state': 'pending', 'evidence': None, 'rationale': None})
        rec['required'] = True


def stamp_implementation_boundary(node: dict, run: str, actor: str) -> None:
    """Record implementation run/actor from the first node.stage -> implement only."""
    if not node.get('implementation_run') and run:
        node['implementation_run'] = run
        node['implementation_actor'] = actor or None


def stamp_pass_provenance(rec: dict, state: str | None, run: str, actor: str) -> None:
    if state in QUALITY_DONE and state != 'na':
        rec['pass_run'] = run or None
        rec['pass_actor'] = actor or None
    elif state in {'pending', 'blocked'}:
        rec.pop('pass_run', None)
        rec.pop('pass_actor', None)


def quality_check(node: dict, *, check_independence: bool = True) -> tuple[bool, str | None]:
    """Return (ok, reason). reason is set only on failure."""
    for rec in (node.get('quality') or {}).values():
        if not rec.get('required'):
            continue
        st = rec.get('state')
        if st not in QUALITY_DONE:
            return False, 'required quality dimensions incomplete'
        if st == 'na' and not rec.get('rationale'):
            return False, 'na requires rationale'
    ok, reason = design_experience_ok(node)
    if not ok:
        return ok, reason
    if check_independence:
        return independence_ok(node)
    return True, None


def gates_valid(node: dict, *, check_independence: bool = True) -> tuple[bool, list[str]]:
    """Current gate validity for a node snapshot (quality + independence)."""
    ok, reason = quality_check(node, check_independence=check_independence)
    if ok:
        return True, []
    issues = independence_issues(node) if check_independence else []
    if issues:
        return False, issues
    return False, [reason] if reason else []


def quality_ok(node: dict, *, check_independence: bool = True) -> bool:
    ok, _reason = quality_check(node, check_independence=check_independence)
    return ok


def gates_ok(
    state: dict,
    nid: str,
    *,
    check_journeys: bool = True,
    check_independence: bool = True,
) -> bool:
    node = state['nodes'][nid]
    if not quality_ok(node, check_independence=check_independence):
        return False
    if node.get('acceptance') == 'operator' and node.get('acceptance_state') != 'accepted':
        return False
    if node.get('class') == 'human' and node.get('acceptance_state') != 'accepted':
        return False
    ver = node.get('verification') or {}
    if 'ui' in (node.get('facets') or []):
        rend = (ver.get('rendered') or {}).get('state')
        qrend = ((node.get('quality') or {}).get('rendered') or {}).get('state')
        if rend not in QUALITY_DONE and qrend not in QUALITY_DONE:
            return False
    if risk_rank(node.get('risk', 'R0')) >= 3:
        ref = (ver.get('referent') or {}).get('state')
        if ref not in QUALITY_DONE:
            return False
    if node.get('class') == 'parity':
        src = node.get('parity_source') or []
        matrix = node.get('parity_matrix') or {}
        if any(s not in matrix for s in src):
            return False
        retires = node.get('parity_retire_decisions') or {}
        for s in src:
            if matrix.get(s) == 'retire' and s not in retires:
                return False
    if node.get('class') == 'skeleton':
        rend = (ver.get('rendered') or {}).get('state')
        if rend not in QUALITY_DONE:
            return False
    if check_journeys and not journeys_gate_ok(node, state.get('journeys_catalog')):
        return False
    return True


def effective_status(state: dict, nid: str) -> str:
    node = state['nodes'][nid]
    recorded = node['status']
    if recorded in {'deferred', 'rejected', 'split'}:
        return recorded
    if is_leaf(state, nid):
        return recorded
    desc = descendants(state, nid)
    if desc and all(effective_status(state, d) in TERMINAL for d in desc) and gates_ok(state, nid):
        return 'complete'
    return recorded


def bump(node: dict) -> None:
    node['revision'] = int(node.get('revision') or 0) + 1


def assert_revision(node: dict, expected: Any) -> None:
    if expected is None:
        raise ProgramError('REVISION_REQUIRED', 'node mutation requires expected_revision')
    if int(expected) != int(node.get('revision') or 0):
        raise ProgramError('STALE_REVISION', f'expected revision {expected}, actual {node.get("revision")}')


def assert_scope(state: dict, target: str, decision_id: str | None) -> None:
    if not decision_id:
        return
    dec = state['decisions'].get(decision_id)
    if not dec:
        raise ProgramError('DECISION_UNKNOWN', str(decision_id))
    scope = dec.get('scope')
    if not scope:
        return
    if target == scope:
        return
    if is_ancestor(state, target, scope):
        raise ProgramError('ANTI_ECLIPSE', f'decision {decision_id} scoped to {scope} cannot alter ancestor {target}')
    if target not in descendants(state, scope):
        raise ProgramError('ANTI_ECLIPSE', f'decision {decision_id} scoped to {scope} cannot alter {target}')


def assert_lease_owner(node: dict, run: str, *, allow_expired=False) -> None:
    lease = node.get('lease')
    if not lease:
        return
    if live_lease(node) and lease.get('run') != run:
        raise ProgramError('LEASE_HELD', f'node leased to {lease.get("run")}')
    if not live_lease(node) and not allow_expired and lease.get('run') != run:
        raise ProgramError('LEASE_EXPIRED', 'lease expired; reclaim before mutating')


def _lease_record_owner(node: dict, run: str) -> None:
    lease = node.get('lease')
    if lease and lease.get('run') != run:
        raise ProgramError('LEASE_NOT_OWNER', run)


def mutable_node(
    state: dict,
    payload: dict,
    run: str,
    *,
    allow_expired=False,
    replay: bool = False,
) -> dict:
    nid = payload.get('node') or payload.get('id')
    if nid not in state['nodes']:
        raise ProgramError('NODE_UNKNOWN', str(nid))
    node = state['nodes'][nid]
    assert_revision(node, payload.get('expected_revision'))
    assert_scope(state, nid, payload.get('decision'))
    if not replay:
        assert_lease_owner(node, run, allow_expired=allow_expired)
    return node


def apply_event(state: dict, event: dict, *, replay: bool = False) -> dict:
    s = copy.deepcopy(state)
    et = event['event']
    payload = event.get('payload')
    if not isinstance(payload, dict):
        payload = {}
        event['payload'] = payload
    # Persist/recover programme id from the event so replay is deterministic.
    # v0.5.1 migrate often omitted payload id; generating from wall clock on
    # every load would reinterpret identity.
    if et == 'programme.init' and not payload.get('id'):
        ts = event.get('ts') or iso()
        payload['id'] = f"PRG-{str(ts).replace('-', '').replace(':', '')[:15]}"
    run = event.get('run') or ''
    actor = event.get('actor') or ''
    handlers = {
        'programme.init': h_init,
        'programme.charter': h_charter,
        'programme.status': h_prog_status,
        'identity.set': h_identity,
        'node.add': h_node_add,
        'node.patch': h_node_patch,
        'node.lease.acquire': h_lease_acquire,
        'node.lease.heartbeat': h_lease_heartbeat,
        'node.lease.release': h_lease_release,
        'node.lease.reclaim': h_lease_reclaim,
        'node.stage': h_stage,
        'node.status': h_status,
        'node.quality': h_quality,
        'node.verification': h_verification,
        'node.blocker.open': h_blocker_open,
        'node.blocker.close': h_blocker_close,
        'node.baseline': h_node_baseline,
        'node.stage_note': h_stage_note,
        'node.debug': h_debug,
        'node.accept': h_accept,
        'decision.add': h_decision_add,
        'decision.status': h_decision_status,
        'evidence.add': h_evidence_add,
        'baseline.add': h_baseline_add,
    }
    fn = handlers.get(et)
    if not fn:
        raise ProgramError('UNKNOWN_EVENT', et)
    _REPLAY_AWARE = {
        'node.patch', 'node.lease.acquire', 'node.lease.heartbeat', 'node.lease.release',
        'node.lease.reclaim', 'node.stage', 'node.status', 'node.quality',
        'node.verification', 'node.blocker.open', 'node.blocker.close', 'node.baseline',
        'node.stage_note', 'node.debug', 'node.accept',
    }
    if et in _REPLAY_AWARE:
        fn(s, payload, run, actor=actor, replay=replay)
    else:
        fn(s, payload, run, actor=actor)
    if event.get('seq') is not None:
        s['programme']['snapshot_revision'] = int(event['seq'])
    return s


def h_init(s, p, run, actor=''):
    if s['programme'].get('id'):
        raise ProgramError('ALREADY_INIT', 'programme already initialized')
    s['programme']['id'] = p.get('id') or f"PRG-{iso().replace('-', '').replace(':', '')[:15]}"
    s['programme']['outcome_statement'] = p.get('outcome_statement') or ''
    s['programme']['conservation_nouns'] = list(p.get('conservation_nouns') or [])
    ident = s['programme']['identity']
    ident['form'] = p.get('identity_form') or p.get('form') or 'pre_history'
    ident['project_id'] = p.get('project_id')
    ident['root_commit'] = p.get('root_commit')
    if p.get('debug_budget') is not None:
        s['programme']['debug_budget'] = int(p['debug_budget'])


def h_charter(s, p, run, actor=''):
    ch = s['programme']['charter']
    status = p.get('status') or 'accepted'
    if status not in {'accepted', 'auto', 'pending'}:
        raise ProgramError('CHARTER_STATUS', status)
    ch['status'] = status
    ch['by'] = p.get('by') or ('policy' if status == 'auto' else 'operator')
    ch['at'] = p.get('at') or iso()
    for k in ('workstreams', 'assumptions', 'inclusions', 'exclusions'):
        if k in p:
            ch[k] = p[k]
    if 'root_interpretation' in p:
        ch['root_interpretation'] = p['root_interpretation']


def h_prog_status(s, p, run, actor=''):
    st = p.get('status')
    if st not in {'active', 'suspended', 'complete'}:
        raise ProgramError('PROGRAMME_STATUS', str(st))
    if st == 'complete':
        roots = [i for i, n in s['nodes'].items() if not n.get('parent')]
        if not roots or any(effective_status(s, r) != 'complete' for r in roots):
            raise ProgramError('ROOT_NOT_DERIVED_COMPLETE', 'root is not derived-complete')
    s['programme']['status'] = st


def h_identity(s, p, run, actor=''):
    ident = s['programme']['identity']
    if p.get('form'):
        ident['form'] = p['form']
    if 'project_id' in p:
        ident['project_id'] = p['project_id']
    if 'root_commit' in p:
        ident['root_commit'] = p['root_commit']


def h_node_add(s, p, run, actor=''):
    nid = p.get('id') or next_id(s, 'node', 'N')
    if nid in s['nodes']:
        raise ProgramError('NODE_EXISTS', nid)
    parent = p.get('parent')
    if parent and parent not in s['nodes']:
        raise ProgramError('PARENT_UNKNOWN', str(parent))
    cls = p.get('class') or 'feature'
    if cls not in NODE_CLASSES:
        raise ProgramError('NODE_CLASS', cls)
    fp = p.get('fingerprint')
    if cls == 'observation' and fp:
        for oid, on in s['nodes'].items():
            if on.get('class') == 'observation' and on.get('fingerprint') == fp and on.get('status') == 'proposed':
                raise ProgramError('OBSERVATION_DUP', f'duplicate fingerprint {fp} on {oid}')
    risk = p.get('risk') or 'R1'
    policy = s['programme'].get('acceptance_policy') or {}
    acc = p.get('acceptance')
    if not acc:
        if cls in {'milestone', 'human'} or risk_rank(risk) >= 3 or parent is None:
            acc = 'operator'
        else:
            acc = policy.get('default', 'auto')
    resolved_facets = resolve_facets(
        class_=cls,
        title=p.get('title') or nid,
        facets=list(p.get('facets') or []),
        risk=risk,
        acceptance_criteria=list(p.get('acceptance_criteria') or []),
    )
    node = {
        'id': nid,
        'parent': parent,
        'title': p.get('title') or nid,
        'class': cls,
        'origin': p.get('origin') or 'decomposition',
        'status': p.get('status') or 'proposed',
        'stage': p.get('stage'),
        'revision': 0,
        'lease': None,
        'depends_on': list(p.get('depends_on') or []),
        'facets': resolved_facets,
        'risk': risk,
        'touches_existing': bool(p.get('touches_existing')),
        'acceptance': acc,
        'acceptance_state': 'not_required' if acc == 'auto' else 'pending',
        'acceptance_criteria': list(p.get('acceptance_criteria') or []),
        'baseline_ref': p.get('baseline_ref'),
        'parity_source': list(p.get('parity_source') or []),
        'parity_matrix': dict(p.get('parity_matrix') or {}),
        'parity_retire_decisions': dict(p.get('parity_retire_decisions') or {}),
        'quality': {},
        'verification': dict(p.get('verification') or {}),
        'evidence': list(p.get('evidence') or []),
        'blockers': [],
        'conservation_tags': list(p.get('conservation_tags') or []),
        'fingerprint': fp,
        'stage_note': None,
        'debug_iterations': 0,
        'split_into': None,
        'deferred': None,
        'rejected': None,
        'preservation': dict(p.get('preservation') or {}),
        'target_artifact_class': None,
        'design_artifact_class': p.get('design_artifact_class'),
    }
    rebuild_quality(node)
    materialize_artifact_classes(node)
    s['nodes'][nid] = node


def h_node_patch(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    allowed = {
        'title', 'facets', 'risk', 'depends_on', 'acceptance_criteria', 'touches_existing',
        'conservation_tags', 'parity_source', 'parity_matrix', 'parity_retire_decisions',
        'preservation', 'baseline_ref', 'class', 'acceptance', 'design_artifact_class',
    }
    for k, v in p.items():
        if k in allowed:
            node[k] = v
    if 'acceptance' in p and p['acceptance'] == 'auto':
        node['acceptance_state'] = 'not_required'
    if any(k in p for k in ('facets', 'class', 'title', 'risk', 'acceptance_criteria')):
        node['facets'] = resolve_facets(
            class_=node.get('class'),
            title=node.get('title'),
            facets=list(node.get('facets') or []),
            risk=node.get('risk'),
            acceptance_criteria=list(node.get('acceptance_criteria') or []),
        )
    rebuild_quality(node)
    materialize_artifact_classes(node)
    bump(node)


def h_lease_acquire(s, p, run, actor='', replay=False):
    nid = p.get('node')
    node = s['nodes'].get(nid)
    if not node:
        raise ProgramError('NODE_UNKNOWN', str(nid))
    if not replay and live_lease(node) and node['lease'].get('run') != run:
        raise ProgramError('LEASE_HELD', node['lease']['run'])
    ttl = int(p.get('ttl_seconds') or 1800)
    ts = p.get('acquired_at') or iso()
    exp = p.get('expires_at') or iso(now() + timedelta(seconds=ttl))
    node['lease'] = {
        'run': run, 'acquired_at': ts, 'heartbeat_at': p.get('heartbeat_at') or ts,
        'expires_at': exp,
    }
    if node['status'] in {'proposed', 'accepted', 'ready'}:
        node['status'] = 'in_progress'
        if not node.get('stage'):
            node['stage'] = 'discovery'
    bump(node)


def h_lease_heartbeat(s, p, run, actor='', replay=False):
    node = s['nodes'].get(p.get('node'))
    if not node:
        raise ProgramError('NODE_UNKNOWN', str(p.get('node')))
    if not node.get('lease') or node['lease'].get('run') != run:
        raise ProgramError('LEASE_NOT_OWNER', run)
    if not replay and not live_lease(node):
        raise ProgramError('LEASE_EXPIRED', 'cannot heartbeat an expired lease')
    ttl = int(p.get('ttl_seconds') or 1800)
    node['lease']['heartbeat_at'] = p.get('heartbeat_at') or iso()
    node['lease']['expires_at'] = p.get('expires_at') or iso(now() + timedelta(seconds=ttl))


def h_lease_release(s, p, run, actor='', replay=False):
    node = s['nodes'].get(p.get('node'))
    if not node:
        raise ProgramError('NODE_UNKNOWN', str(p.get('node')))
    if node.get('lease'):
        if replay:
            _lease_record_owner(node, run)
        elif live_lease(node) and node['lease'].get('run') != run:
            raise ProgramError('LEASE_NOT_OWNER', run)
    node['lease'] = None
    if p.get('stage_note'):
        node['stage_note'] = p['stage_note']
    bump(node)


def h_lease_reclaim(s, p, run, actor='', replay=False):
    node = s['nodes'].get(p.get('node'))
    if not node:
        raise ProgramError('NODE_UNKNOWN', str(p.get('node')))
    if not replay and live_lease(node):
        raise ProgramError('LEASE_HELD', node['lease']['run'])
    ttl = int(p.get('ttl_seconds') or 1800)
    ts = p.get('acquired_at') or iso()
    exp = p.get('expires_at') or iso(now() + timedelta(seconds=ttl))
    node['lease'] = {
        'run': run, 'acquired_at': ts, 'heartbeat_at': p.get('heartbeat_at') or ts,
        'expires_at': exp,
    }
    bump(node)


def h_stage(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    dest = p.get('to') or p.get('stage')
    if dest in {'null', ''}:
        dest = None
    if dest is not None and dest not in STAGE_ORDER:
        raise ProgramError('STAGE', str(dest))
    cur = node.get('stage')
    leaving_discovery = (cur in {None, 'discovery'} or dest not in {None, 'discovery'}) and dest not in {None, 'discovery'}
    if needs_baseline(node) and leaving_discovery:
        if not valid_baseline(s, node):
            raise ProgramError('BASELINE_REQUIRED', f'{node["id"]} needs an implementation baseline before leaving discovery')
    if node.get('class') == 'parity' and dest not in {None, 'discovery'}:
        src = node.get('parity_source') or []
        matrix = node.get('parity_matrix') or {}
        missing = [x for x in src if x not in matrix]
        if missing:
            raise ProgramError('PARITY_MATRIX', f'capabilities omitted: {missing}')
    if dest == 'implement' and node.get('class') in BROWNFIELD:
        bl = s['baselines'].get(node.get('baseline_ref') or '') or {}
        latent = bl.get('latent_capabilities') or []
        pres = dict(node.get('preservation') or {})
        pres.update(bl.get('preservation') or {})
        missing = [c for c in latent if c not in pres]
        if missing:
            raise ProgramError('LATENT_UNPRESERVED', f'latent capabilities lack preservation/retirement: {missing}')
    if dest == 'implement':
        stamp_implementation_boundary(node, run, actor)
    node['stage'] = dest
    if p.get('stage_note') is not None:
        node['stage_note'] = p.get('stage_note')
    if node['status'] in {'proposed', 'accepted', 'ready'}:
        node['status'] = 'in_progress'
    bump(node)


def h_status(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    dest = p.get('to') or p.get('status')
    if dest not in STATUSES:
        raise ProgramError('STATUS', str(dest))
    if dest == 'complete':
        if not is_leaf(s, node['id']):
            raise ProgramError('DERIVED_COMPLETE', 'non-leaf complete is derived; do not assert it')
        if not gates_ok(s, node['id']):
            # Replay must not reinterpret historical completes that predate
            # journeys or independent-review enforcement. verify/account flag
            # invalid gates on recorded-complete nodes instead.
            if not (
                replay
                and gates_ok(s, node['id'], check_journeys=False, check_independence=False)
            ):
                _ok, reason = quality_check(node)
                detail = reason if not _ok and reason else 'required dimensions/verification/acceptance incomplete'
                raise ProgramError('QUALITY_GATE', f'{node["id"]} {detail}')
    if dest == 'split':
        kids = p.get('split_into') or []
        if not kids:
            raise ProgramError('SPLIT_CHILDREN', 'split requires split_into')
        node['split_into'] = kids
    if dest == 'deferred':
        node['deferred'] = {'decision': p.get('decision'), 'note': p.get('note')}
    if dest == 'rejected':
        node['rejected'] = {'decision': p.get('decision'), 'note': p.get('note')}
    node['status'] = dest
    if dest in TERMINAL:
        node['lease'] = None
        node['stage'] = None
    bump(node)


def h_quality(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    dim = p.get('dim')
    if not dim:
        raise ProgramError('QUALITY_DIM', 'dim required')
    rec = node.setdefault('quality', {}).setdefault(
        dim, {'required': False, 'state': 'pending', 'evidence': None, 'rationale': None},
    )
    if 'state' in p:
        rec['state'] = p['state']
        stamp_pass_provenance(rec, p['state'], run, actor)
    if 'evidence' in p:
        rec['evidence'] = p['evidence']
    if 'rationale' in p:
        rec['rationale'] = p['rationale']
    if rec.get('state') == 'na' and not rec.get('rationale'):
        raise ProgramError('NA_RATIONALE', f'{dim} na requires rationale')
    materialize_artifact_classes(node)
    bump(node)


def h_verification(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    kind = p.get('kind')
    if kind not in {'referent', 'rendered', 'behavioral', 'journeys'}:
        raise ProgramError('VERIFY_KIND', str(kind))
    if kind == 'journeys':
        if p.get('required_ids') is not None:
            required = sorted({str(x) for x in (p.get('required_ids') or [])})
        else:
            catalog = s.get('journeys_catalog') or []
            required = required_journey_ids(
                catalog,
                node_class=node.get('class'),
                facets=node.get('facets'),
            )
            p['required_ids'] = required
        rec = node.setdefault('verification', {}).setdefault(
            'journeys',
            {'state': 'pending', 'required_ids': [], 'covered_ids': [], 'evidence': [], 'rationale': None},
        )
        rec['required_ids'] = required
        if 'state' in p:
            rec['state'] = p['state']
            stamp_pass_provenance(rec, p['state'], run, actor)
        if 'covered_ids' in p:
            rec['covered_ids'] = list(p['covered_ids'])
        if 'evidence' in p:
            rec['evidence'] = p['evidence']
        if 'rationale' in p:
            rec['rationale'] = p['rationale']
        if rec.get('state') == 'na' and not rec.get('rationale'):
            raise ProgramError('NA_RATIONALE', 'journeys na requires rationale')
        bump(node)
        return
    rec = node.setdefault('verification', {}).setdefault(kind, {})
    if 'state' in p:
        rec['state'] = p.get('state') or rec.get('state')
        stamp_pass_provenance(rec, rec.get('state'), run, actor)
    else:
        rec['state'] = p.get('state') or rec.get('state')
    rec['evidence'] = p.get('evidence', rec.get('evidence'))
    rec['path'] = p.get('path', rec.get('path'))
    if kind == 'rendered' and rec.get('state') in QUALITY_DONE:
        q = node.setdefault('quality', {}).setdefault(
            'rendered', {'required': 'ui' in (node.get('facets') or []), 'state': 'pending', 'evidence': None, 'rationale': None},
        )
        q['state'] = rec['state']
        q['evidence'] = rec.get('evidence')
        stamp_pass_provenance(q, rec['state'], run, actor)
    bump(node)


def h_blocker_open(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    bid = p.get('id') or next_id(s, 'blocker', 'BL')
    node['blockers'].append({
        'id': bid,
        'type': p.get('type') or 'decision',
        'ref': p.get('ref'),
        'opened': p.get('opened') or iso(),
        'note': p.get('note'),
    })
    node['status'] = 'blocked'
    if p.get('release_lease', True):
        node['lease'] = None
    bump(node)


def h_blocker_close(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    bid = p.get('id') or p.get('blocker')
    node['blockers'] = [b for b in node['blockers'] if b.get('id') != bid]
    if not node['blockers'] and node['status'] == 'blocked':
        node['status'] = 'ready'
    bump(node)


def h_node_baseline(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    ref = p.get('baseline_ref')
    if ref not in s['baselines']:
        raise ProgramError('BASELINE_UNKNOWN', str(ref))
    if s['baselines'][ref].get('provenance') == 'design-direction':
        raise ProgramError('BASELINE_PROVENANCE', 'design-direction artifacts cannot be implementation baselines')
    node['baseline_ref'] = ref
    if p.get('preservation'):
        node['preservation'] = dict(p['preservation'])
    bump(node)


def h_stage_note(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    node['stage_note'] = p.get('note') or p.get('stage_note')
    bump(node)


def h_debug(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    node['debug_iterations'] = int(node.get('debug_iterations') or 0) + int(p.get('n') or 1)
    budget = int(s['programme'].get('debug_budget') or 5)
    if node['debug_iterations'] > budget:
        raise ProgramError('DEBUG_BUDGET', f'debug iterations {node["debug_iterations"]} exceed budget {budget}')
    bump(node)


def h_accept(s, p, run, actor='', replay=False):
    node = mutable_node(s, p, run, replay=replay)
    node['acceptance_state'] = 'accepted'
    bump(node)


def h_decision_add(s, p, run, actor=''):
    did = p.get('id') or next_id(s, 'decision', 'D')
    scope = p.get('scope')
    if scope and scope not in s['nodes']:
        raise ProgramError('SCOPE_UNKNOWN', str(scope))
    s['decisions'][did] = {
        'id': did,
        'scope': scope,
        'statement': p.get('statement') or '',
        'origin': p.get('origin') or 'operator',
        'status': p.get('status') or 'proposed',
        'supersedes': p.get('supersedes'),
    }


def h_decision_status(s, p, run, actor=''):
    did = p.get('id') or p.get('decision')
    if did not in s['decisions']:
        raise ProgramError('DECISION_UNKNOWN', str(did))
    st = p.get('status')
    if st not in {'proposed', 'accepted', 'superseded'}:
        raise ProgramError('DECISION_STATUS', str(st))
    s['decisions'][did]['status'] = st


def h_evidence_add(s, p, run, actor=''):
    eid = p.get('id') or next_id(s, 'evidence', 'EV')
    s['evidence'][eid] = {
        'id': eid,
        'provenance': p.get('provenance') or 'implementation-observation',
        'path': p.get('path'),
        'tree_hash': p.get('tree_hash'),
        'note': p.get('note'),
    }


def h_baseline_add(s, p, run, actor=''):
    bid = p.get('id') or next_id(s, 'baseline', 'BLN')
    s['baselines'][bid] = {
        'id': bid,
        'provenance': p.get('provenance') or 'implementation-observation',
        'tree_hash': p.get('tree_hash'),
        'latent_capabilities': list(p.get('latent_capabilities') or []),
        'preservation': dict(p.get('preservation') or {}),
        'path': p.get('path'),
        'observed_behavior': p.get('observed_behavior'),
    }


def frontier(state: dict) -> list[str]:
    out = []
    for nid, node in state['nodes'].items():
        if not is_leaf(state, nid):
            continue
        if node['status'] not in {'ready', 'accepted', 'proposed'}:
            continue
        if node['status'] == 'proposed' and state['programme']['charter'].get('status') not in {'accepted', 'auto'}:
            continue
        if node.get('blockers'):
            continue
        deps = node.get('depends_on') or []
        if any(effective_status(state, d) not in TERMINAL for d in deps if d in state['nodes']):
            continue
        anc = node.get('parent')
        blocked_anc = False
        while anc:
            an = state['nodes'][anc]
            if an.get('status') == 'blocked' or an.get('blockers'):
                blocked_anc = True
                break
            anc = an.get('parent')
        if blocked_anc:
            continue
        if live_lease(node):
            continue
        out.append(nid)

    def sort_key(nid):
        n = state['nodes'][nid]
        depth = 0
        parent = n.get('parent')
        while parent:
            depth += 1
            parent = state['nodes'][parent].get('parent')
        return (depth, -risk_rank(n.get('risk', 'R0')), nid)
    return sorted(out, key=sort_key)


def conservation_gaps(state: dict) -> list[str]:
    nouns = [x.lower() for x in (state['programme'].get('conservation_nouns') or [])]
    blob = []
    for n in state['nodes'].values():
        blob.append(n.get('title') or '')
        blob.extend(n.get('conservation_tags') or [])
        blob.extend(n.get('acceptance_criteria') or [])
        blob.append(n.get('class') or '')
    text = ' '.join(blob).lower()
    return [n for n in nouns if n not in text]


def completion_account(state: dict) -> dict:
    rows = []
    for nid, n in sorted(state['nodes'].items()):
        rows.append({
            'id': nid,
            'title': n.get('title'),
            'class': n.get('class'),
            'recorded_status': n.get('status'),
            'effective_status': effective_status(state, nid),
            'leaf': is_leaf(state, nid),
            'gates_valid': gates_ok(state, nid),
            'independence_issues': independence_issues(n),
        })
    roots = [i for i, n in state['nodes'].items() if not n.get('parent')]
    return {
        'roots': {r: effective_status(state, r) for r in roots},
        'nodes': rows,
        'conservation_gaps': conservation_gaps(state),
        'open_decisions': [d['id'] for d in state['decisions'].values() if d.get('status') == 'proposed'],
    }


def log_sha256(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def dump_snapshot(state: dict) -> str:
    snap = {k: v for k, v in state.items() if k != 'journeys_catalog'}
    return yaml.safe_dump(snap, sort_keys=False, allow_unicode=True, width=120)


def load_snapshot(text: str) -> dict:
    return yaml.safe_load(text) or empty_state()


# Call-site aliases (handlers and CLI use one vocabulary).
ProgramError = ProgramError
iso = iso
next_id = next_id
NODE_CLASSES = NODE_CLASSES
risk_rank = risk_rank
live_lease = live_lease
live_lease = live_lease
needs_baseline = needs_baseline
valid_baseline = valid_baseline
BROWNFIELD = BROWNFIELD
STATUSES = STATUSES
is_leaf = is_leaf
gates_ok = gates_ok
TERMINAL = TERMINAL
QUALITY_DONE = QUALITY_DONE
apply_event = apply_event
effective_status = effective_status
is_leaf = is_leaf
is_terminal = is_terminal
frontier = frontier
conservation_gaps = conservation_gaps
completion_account = completion_account
dump_snapshot = dump_snapshot
load_snapshot = load_snapshot
quality_ok = quality_ok
quality_check = quality_check
gates_valid = gates_valid
rebuild_quality = rebuild_quality
