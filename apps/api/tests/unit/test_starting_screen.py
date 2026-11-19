"""D-0141 starting screen and My accounts default (no database)."""

from __future__ import annotations

import pytest
from app.core.my_accounts import (
    BRIEF_PATH,
    MY_ACCOUNTS_STARTER_PATH,
    filter_default_on,
    filter_on,
    header_clears_my_accounts,
    header_my_accounts_choice,
    starting_screen,
)

JOBS = ("account_manager", "product_manager", "finance", "country_manager", "admin", None)


@pytest.mark.parametrize("job", JOBS)
def test_assigned_policy_keeps_todays_rule(job):
    assert filter_default_on(policy="assigned", job=job, assigned_count=3) is True
    assert filter_default_on(policy="assigned", job=job, assigned_count=0) is False
    assert starting_screen(policy="assigned", job=job, assigned_count=3) == BRIEF_PATH


@pytest.mark.parametrize("job", JOBS)
def test_d0141_only_an_account_manager_with_accounts_starts_on(job):
    on = job == "account_manager"
    assert filter_default_on(policy="d0141", job=job, assigned_count=2) is on
    assert starting_screen(policy="d0141", job=job, assigned_count=2) == (
        MY_ACCOUNTS_STARTER_PATH if on else BRIEF_PATH
    )
    # An empty assignment lands on Brief with the filter off, whatever the job.
    assert filter_default_on(policy="d0141", job=job, assigned_count=0) is False
    assert starting_screen(policy="d0141", job=job, assigned_count=0) == BRIEF_PATH


def test_the_sign_in_choice_overrides_the_default_but_never_invents_accounts():
    assert filter_on(default_on=True, assigned_count=2, choice=None) is True
    assert filter_on(default_on=True, assigned_count=2, choice="off") is False
    assert filter_on(default_on=False, assigned_count=2, choice=None) is False
    assert filter_on(default_on=False, assigned_count=2, choice="on") is True
    assert filter_on(default_on=False, assigned_count=0, choice="on") is False


def test_header_choice():
    assert header_my_accounts_choice({"x-cip-my-accounts": "off"}) == "off"
    assert header_my_accounts_choice({"x-cip-my-accounts": " ON "}) == "on"
    assert header_my_accounts_choice({"x-cip-my-accounts": "maybe"}) is None
    assert header_my_accounts_choice({}) is None
    assert header_my_accounts_choice(None) is None
    assert header_clears_my_accounts({"x-cip-my-accounts": "off"})
    assert not header_clears_my_accounts({"x-cip-my-accounts": "on"})
