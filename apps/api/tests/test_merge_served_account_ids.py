"""Pure merge for store-dc served accounts (B1: no silent link drop)."""

from app.services.store_dc.candidates import merge_served_account_ids


def test_preserves_ids_not_in_visible_row_set():
    before = {1, 2, 99}
    wanted = {1}
    visible = {1}
    assert merge_served_account_ids(before, wanted, visible) == [1, 2, 99]


def test_removes_only_when_id_was_visible():
    before = {1, 2}
    wanted = {1}
    visible = {1, 2}
    assert merge_served_account_ids(before, wanted, visible) == [1]
