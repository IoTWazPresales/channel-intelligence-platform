"""My accounts is a query filter. No database connection."""

from app.core.my_accounts import (
    ACCOUNT_PREDICATE_BIND,
    account_predicate,
    accounts_to_store,
    header_clears_my_accounts,
    request_my_account_ids,
    reset_my_accounts,
)
from app.core.product_line_scope import product_line_scope_statement, request_product_lines
from app.query.model.compiler import compile_plan
from app.query.model.graph import V2Request, plan_request
from app.query.model.loader import clear_model_cache, default_model
from app.semantics.registry import load_catalog
from app.services.brief_signals import cst_late_missing_count_stmt


def setup_function() -> None:
    clear_model_cache()
    request_my_account_ids.set(None)
    request_product_lines.set(None)


def _compiled_sellthrough() -> str:
    model = default_model()
    request = V2Request(measures=["cst_sellthrough.units"], breakdowns=["customer"])
    plan = plan_request(model, request, v1_catalog=load_catalog())
    assert plan.ok, plan.refusals
    return compile_plan(model, plan, tenant_id="example").sql_text()


def test_predicate_is_in_the_query_while_the_filter_is_on():
    account_token = request_my_account_ids.set(frozenset({11, 22}))
    line_token = request_product_lines.set(frozenset({"line-a"}))
    try:
        scope_sql, _params = product_line_scope_statement() or ("", {})
        assert "cip.product_lines" in scope_sql
        assert ACCOUNT_PREDICATE_BIND in _compiled_sellthrough()
        assert ACCOUNT_PREDICATE_BIND in str(cst_late_missing_count_stmt())
    finally:
        reset_my_accounts(account_token)
        request_product_lines.reset(line_token)


def test_predicate_is_absent_after_clear():
    account_token = request_my_account_ids.set(None)
    line_token = request_product_lines.set(frozenset({"line-a"}))
    try:
        assert header_clears_my_accounts({"x-cip-my-accounts": "off"})
        assert account_predicate(object()) is None
        scope_sql, _params = product_line_scope_statement() or ("", {})
        assert "cip.product_lines" in scope_sql
        assert ACCOUNT_PREDICATE_BIND not in _compiled_sellthrough()
        assert ACCOUNT_PREDICATE_BIND not in str(cst_late_missing_count_stmt())
    finally:
        reset_my_accounts(account_token)
        request_product_lines.reset(line_token)


def test_accounts_to_store_uses_existing_ids_only():
    assert accounts_to_store("all", [11], {11}) == []
    assert accounts_to_store("selected", [22, 11, 22], {11, 22}) == [22, 11]
    try:
        accounts_to_store("selected", [11], set())
    except ValueError as exc:
        assert "already exist" in str(exc)
    else:
        raise AssertionError("missing account was accepted")
    try:
        accounts_to_store("selected", [], {11})
    except ValueError as exc:
        assert "at least one account" in str(exc)
    else:
        raise AssertionError("empty selection was accepted")
