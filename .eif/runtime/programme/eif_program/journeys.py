"""Load, validate and select declared user journeys from JOURNEYS.yaml."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import ProgramError

# id, name, and non-empty steps are required. success_criteria is optional so a
# project valid under published v0.5.1 stays valid; when present it must be a
# non-empty list. Loaders must not rewrite host journey files to add it.
REQUIRED_JOURNEY_KEYS = ('id', 'name', 'steps')


def find_journeys_file(project: Path) -> Path | None:
    project = Path(project).resolve()
    for base in (project / '.eif', project):
        for name in ('JOURNEYS.yaml', 'journeys.yaml'):
            p = base / name
            if p.is_file():
                return p
    return None


def validate_journey(j: dict[str, Any], *, index: int | None = None) -> list[str]:
    label = f'journey[{index}]' if index is not None else f'journey {j.get("id")!r}'
    errors: list[str] = []
    for key in REQUIRED_JOURNEY_KEYS:
        if not j.get(key):
            errors.append(f'{label}: missing required field {key!r}')
    steps = j.get('steps')
    if steps is not None and (not isinstance(steps, list) or not steps):
        errors.append(f'{label}: steps must be a non-empty list')
    crit = j.get('success_criteria')
    if crit is not None and (not isinstance(crit, list) or not crit):
        errors.append(f'{label}: success_criteria must be a non-empty list')
    req_for = j.get('required_for')
    if req_for is not None and not isinstance(req_for, list):
        errors.append(f'{label}: required_for must be a list when present')
    req_facets = j.get('facets')
    if req_facets is not None and not isinstance(req_facets, list):
        errors.append(f'{label}: facets must be a list when present')
    return errors


def validate_journeys_doc(data: dict[str, Any] | None) -> list[str]:
    if not isinstance(data, dict):
        return ['journeys document must be a mapping']
    journeys = data.get('journeys')
    if journeys is None:
        return ['journeys: top-level journeys list is required']
    if not isinstance(journeys, list):
        return ['journeys: must be a list']
    errors: list[str] = []
    seen: set[str] = set()
    for i, j in enumerate(journeys):
        if not isinstance(j, dict):
            errors.append(f'journey[{i}]: must be a mapping')
            continue
        errors.extend(validate_journey(j, index=i))
        jid = j.get('id')
        if jid:
            if jid in seen:
                errors.append(f'journey[{i}]: duplicate id {jid!r}')
            seen.add(str(jid))
    return errors


def load_journeys(path: Path) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding='utf-8')
    data = yaml.safe_load(text) or {}
    errors = validate_journeys_doc(data)
    if errors:
        raise ProgramError('JOURNEYS_INVALID', '; '.join(errors))
    return list(data.get('journeys') or [])


def load_project_journeys(project: Path) -> list[dict[str, Any]]:
    path = find_journeys_file(project)
    if not path:
        return []
    return load_journeys(path)


def select_journeys(
    journeys: list[dict[str, Any]],
    *,
    node_class: str | None = None,
    facets: list[str] | None = None,
    criticality: str | None = None,
) -> list[dict[str, Any]]:
    """Return journeys whose required_for / facets / criticality match the node context."""
    cls = node_class or ''
    facet_set = set(facets or [])
    out: list[dict[str, Any]] = []
    for j in journeys:
        req_for = j.get('required_for') or []
        if req_for and cls not in req_for:
            continue
        req_facets = j.get('facets') or []
        if req_facets and not set(req_facets).issubset(facet_set):
            continue
        jc = j.get('criticality')
        if criticality and jc and criticality != jc:
            continue
        out.append(j)
    return out


def select_journeys_for_node(node: dict[str, Any], project: Path) -> list[dict[str, Any]]:
    journeys = load_project_journeys(project)
    return select_journeys(
        journeys,
        node_class=node.get('class'),
        facets=node.get('facets'),
    )


QUALITY_DONE = frozenset({'pass', 'resolved', 'na'})


def required_journey_ids(
    journeys: list[dict[str, Any]],
    *,
    node_class: str | None = None,
    facets: list[str] | None = None,
    criticality: str | None = None,
) -> list[str]:
    """Return sorted journey ids from the selector — the authoritative required set."""
    selected = select_journeys(
        journeys,
        node_class=node_class,
        facets=facets,
        criticality=criticality,
    )
    return sorted({str(j['id']) for j in selected if j.get('id')})


def frozen_required_journey_ids(
    node: dict[str, Any],
    journeys: list[dict[str, Any]] | None,
) -> list[str]:
    """Historical required set from verification evidence, or current catalogue when unset."""
    jrec = (node.get('verification') or {}).get('journeys') or {}
    frozen = jrec.get('required_ids')
    if frozen is not None:
        return sorted({str(x) for x in frozen})
    return required_journey_ids(
        journeys or [],
        node_class=node.get('class'),
        facets=node.get('facets'),
    )


def journeys_gate_ok(node: dict[str, Any], journeys: list[dict[str, Any]] | None) -> bool:
    """True when no journeys apply, or journey verification accounts for every required id."""
    required = set(frozen_required_journey_ids(node, journeys))
    if not required:
        return True
    jrec = (node.get('verification') or {}).get('journeys') or {}
    st = jrec.get('state')
    if st not in QUALITY_DONE:
        return False
    if st == 'na':
        return bool(jrec.get('rationale'))
    covered = {str(x) for x in (jrec.get('covered_ids') or [])}
    return required.issubset(covered)


def journey_verification_issues(
    state: dict[str, Any],
    *,
    snapshot: dict[str, Any] | None = None,
) -> list[str]:
    """Detect journey evidence drift between replay state and optional snapshot."""
    issues: list[str] = []
    for nid, node in sorted((state.get('nodes') or {}).items()):
        jrec = (node.get('verification') or {}).get('journeys') or {}
        if not jrec:
            continue
        req = {str(x) for x in (jrec.get('required_ids') or [])}
        st = jrec.get('state')
        if st in {'pass', 'resolved'} and req:
            covered = {str(x) for x in (jrec.get('covered_ids') or [])}
            if not req.issubset(covered):
                issues.append(
                    f'{nid}: journey covered_ids {sorted(covered)} '
                    f'does not cover frozen required_ids {sorted(req)}'
                )
        if snapshot is not None:
            snap_node = (snapshot.get('nodes') or {}).get(nid) or {}
            snap_j = (snap_node.get('verification') or {}).get('journeys') or {}
            for key in ('state', 'required_ids', 'covered_ids', 'rationale'):
                if jrec.get(key) != snap_j.get(key):
                    issues.append(f'{nid}: snapshot journey {key!r} drift from log replay')
    return issues
