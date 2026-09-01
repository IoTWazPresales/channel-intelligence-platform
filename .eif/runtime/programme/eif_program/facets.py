"""Deterministic facet inference for programme nodes and task mode."""
from __future__ import annotations

import re

# Words that themselves denote a user-facing surface.
EXPLICIT_UI = re.compile(r'\b(?:ui|ux|interface|screens?)\b', re.I)

# Shell is UI only as an explicit product/UI shell, never as a generic token.
PRODUCT_SHELL = re.compile(r'\b(?:product|ui|ux)\s+shell\b', re.I)

# Head nouns that denote a user-facing surface when they are the object of the work.
SURFACE_HEADS = frozenset({'page', 'dashboard', 'checkout'})

# Trailing work-actions stripped so the object head can be recovered.
_WORK_ACTIONS = frozenset({
    'redesign', 'overhaul', 'revamp', 'refresh', 'rework',
    'change', 'changes', 'update', 'updates', 'fix', 'fixes',
    'correction', 'corrections',
})

# Light leading words that do not affect the object head.
_LEADING_NOISE = frozenset({
    'a', 'an', 'the', 'new', 'write', 'add', 'create', 'build',
    'make', 'implement', 'major', 'minor', 'trivial',
})

# Actions that make a user-facing surface object material design work.
_SURFACE_MATERIAL_ACTIONS = frozenset({'redesign', 'overhaul', 'revamp'})

# Phrases that are themselves material design work (and imply ui).
EXPLICIT_MATERIAL = re.compile(
    r'\b(?:product\s+shell|ui\s+shell|'
    r'(?:ui|ux|interface)\s+(?:redesign|overhaul)|'
    r'art[- ]direction|visual\s+redesign|design\s+overhaul|'
    r'substantial\s+design)\b',
    re.I,
)

# Materiality when ui is already established (not itself a UI detector).
MATERIAL_WHEN_UI = re.compile(
    r'\b(?:major\s+)?information\s+architecture(?:\s+(?:change|redesign))?\b',
    re.I,
)

TRIVIAL_TITLE = re.compile(
    r'\b(?:contrast fix|colour fix|color fix|typo|alignment fix|'
    r'minor (?:css|ui)|small css|button colou?r|regression fix)\b',
    re.I,
)


def _norm_facets(facets) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for f in facets or []:
        f = str(f).strip()
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def _risk_rank(r: str | None) -> int:
    try:
        return int(str(r or 'R0').upper().replace('R', ''))
    except Exception:
        return 0


def _tokens(text: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', text.lower())


def _object_head(tokens: list[str]) -> str | None:
    """Recover the head noun of the work object.

    Drops a trailing 'for …' adjunct and trailing work-actions so that
    'admin dashboard redesign' heads at dashboard while 'page cache redesign'
    heads at cache. Contextual UI nouns count only as this head, never as
    modifiers of infrastructure/runtime/data concepts.
    """
    t = list(tokens)
    if 'for' in t:
        t = t[: t.index('for')]
    while t and t[-1] in _WORK_ACTIONS:
        t.pop()
    while t and t[0] in _LEADING_NOISE:
        t.pop(0)
    return t[-1] if t else None


def _is_surface_object(title_s: str) -> bool:
    return _object_head(_tokens(title_s)) in SURFACE_HEADS


def _surface_material(title_s: str) -> bool:
    tokens = _tokens(title_s)
    if not any(t in _SURFACE_MATERIAL_ACTIONS for t in tokens):
        return False
    return bool(PRODUCT_SHELL.search(title_s)) or _object_head(tokens) in SURFACE_HEADS


def _infer_ui(title_s: str) -> bool:
    if EXPLICIT_UI.search(title_s) or PRODUCT_SHELL.search(title_s) or EXPLICIT_MATERIAL.search(title_s):
        return True
    return _is_surface_object(title_s)


def resolve_facets(
    *,
    class_: str | None = None,
    title: str | None = None,
    facets: list[str] | None = None,
    risk: str | None = None,
    acceptance_criteria: list[str] | None = None,
) -> list[str]:
    """Merge explicit facets with deterministic inference.

    ui is inferred from explicit UI terms (ui/ux/interface/screen, product/ui
    shell) or from a contextual surface noun (page, dashboard, checkout) only
    when that noun is the object of the work. Bare shell is not UI.
    Materiality establishes design_experience once ui is present.
    Programme class alone is not evidence of UI work.
    """
    cls = (class_ or 'feature').strip()
    title_s = ' '.join([title or ''] + list(acceptance_criteria or [])).strip()
    out = set(_norm_facets(facets))

    if _infer_ui(title_s):
        out.add('ui')

    has_ui = 'ui' in out
    explicit_ui = bool(PRODUCT_SHELL.search(title_s) or EXPLICIT_MATERIAL.search(title_s))
    material = (
        explicit_ui
        or (has_ui and cls == 'redesign')
        or (has_ui and _surface_material(title_s))
        or (has_ui and bool(MATERIAL_WHEN_UI.search(title_s)))
    )
    trivial = cls == 'feature' and _risk_rank(risk) <= 1 and bool(TRIVIAL_TITLE.search(title_s))

    if material and not trivial:
        out.add('design_experience')
        if explicit_ui or _is_surface_object(title_s):
            out.add('ui')

    return sorted(out)
