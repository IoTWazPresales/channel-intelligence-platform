"""CLI for the EIF programme mutation interface (host: .eif/runtime/programme/program.py)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from eif_program.engine import (  # noqa: E402
    ProgramError, completion_account, conservation_gaps, frontier, gates_ok, live_lease,
)
from eif_program.store import ProgramStore  # noqa: E402
from eif_program.views import write_views  # noqa: E402


def die(e: ProgramError):
    print(f'ERROR {e.code}: {e}', file=sys.stderr)
    return 2


def store_from(args) -> ProgramStore:
    return ProgramStore(Path(args.project), run=args.run or '')


def cmd_init(args):
    st = store_from(args)
    if st.exists() and not args.force:
        raise ProgramError('ALREADY_EXISTS', str(st.dir))
    nouns = [x.strip() for x in (args.nouns or '').split(',') if x.strip()]
    state = st.append('programme.init', {
        'outcome_statement': args.outcome,
        'conservation_nouns': nouns,
        'identity_form': args.identity_form,
        'project_id': getattr(args, 'project_id', None),
        'debug_budget': args.debug_budget,
    }, actor=args.actor)
    if args.charter in {'accepted', 'auto'}:
        state = st.append('programme.charter', {
            'status': args.charter,
            'workstreams': [x.strip() for x in (args.workstreams or '').split(',') if x.strip()],
            'root_interpretation': args.interpretation,
        }, actor=args.actor)
    write_views(st.project, state)
    print(state['programme']['id'], 'rev', state['programme']['snapshot_revision'])
    return 0


def cmd_add_node(args):
    st = store_from(args)
    payload = {
        'id': args.id,
        'parent': args.parent,
        'title': args.title,
        'class': args.klass,
        'origin': args.origin,
        'status': args.status,
        'facets': [x.strip() for x in (args.facets or '').split(',') if x.strip()],
        'risk': args.risk,
        'touches_existing': args.touches_existing,
        'depends_on': [x.strip() for x in (args.depends_on or '').split(',') if x.strip()],
        'acceptance_criteria': [x.strip() for x in (args.criteria or '').split(';') if x.strip()],
        'conservation_tags': [x.strip() for x in (args.tags or '').split(',') if x.strip()],
        'parity_source': [x.strip() for x in (args.parity_source or '').split(',') if x.strip()],
        'fingerprint': args.fingerprint,
        'acceptance': args.acceptance,
    }
    state = st.append('node.add', payload, actor=args.actor)
    write_views(st.project, state)
    nid = payload['id'] or max(state['nodes'])
    print(nid, 'rev', state['nodes'][nid if nid in state['nodes'] else list(state['nodes'])[-1]]['revision'])
    return 0


def cmd_event(args):
    st = store_from(args)
    payload = json.loads(args.payload) if args.payload else {}
    state = st.append(args.type, payload, actor=args.actor)
    write_views(st.project, state)
    print('rev', state['programme']['snapshot_revision'])
    return 0


def cmd_frontier(args):
    st = store_from(args)
    state = st.load()
    for nid in frontier(state):
        n = state['nodes'][nid]
        print(f"{nid}\t{n.get('class')}\t{n.get('risk')}\t{n.get('title')}")
    return 0


def cmd_status(args):
    st = store_from(args)
    state = st.load()
    p = state['programme']
    print(f"id={p.get('id')} status={p.get('status')} charter={p['charter'].get('status')} rev={p.get('snapshot_revision')}")
    acc = completion_account(state)
    print('roots', json.dumps(acc['roots']))
    print('conservation_gaps', ','.join(acc['conservation_gaps']) or '-')
    print('frontier', ','.join(frontier(state)) or '-')
    if args.node:
        n = state['nodes'][args.node]
        print(json.dumps(n, indent=2, default=str))
    return 0


def cmd_views(args):
    st = store_from(args)
    write_views(st.project, st.load())
    print('views written under', st.project / '.eif')
    return 0


def cmd_rebuild(args):
    st = store_from(args)
    state = st.rebuild()
    write_views(st.project, state)
    print('rebuilt rev', state['programme']['snapshot_revision'])
    return 0


def cmd_verify(args):
    st = store_from(args)
    result = st.verify()
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 2


def cmd_account(args):
    st = store_from(args)
    print(json.dumps(completion_account(st.load()), indent=2))
    return 0


def cmd_nouns(args):
    st = store_from(args)
    gaps = conservation_gaps(st.load())
    print(json.dumps(gaps))
    return 0 if not gaps else 2


def cmd_health(args):
    st = store_from(args)
    if not st.exists():
        print('mode task')
        print('integrity n/a')
        return 0
    integrity = st.verify()
    state = st.load()
    acc = completion_account(state)
    expired = [nid for nid, n in state['nodes'].items() if n.get('lease') and not live_lease(n)]
    print('mode programme')
    print('integrity', 'ok' if integrity.get('ok') else 'FAIL')
    if integrity.get('issues'):
        print('integrity_issues', '; '.join(integrity['issues']))
    print('open_decisions', len(acc.get('open_decisions') or acc.get('open_decisions') or []))
    print('conservation_gaps', acc.get('conservation_gaps') or acc.get('conservation_gaps'))
    print('frontier', frontier(state))
    print('expired_leases', expired or '-')
    return 0 if integrity.get('ok') else 2


def cmd_task_check(args):
    """Task mode: quality engine without a programme directory."""
    from eif_program.engine import rebuild_quality, quality_check
    from eif_program.design_artifacts import materialize_artifact_classes
    from eif_program.facets import resolve_facets
    criteria = [x.strip() for x in (args.criteria or '').split(';') if x.strip()]
    facets = resolve_facets(
        class_=args.klass or 'feature',
        title=args.title or '',
        facets=[x.strip() for x in (args.facets or '').split(',') if x.strip()],
        risk=args.risk or 'R1',
        acceptance_criteria=criteria,
    )
    node = {
        'id': 'TASK',
        'class': args.klass or 'feature',
        'title': args.title or 'TASK',
        'facets': facets,
        'risk': args.risk or 'R1',
        'quality': {},
        'verification': {},
        'acceptance': 'auto',
        'acceptance_state': 'not_required',
        'acceptance_criteria': criteria,
        'design_artifact_class': args.design_artifact_class or None,
        'target_artifact_class': None,
    }
    rebuild_quality(node)
    materialize_artifact_classes(node)
    # optional resolutions: dim=state:rationale  OR dim=state:rationale with evidence via dim=state:rationale@json
    for spec in args.resolve or []:
        dim, _, rest = spec.partition('=')
        state_s, _, rationale = rest.partition(':')
        rec = node['quality'].setdefault(dim, {'required': True, 'state': 'pending', 'evidence': None, 'rationale': None})
        rec['state'] = state_s or 'pass'
        rec['rationale'] = rationale or None
    ok, reason = quality_check(node)
    print(json.dumps({
        'facets': facets,
        'quality': node['quality'],
        'target_artifact_class': node.get('target_artifact_class'),
        'design_artifact_class': node.get('design_artifact_class'),
        'ok': ok,
        'reason': reason,
    }, indent=2, default=str))
    return 0 if ok else 2


def cmd_journeys(args):
    from eif_program.journeys import find_journeys_file, load_journeys, select_journeys, validate_journeys_doc
    import yaml
    project = Path(args.project)
    path = Path(args.file) if args.file else find_journeys_file(project)
    if not path or not path.exists():
        print(json.dumps({'journeys': [], 'selected': [], 'path': None}))
        return 0
    if args.validate_only:
        data = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        errors = validate_journeys_doc(data)
        print(json.dumps({'path': str(path), 'ok': not errors, 'errors': errors}, indent=2))
        return 0 if not errors else 2
    journeys = load_journeys(path)
    facets = [x.strip() for x in (args.facets or '').split(',') if x.strip()]
    selected = select_journeys(
        journeys,
        node_class=args.klass,
        facets=facets,
        criticality=args.criticality or None,
    )
    print(json.dumps({
        'path': str(path),
        'journeys': [{'id': j.get('id'), 'name': j.get('name')} for j in journeys],
        'selected': selected,
    }, indent=2, default=str))
    return 0


def build_parser():
    p = argparse.ArgumentParser(prog='program.py')
    p.add_argument('--project', default='.')
    p.add_argument('--run', default='')
    p.add_argument('--actor', default='gov-001')
    sp = p.add_subparsers(dest='cmd', required=True)

    s = sp.add_parser('init')
    s.add_argument('--outcome', required=True)
    s.add_argument('--nouns', default='')
    s.add_argument('--identity-form', default='pre_history')
    s.add_argument('--project-id', default='')
    s.add_argument('--debug-budget', type=int, default=5)
    s.add_argument('--charter', choices=['pending', 'accepted', 'auto'], default='pending')
    s.add_argument('--workstreams', default='')
    s.add_argument('--interpretation', default='')
    s.add_argument('--force', action='store_true')
    s.set_defaults(func=cmd_init)

    s = sp.add_parser('add-node')
    s.add_argument('--title', required=True)
    s.add_argument('--class', dest='klass', default='feature')
    s.add_argument('--parent', default=None)
    s.add_argument('--id', default=None)
    s.add_argument('--origin', default='decomposition')
    s.add_argument('--status', default='proposed')
    s.add_argument('--facets', default='')
    s.add_argument('--risk', default='R1')
    s.add_argument('--touches-existing', action='store_true')
    s.add_argument('--depends-on', default='')
    s.add_argument('--criteria', default='')
    s.add_argument('--tags', default='')
    s.add_argument('--parity-source', default='')
    s.add_argument('--fingerprint', default=None)
    s.add_argument('--acceptance', default=None)
    s.set_defaults(func=cmd_add_node)

    s = sp.add_parser('event')
    s.add_argument('type')
    s.add_argument('--payload', default='{}')
    s.set_defaults(func=cmd_event)

    for name, fn in [
        ('frontier', cmd_frontier), ('status', cmd_status), ('views', cmd_views),
        ('rebuild', cmd_rebuild), ('verify', cmd_verify), ('account', cmd_account),
        ('nouns', cmd_nouns), ('health', cmd_health),
    ]:
        s = sp.add_parser(name)
        if name == 'status':
            s.add_argument('--node')
        s.set_defaults(func=fn)

    s = sp.add_parser('task-check')
    s.add_argument('--facets', default='')
    s.add_argument('--title', default='')
    s.add_argument('--risk', default='R1')
    s.add_argument('--class', dest='klass', default='feature')
    s.add_argument('--resolve', action='append', default=[])
    s.add_argument('--criteria', default='')
    s.add_argument('--design-artifact-class', default='')
    s.set_defaults(func=cmd_task_check)

    s = sp.add_parser('journeys')
    s.add_argument('--file', default='')
    s.add_argument('--class', dest='klass', default='')
    s.add_argument('--facets', default='')
    s.add_argument('--criticality', default='')
    s.add_argument('--validate-only', action='store_true')
    s.set_defaults(func=cmd_journeys)

    s = sp.add_parser('migrate')
    s.set_defaults(func=cmd_migrate)
    return p


def cmd_migrate(args):
    from eif_program.migrate import migrate
    st = store_from(args)
    state = migrate(st)
    write_views(st.project, state)
    print('migrated', state['programme']['id'], 'nodes', len(state['nodes']))
    return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    project = Path(args.project).resolve()
    from eif_program.runtime_paths import manifest_path  # noqa: WPS433
    if manifest_path(project).is_file():
        from eif_program.runtime_integrity import verify_runtime  # noqa: WPS433
        ok, msg = verify_runtime(project)
        if not ok:
            print(f'ERROR RUNTIME_INTEGRITY: {msg}', file=sys.stderr)
            return 2
    try:
        return args.func(args)
    except ProgramError as e:
        return die(e)


if __name__ == '__main__':
    raise SystemExit(main())
