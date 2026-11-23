"""GS1 check digits and canonical GTIN-14 forms. No database or network."""

import pytest
from app.services.listing_capture.web_discovery.gtin import (
    calculate_check_digit,
    is_valid_gtin,
    normalize_gtin,
)

VALID = (
    ("96385074", "00000096385074"),
    ("036000291452", "00036000291452"),
    ("4006381333931", "04006381333931"),
    ("10012345000017", "10012345000017"),
)


@pytest.mark.parametrize(("raw", "canonical"), VALID)
def test_supported_lengths_and_canonical_forms(raw, canonical):
    assert calculate_check_digit(raw[:-1]) == raw[-1]
    assert is_valid_gtin(raw)
    assert normalize_gtin(raw) == canonical
    assert normalize_gtin(canonical) == canonical


def test_presentation_separators_and_leading_zeros():
    assert normalize_gtin(" 0 36000-29145 2\n") == "00036000291452"
    assert normalize_gtin("00036000291452") == normalize_gtin("036000291452")


@pytest.mark.parametrize(("raw", "_canonical"), VALID)
def test_every_single_digit_mutation_is_rejected(raw, _canonical):
    for index, digit in enumerate(raw):
        changed = raw[:index] + str((int(digit) + 1) % 10) + raw[index + 1 :]
        assert normalize_gtin(changed) is None
        assert not is_valid_gtin(changed)


@pytest.mark.parametrize(
    "raw",
    [
        None,
        True,
        36000291452,
        36000291452.0,
        "",
        " ",
        "0",
        "1234567",
        "123456789",
        "1234567890",
        "12345678901",
        "123456789012345",
        "00000000",
        "000000000000",
        "0000000000000",
        "00000000000000",
        "4006381333932",
        "gtin:4006381333931",
        "4006381333931.0",
        "4.006381333931e12",
        "+4006381333931",
        "4006381333931x",
        "４００６３８１３３３９３１",
        "4006381/333931",
    ],
)
def test_invalid_input_is_not_repaired_or_coerced(raw):
    assert normalize_gtin(raw) is None
    assert not is_valid_gtin(raw)


@pytest.mark.parametrize(
    "body", [None, 1234567, "", "123456", "12345678", "123456a", "１２３４５６７"]
)
def test_invalid_payload_raises_value_error(body):
    with pytest.raises(ValueError):
        calculate_check_digit(body)
