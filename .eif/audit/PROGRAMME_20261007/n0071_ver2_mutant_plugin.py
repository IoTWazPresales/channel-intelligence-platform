"""GOV-008 RUN-20261008-N0071-VER2: in-memory mutants of app/services/shipment_strict_pair.py.

Loaded with ``-p n0071_ver2_mutant_plugin`` and ``N0071_VER2_MUTANT=<name>``. The module source
is read, the mutation is applied to the text in memory, and the result is registered in
``sys.modules`` before any test imports it. The file on disk is never written.
"""

from __future__ import annotations

import os
import sys
import types

_NAME = "app.services.shipment_strict_pair"
_PATH = os.path.join(os.getcwd(), "app", "services", "shipment_strict_pair.py")

MUTANTS: dict[str, list[tuple[str, str]]] = {
    # Remainder against one twin only (the largest), not the sum of all shipped twins.
    "first_twin_only": [
        (
            "func.sum(case((is_shipped, func.coalesce(r.quantity, 0)), else_=0))",
            "func.max(case((is_shipped, func.coalesce(r.quantity, 0)), else_=0))",
        ),
        (
            "sum(CASE WHEN lower(line_state) = 'shipped' THEN coalesce(quantity, 0) ELSE 0 END)",
            "max(CASE WHEN lower(line_state) = 'shipped' THEN coalesce(quantity, 0) ELSE 0 END)",
        ),
    ],
    # Pro-rata value replaced by the full stored amount (ORM and SQL text).
    "pro_rata_to_full": [
        (
            "(counted_qty > 0, model.amount * counted_qty / func.nullif(model.quantity, 0)),",
            "(counted_qty > 0, model.amount),",
        ),
        (
            '"WHEN twin_rem.counted_qty > 0 THEN fact_inbound_shipment.amount * twin_rem.counted_qty "\n'
            '    "/ nullif(fact_inbound_shipment.quantity, 0) "',
            '"WHEN twin_rem.counted_qty > 0 THEN fact_inbound_shipment.amount "',
        ),
    ],
    # Exact coverage (open == shipped) no longer skipped by the line filter.
    "equal_not_covered": [
        ("w.c.open_qty <= w.c.shipped_qty,", "w.c.open_qty < w.c.shipped_qty,"),
    ],
    # A covered line keeps its stored amount in counted_amount.
    "covered_amount_full": [
        (
            "        (counted_qty > 0, model.amount * counted_qty / func.nullif(model.quantity, 0)),\n"
            "        else_=0,",
            "        (counted_qty > 0, model.amount * counted_qty / func.nullif(model.quantity, 0)),\n"
            "        else_=model.amount,",
        ),
    ],
}


def _install() -> None:
    mutant = os.environ.get("N0071_VER2_MUTANT", "").strip()
    if not mutant:
        return
    with open(_PATH, encoding="utf-8") as fh:
        src = fh.read()
    for old, new in MUTANTS[mutant]:
        n = src.count(old)
        if n != 1:
            raise RuntimeError(f"mutant {mutant}: expected 1 match, found {n}: {old[:60]!r}")
        src = src.replace(old, new)
    import app.services  # noqa: F401  (parent package first)

    mod = types.ModuleType(_NAME)
    mod.__file__ = _PATH
    sys.modules[_NAME] = mod
    exec(compile(src, _PATH, "exec"), mod.__dict__)
    setattr(sys.modules["app.services"], "shipment_strict_pair", mod)
    sys.stderr.write(f"[n0071_ver2] mutant {mutant} installed in memory\n")


_install()
