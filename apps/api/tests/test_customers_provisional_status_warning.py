"""PATCH customer_status provisional-reuse warning."""

from app.api.v1.endpoints.customers import (
    PROVISIONAL_REUSE_STATUS_WARNING,
    _provisional_reuse_status_warning,
)
from app.models.dimensions import DimCustomer


def test_provisional_warning_when_leaving_unverified_tmp_cust():
    row = DimCustomer(code="TMP-CUST-20260601120248-DC36", customer_status="unverified")
    assert _provisional_reuse_status_warning(row, "active") == PROVISIONAL_REUSE_STATUS_WARNING


def test_no_warning_when_staying_unverified_or_non_tmp():
    tmp = DimCustomer(code="TMP-CUST-ABC", customer_status="unverified")
    assert _provisional_reuse_status_warning(tmp, "unverified") is None
    real = DimCustomer(code="CUST-1001", customer_status="unverified")
    assert _provisional_reuse_status_warning(real, "active") is None
    active = DimCustomer(code="TMP-CUST-ABC", customer_status="active")
    assert _provisional_reuse_status_warning(active, "inactive") is None
