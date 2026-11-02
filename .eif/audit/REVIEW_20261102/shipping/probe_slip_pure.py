"""GOV-008 pure probe (no DB): vessel slip when the port ETA was pulled in, and a vessel with no port ETA."""
import os, sys
sys.path.insert(0, os.getcwd())
from datetime import date
from app.services.shipping.on_the_water import WaterLine, build_vessels, config_from_overrides
cfg = config_from_overrides({})
def ln(i, **kw):
    base = dict(id=i, quantity=10.0, amount=None, currency="USD", amount_suspect=False, line_state="shipped", report_type="acza_workbook_shipped",
                ship_way="SEA", on_board=date(2026, 9, 19), port_eta=date(2026, 11, 5), port_ata=None, pod=None, ship_confirm=date(2026, 9, 18),
                exwork=None, forwarder="COSCO", hub="ckg", deliver_port="ZAJNB", vessel_name=None, voyage_no=None, delivery_no=f"D{i}",
                model="M", distributor="X")
    base.update(kw)
    w = WaterLine(**base)
    return w
pulled = ln(1); pulled.first_eta = date(2026, 11, 20); pulled.first_eta_report = date(2026, 9, 29)
noeta = ln(2, on_board=date(2026, 10, 1), port_eta=None, hub="nl")
for v in build_vessels([pulled, noeta], as_of=date(2026, 10, 28), report_date=date(2026, 10, 27), cfg=cfg):
    print({k: v[k] for k in ("eta", "overdue", "days_overdue", "days_to_eta", "slip_days", "history", "pct")})
