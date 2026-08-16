"""BACKLOG-111: worker code pin string is non-empty."""
from app.worker.code_pin import describe_worker_code_pin


def test_describe_worker_code_pin_mentions_parser() -> None:
    pin = describe_worker_code_pin()
    assert pin.startswith("celery worker code pin sha=")
    assert "lineup_case_parser_mtime=" in pin
