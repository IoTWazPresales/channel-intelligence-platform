"""Design artifact classes and evidence-kind gates for design_experience nodes.

Deterministic checks cover process and evidence presence, not aesthetic quality.
Target class is declared as a structured acceptance-criterion line, never inferred
from free-text high-fidelity phrasing.
"""
from __future__ import annotations

import re
from typing import Any

ARTIFACT_CLASSES = ('ia_concept', 'interaction', 'high_fidelity')
CLASS_RANK = {name: i for i, name in enumerate(ARTIFACT_CLASSES)}

TARGET_LINE = re.compile(
    r'^target_artifact_class:\s*(ia_concept|interaction|high_fidelity)\s*$',
    re.I,
)
CLASS_NA = re.compile(
    r'artifact_class\s*=\s*(ia_concept|interaction|high_fidelity)',
    re.I,
)

DIM_ARTIFACT_CLASS = 'design_artifact_class'
DIM_INTERACTION = 'design_interaction_spec'
DIM_STATES = 'design_state_coverage'
DIM_IDENTITY = 'design_identity_tokens'
DIM_EXECUTION = 'design_execution_decisions'
DIM_RENDERED_CMP = 'rendered_comparison'
DIM_SAMENESS = 'design_sameness_review'

# Dimensions that exist only to certify higher-fidelity execution.
HF_ONLY_DIMS = frozenset({DIM_IDENTITY})
INTERACTION_PLUS_DIMS = frozenset({DIM_INTERACTION, DIM_STATES})
CLASS_SKIPPABLE = HF_ONLY_DIMS | INTERACTION_PLUS_DIMS | frozenset({DIM_EXECUTION})

EXECUTION_SLOTS = (
    'responsive_decision',
    'visualisation_decision',
    'consequential_action_decision',
)

QUALITY_DONE = frozenset({'pass', 'resolved', 'na'})
PASS_STATES = frozenset({'pass', 'resolved'})


def parse_target_artifact_class(acceptance_criteria) -> tuple[str | None, str | None]:
    """Return (target, error). Missing target is (None, None), not an error here."""
    found: list[str] = []
    for raw in acceptance_criteria or []:
        m = TARGET_LINE.match(str(raw).strip())
        if m:
            found.append(m.group(1).lower())
    if not found:
        return None, None
    uniq = sorted(set(found))
    if len(uniq) > 1:
        return None, 'conflicting target_artifact_class declarations'
    return uniq[0], None


def class_from_evidence(evidence: Any) -> str | None:
    if isinstance(evidence, str):
        val = evidence.strip().lower()
        return val if val in CLASS_RANK else None
    if isinstance(evidence, dict):
        for key in ('class', 'artifact_class', 'fidelity'):
            val = str(evidence.get(key) or '').strip().lower()
            if val in CLASS_RANK:
                return val
    return None


def materialize_artifact_classes(node: dict) -> None:
    """Persist per-node target from acceptance criteria; delivered from field or quality evidence."""
    target, _err = parse_target_artifact_class(node.get('acceptance_criteria'))
    node['target_artifact_class'] = target
    rec = (node.get('quality') or {}).get(DIM_ARTIFACT_CLASS) or {}
    from_ev = class_from_evidence(rec.get('evidence'))
    delivered = str(node.get('design_artifact_class') or '').strip().lower() or None
    if delivered and delivered not in CLASS_RANK:
        delivered = None
    if not delivered and from_ev:
        node['design_artifact_class'] = from_ev
    elif delivered:
        node['design_artifact_class'] = delivered


def _dim(node: dict, name: str) -> dict:
    return (node.get('quality') or {}).get(name) or {}


def _state(node: dict, name: str) -> str | None:
    return _dim(node, name).get('state')


def _rationale(node: dict, name: str) -> str:
    return str(_dim(node, name).get('rationale') or '')


def _na_class(node: dict, name: str) -> str | None:
    m = CLASS_NA.search(_rationale(node, name))
    return m.group(1).lower() if m else None


def _skippable_na_ok(node: dict, name: str, delivered: str) -> str | None:
    if _state(node, name) != 'na':
        return None
    declared = _na_class(node, name)
    if declared != delivered:
        return (
            f'{name} na on {delivered} requires rationale containing '
            f'artifact_class={delivered}'
        )
    return None


def _require_nonempty_evidence(node: dict, name: str) -> str | None:
    rec = _dim(node, name)
    if rec.get('state') not in PASS_STATES:
        return f'{name} must be pass or resolved'
    ev = rec.get('evidence')
    if ev in (None, '', [], {}):
        return f'{name} requires evidence'
    if isinstance(ev, str) and not ev.strip():
        return f'{name} requires evidence'
    return None


def _hf_identity_ok(node: dict) -> str | None:
    err = _require_nonempty_evidence(node, DIM_IDENTITY)
    if err:
        return err
    ev = _dim(node, DIM_IDENTITY).get('evidence')
    tokens = ev.get('tokens') if isinstance(ev, dict) else None
    if not isinstance(tokens, dict) or not tokens.get('direction_name'):
        return 'design_identity_tokens evidence.tokens.direction_name must be declared'
    return None


def _hf_states_ok(node: dict) -> str | None:
    err = _require_nonempty_evidence(node, DIM_STATES)
    if err:
        return err
    ev = _dim(node, DIM_STATES).get('evidence')
    states = ev.get('states') if isinstance(ev, dict) else ev
    if not isinstance(states, list) or not [s for s in states if str(s).strip()]:
        return 'design_state_coverage evidence must enumerate states'
    return None


def _hf_interaction_ok(node: dict) -> str | None:
    return _require_nonempty_evidence(node, DIM_INTERACTION)


def _hf_execution_ok(node: dict) -> str | None:
    rec = _dim(node, DIM_EXECUTION)
    if rec.get('state') == 'na':
        return 'design_execution_decisions cannot be na on high_fidelity'
    if rec.get('state') not in PASS_STATES:
        return 'design_execution_decisions must be pass or resolved on high_fidelity'
    ev = rec.get('evidence')
    if not isinstance(ev, dict):
        return 'design_execution_decisions evidence must be a structured map of decisions'
    for slot in EXECUTION_SLOTS:
        item = ev.get(slot)
        if not isinstance(item, dict):
            return f'design_execution_decisions missing {slot}'
        status = str(item.get('status') or '').strip().lower()
        if status not in {'applicable', 'not_applicable'}:
            return f'{slot} status must be applicable or not_applicable'
        if status == 'not_applicable' and not str(item.get('rationale') or '').strip():
            return f'{slot} not_applicable requires rationale'
        if status == 'applicable' and not str(item.get('rationale') or item.get('evidence') or '').strip():
            return f'{slot} applicable requires rationale or evidence'
    return None


def _hf_rendered_comparison_ok(node: dict) -> str | None:
    if _state(node, DIM_RENDERED_CMP) not in PASS_STATES:
        return None  # ordinary quality_ok handles pending/na
    ev_class = class_from_evidence(_dim(node, DIM_RENDERED_CMP).get('evidence'))
    if ev_class != 'high_fidelity':
        return 'high_fidelity rendered_comparison evidence must declare artifact_class high_fidelity'
    return None


def _hf_sameness_ok(node: dict) -> str | None:
    if _state(node, DIM_SAMENESS) not in PASS_STATES:
        return None
    ev = _dim(node, DIM_SAMENESS).get('evidence')
    challenge = ev.get('visual_vocabulary_challenge') if isinstance(ev, dict) else None
    if not (isinstance(challenge, str) and challenge.strip()) and not (
        isinstance(challenge, dict) and challenge
    ):
        return 'high_fidelity design_sameness_review must include visual_vocabulary_challenge'
    return None


def design_experience_ok(node: dict) -> tuple[bool, str | None]:
    """True when design_experience process/evidence requirements are satisfied or inapplicable."""
    if 'design_experience' not in (node.get('facets') or []):
        return True, None

    materialize_artifact_classes(node)
    target, terr = parse_target_artifact_class(node.get('acceptance_criteria'))
    if terr:
        return False, terr
    if not target:
        return False, 'missing target_artifact_class'
    stored_target = str(node.get('target_artifact_class') or '').strip().lower() or None
    if stored_target and stored_target != target:
        return False, 'target_artifact_class field disagrees with acceptance_criteria'

    delivered = str(node.get('design_artifact_class') or '').strip().lower() or None
    if not delivered:
        return False, 'missing design_artifact_class'
    if delivered not in CLASS_RANK:
        return False, f'invalid design_artifact_class {delivered}'
    if target not in CLASS_RANK:
        return False, f'invalid target_artifact_class {target}'
    if CLASS_RANK[delivered] < CLASS_RANK[target]:
        return False, (
            f'delivered design_artifact_class {delivered} does not satisfy '
            f'target_artifact_class {target}'
        )

    if _state(node, DIM_ARTIFACT_CLASS) == 'na':
        return False, 'design_artifact_class cannot be na'
    ev_class = class_from_evidence(_dim(node, DIM_ARTIFACT_CLASS).get('evidence'))
    if ev_class and ev_class != delivered:
        return False, 'design_artifact_class evidence disagrees with delivered class'

    if delivered == 'ia_concept':
        for dim in HF_ONLY_DIMS:
            if _state(node, dim) in PASS_STATES:
                return False, f'{dim} cannot pass on ia_concept'
        for dim in CLASS_SKIPPABLE:
            err = _skippable_na_ok(node, dim, delivered)
            if err:
                return False, err
        cmp_class = class_from_evidence(_dim(node, DIM_RENDERED_CMP).get('evidence'))
        if cmp_class == 'high_fidelity':
            return False, 'ia_concept cannot pass high_fidelity rendered_comparison'

    elif delivered == 'interaction':
        for dim in INTERACTION_PLUS_DIMS:
            if _state(node, dim) == 'na':
                return False, f'{dim} cannot be na on interaction'
            err = _require_nonempty_evidence(node, dim)
            if err:
                return False, err
        for dim in HF_ONLY_DIMS | frozenset({DIM_EXECUTION}):
            if _state(node, dim) in PASS_STATES:
                # Over-delivering HF evidence on an interaction node is allowed
                # only if the evidence kinds themselves are well-formed; identity
                # pass is permitted as extra evidence, not as HF completion.
                continue
            err = _skippable_na_ok(node, dim, delivered)
            if err:
                return False, err
        if _state(node, DIM_STATES) in PASS_STATES:
            err = _hf_states_ok(node)
            if err:
                return False, err
        if _state(node, DIM_INTERACTION) in PASS_STATES:
            err = _hf_interaction_ok(node)
            if err:
                return False, err

    elif delivered == 'high_fidelity':
        for dim in (DIM_ARTIFACT_CLASS,) + tuple(HF_ONLY_DIMS) + tuple(INTERACTION_PLUS_DIMS):
            if _state(node, dim) == 'na':
                return False, f'{dim} cannot be na on high_fidelity'
        err = _hf_identity_ok(node)
        if err:
            return False, err
        err = _hf_states_ok(node)
        if err:
            return False, err
        err = _hf_interaction_ok(node)
        if err:
            return False, err
        err = _hf_execution_ok(node)
        if err:
            return False, err
        err = _hf_rendered_comparison_ok(node)
        if err:
            return False, err
        err = _hf_sameness_ok(node)
        if err:
            return False, err

    return True, None
