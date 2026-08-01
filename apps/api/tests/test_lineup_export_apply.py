from app.services.lineup.export_apply import half_year_period_starts, net_requirement_to_csv
from datetime import date

def test_half_year_1h():
    slots = half_year_period_starts(2026, 1)
    assert slots == [(date(2026, 1, 1), "26Q1"), (date(2026, 4, 1), "26Q2")]

def test_csv_header():
    csv = net_requirement_to_csv({"rows": [{"distributor_id": 1, "product_id": 2, "net_requirement": 5}]})
    assert "net_requirement" in csv.splitlines()[0]
    assert "1,2" in csv.replace(" ", "")
