"""Executable independence invariants for programme quality and verification gates.

Independence is derived from event provenance (run + actor), never from
self-declared payload flags such as ``independent: true``.
"""
from __future__ import annotations

from .design_artifacts import DIM_RENDERED_CMP, DIM_SAMENESS

INDEPENDENT_QUALITY_DIMS = frozenset({
    DIM_RENDERED_CMP,
    DIM_SAMENESS,
})

QUALITY_DONE = frozenset({'pass', 'resolved', 'na'})
PASS_STATES = frozenset({'pass', 'resolved'})


def quality_dim_requires_independence(node: dict, dim: str) -> bool:
    if dim not in INDEPENDENT_QUALITY_DIMS:
        return False
    return 'design_experience' in (node.get('facets') or [])


def verification_requires_independence(node: dict, kind: str) -> bool:
    risk = str(node.get('risk') or 'R0').upper()
    rank = int(risk.replace('R', '') or 0)
    facets = node.get('facets') or []
    if kind == 'referent':
        return rank >= 2
    if kind == 'rendered':
        if 'design_experience' in facets:
            return True
        return rank >= 3
    return False


def implementation_provenance_required(node: dict) -> bool:
    """True when any independence-required gate has a completed pass state."""
    for dim, rec in (node.get('quality') or {}).items():
        if not quality_dim_requires_independence(node, dim):
            continue
        if rec.get('state') in PASS_STATES:
            return True
    for kind in ('referent', 'rendered'):
        if not verification_requires_independence(node, kind):
            continue
        rec = (node.get('verification') or {}).get(kind) or {}
        if rec.get('state') in PASS_STATES:
            return True
    return False


def _impl_run(node: dict) -> str | None:
    run = node.get('implementation_run')
    return str(run) if run else None


def implementation_provenance_issue(node: dict) -> str | None:
    if not implementation_provenance_required(node):
        return None
    if _impl_run(node):
        return None
    nid = node.get('id') or '?'
    return (
        f'IMPLEMENTATION_PROVENANCE_REQUIRED: {nid} requires implementation_run from '
        f'node.stage -> implement before independent gates can be evaluated'
    )


def _pass_provenance_ok(node: dict, pass_run: str | None, pass_actor: str | None) -> bool:
    impl_run = _impl_run(node)
    if not impl_run or not pass_run:
        return False
    if pass_run != impl_run:
        return True
    impl_actor = node.get('implementation_actor')
    if impl_actor and pass_actor and pass_actor != impl_actor:
        return True
    return False


def independence_issue(
    node: dict,
    *,
    dim: str | None = None,
    verify_kind: str | None = None,
) -> str | None:
    nid = node.get('id') or '?'
    impl_run = _impl_run(node)

    if dim is not None:
        if not quality_dim_requires_independence(node, dim):
            return None
        rec = (node.get('quality') or {}).get(dim) or {}
        state = rec.get('state')
        if state not in QUALITY_DONE or state == 'na':
            return None
        if not impl_run:
            return (
                f'IMPLEMENTATION_PROVENANCE_REQUIRED: {nid} {dim} {state} lacks '
                f'implementation_run from node.stage -> implement'
            )
        pass_run = rec.get('pass_run')
        pass_actor = rec.get('pass_actor')
        if not pass_run:
            return (
                f'INDEPENDENT_REVIEW_REQUIRED: {nid} {dim} {state} lacks pass provenance'
            )
        if not _pass_provenance_ok(node, pass_run, pass_actor):
            who = pass_run
            if pass_actor:
                who = f'{pass_run}/{pass_actor}'
            impl = impl_run or 'unknown'
            return (
                f'INDEPENDENT_REVIEW_REQUIRED: {nid} {dim} {state} was produced by '
                f'implementation run {impl} (pass run {who})'
            )
        return None

    if verify_kind is not None:
        if not verification_requires_independence(node, verify_kind):
            return None
        rec = (node.get('verification') or {}).get(verify_kind) or {}
        state = rec.get('state')
        if state not in QUALITY_DONE:
            return None
        if not impl_run:
            return (
                f'IMPLEMENTATION_PROVENANCE_REQUIRED: {nid} verification.{verify_kind} '
                f'{state} lacks implementation_run from node.stage -> implement'
            )
        pass_run = rec.get('pass_run')
        pass_actor = rec.get('pass_actor')
        if not pass_run:
            return (
                f'INDEPENDENT_REVIEW_REQUIRED: {nid} verification.{verify_kind} {state} '
                f'lacks pass provenance'
            )
        if not _pass_provenance_ok(node, pass_run, pass_actor):
            who = pass_run
            if pass_actor:
                who = f'{pass_run}/{pass_actor}'
            impl = impl_run or 'unknown'
            return (
                f'INDEPENDENT_REVIEW_REQUIRED: {nid} verification.{verify_kind} {state} '
                f'was produced by implementation run {impl} (pass run {who})'
            )
        return None

    return None


def independence_issues(node: dict) -> list[str]:
    issues: list[str] = []
    msg = implementation_provenance_issue(node)
    if msg:
        issues.append(msg)
    for dim in sorted((node.get('quality') or {})):
        msg = independence_issue(node, dim=dim)
        if msg:
            issues.append(msg)
    for kind in ('referent', 'rendered', 'behavioral', 'journeys'):
        msg = independence_issue(node, verify_kind=kind)
        if msg:
            issues.append(msg)
    return issues


def independence_ok(node: dict) -> tuple[bool, str | None]:
    issues = independence_issues(node)
    if issues:
        return False, issues[0]
    return True, None
