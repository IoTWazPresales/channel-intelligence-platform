"""GOV-008 RUN-20261008-N0071-VER3: in-memory mutants of
app/services/commercial_planner/lineup_case_suggested_pos.py.

Loaded with ``-p n0071_ver3_mutant_plugin`` and ``N0071_VER3_MUTANT=<name>``. The module source
is read, the mutation is applied to the text in memory, and the result is registered in
``sys.modules`` before any test imports it. The file on disk is never written.
"""

from __future__ import annotations

import os
import sys
import types

_NAME = "app.services.commercial_planner.lineup_case_suggested_pos"
_PATH = os.path.join(os.getcwd(), "app", "services", "commercial_planner", "lineup_case_suggested_pos.py")

_FILTERED = 'func.coalesce(func.sum(EV.quantity).filter(EV.line_state == "shipped"), 0)'

# (old, new, expected match count)
MUTANTS: dict[str, list[tuple[str, str, int]]] = {
    # Open lines that have a strict shipped twin (same OU + order + item) are counted as shipped.
    "twin_open_counted": [
        (
            _FILTERED,
            "func.coalesce(func.sum(EV.quantity).filter(or_(EV.line_state == \"shipped\", "
            "select(_TW.id).where(_TW.line_state == \"shipped\", _TW.order_no == EV.order_no, "
            "_TW.item_code == EV.item_code, _TW.operating_unit == EV.operating_unit).exists())), 0)",
            1,
        ),
        ("EV = shipment_evidence_read_model()\n",
         "EV = shipment_evidence_read_model()\nfrom sqlalchemy.orm import aliased as _aliased\n_TW = _aliased(EV)\n", 1),
    ],
    # Filter moved from the SUM to the WHERE clause (drops open-only POs from the suggestions).
    "where_not_filter": [
        (_FILTERED, "func.coalesce(func.sum(EV.quantity), 0)", 1),
        ("EV.purchase_order_id.isnot(None),\n",
         "EV.purchase_order_id.isnot(None),\n            EV.line_state == \"shipped\",\n", 2),
    ],
    # Distributor tie-break ordered ascending by shipped units.
    "order_asc": [
        ("_shipped_units_sum().desc(),", "_shipped_units_sum().asc(),", 1),
    ],
    # Open lines counted as shipped (pre-fix behaviour, all line states).
    "all_states": [
        (_FILTERED, "func.coalesce(func.sum(EV.quantity), 0)", 1),
    ],
}


def _install() -> None:
    mutant = os.environ.get("N0071_VER3_MUTANT", "").strip()
    if not mutant:
        return
    with open(_PATH, encoding="utf-8") as fh:
        src = fh.read()
    for old, new, expected in MUTANTS[mutant]:
        n = src.count(old)
        if n != expected:
            raise RuntimeError(f"mutant {mutant}: expected {expected} match(es), found {n}: {old[:60]!r}")
        src = src.replace(old, new)
    import app.services.commercial_planner as parent

    mod = types.ModuleType(_NAME)
    mod.__file__ = _PATH
    sys.modules[_NAME] = mod
    exec(compile(src, _PATH, "exec"), mod.__dict__)
    setattr(parent, "lineup_case_suggested_pos", mod)
    sys.stderr.write(f"[n0071_ver3] mutant {mutant} installed in memory\n")


_install()
