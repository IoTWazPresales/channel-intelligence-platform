"""pytest plugin (N-0071 round 3): net-requirement in-transit totals the stored quantity again.

In-memory mutant (monkeypatch), so the shared file net_requirement.py is never written
while another run (N-0065) may be editing it.
"""
from __future__ import annotations

import dataclasses

import pytest


@pytest.fixture(autouse=True)
def _net_requirement_stored_quantity(monkeypatch):
    from app.services import shipment_strict_pair as ssp
    from app.services.lineup import net_requirement as nr

    real = ssp.twin_remainder

    def mutant(model, **kw):
        return dataclasses.replace(real(model, **kw), counted_quantity=model.quantity)

    monkeypatch.setattr(nr, "twin_remainder", mutant)
