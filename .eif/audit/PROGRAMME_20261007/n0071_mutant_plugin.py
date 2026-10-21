"""N-0071 negative control: un-wire the strict-pair exclusion in each reader; reader tests must fail."""
from sqlalchemy import true


def pytest_configure(config):  # noqa: ARG001
    import app.api.v1.endpoints.shipping as shipping
    import app.services.brief_signals as brief
    import app.services.commercial_planner.inbound_lineup_quarter as ilq
    import app.services.cpor.intake_weighted_mac as mac

    for mod in (shipping, brief, ilq, mac):
        mod.exclude_open_when_shipped_twin = lambda _model: true()
