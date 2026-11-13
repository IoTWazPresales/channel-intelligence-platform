"""W1-D: scripts/ops/restore_listing_site_readers.py on cip_test only. No network.

Site rows are shaped like the ones migration 20261103_0053 left behind: two sites with link
patterns but no reader, one site already configured with a steward value. Fictional site keys
and hosts only. Everything runs inside one transaction that is rolled back.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from app.models.dimensions import DimCustomer
from app.models.iam import Tenant
from app.models.listing_capture import CustomerListing
from app.models.listing_site import ListingSite
from app.services.listing_capture.registry import poll_active_listings
from app.services.listing_capture.site_pause import MemorySitePauseStore
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

API_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = API_ROOT / "scripts" / "ops" / "restore_listing_site_readers.py"
DOCS_FILE = API_ROOT.parents[1] / "docs" / "ops" / "listing_site_readers_20261113.json"


def _script():
    spec = importlib.util.spec_from_file_location("restore_listing_site_readers", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def scratch():
    """Input files under apps/api/.tmp (gitignored), not the system temp folder."""
    import shutil

    folder = API_ROOT / ".tmp" / "restore_listing_site_readers_test" / uuid.uuid4().hex[:8]
    folder.mkdir(parents=True, exist_ok=True)
    try:
        yield folder
    finally:
        shutil.rmtree(folder, ignore_errors=True)


@pytest.fixture()
def conn():
    from app.core.config import get_settings

    get_settings.cache_clear()
    url = get_settings().database_url_sync.replace("postgresql://", "postgresql+psycopg://", 1)
    eng = create_engine(url)
    try:
        connection = eng.connect()
    except Exception as exc:  # pragma: no cover - environment
        pytest.skip(f"no database: {type(exc).__name__}")
    db = connection.execute(text("select current_database()")).scalar_one()
    print("current_database()", db)
    if db != "cip_test":
        connection.close()
        eng.dispose()
        pytest.skip(f"restore script DB test runs on cip_test only (current_database()={db})")
    connection.rollback()
    tx = connection.begin()
    try:
        yield connection
    finally:
        tx.rollback()
        connection.close()
        eng.dispose()


def _seed(conn) -> dict:
    """Three sites in a fresh tenant, shaped like the rows 0053 left: two without a reader."""
    tag = uuid.uuid4().hex[:6]
    tenant = f"t-restore-{tag}"
    rest_key, html_key, done_key = f"rs-rest-{tag}", f"rs-html-{tag}", f"rs-done-{tag}"
    session = Session(bind=conn)
    session.add(Tenant(id=tenant, name=f"Restore {tag}"))
    session.flush()
    customer = DimCustomer(
        code=f"RS-{tag}",
        name=f"Restore {tag}",
        customer_status="active",
        is_key_account=False,
        tenant_id=tenant,
    )
    session.add(customer)
    session.flush()
    session.add_all(
        [
            ListingSite(
                tenant_id=tenant,
                site_key=rest_key,
                display_name=rest_key,
                product_url_pattern=f"https://{rest_key}.example.test/x/ID{{page_id}}",
                page_id_pattern=r"ID(\d{5,12})",
                updated_by="listing-autoconfigure",
            ),
            ListingSite(
                tenant_id=tenant,
                site_key=html_key,
                display_name=html_key,
                product_url_pattern=f"https://{html_key}.example.test/dp/{{page_id}}",
                page_id_pattern=r"/dp/([A-Z0-9]{10})",
                updated_by="listing-autoconfigure",
            ),
            ListingSite(
                tenant_id=tenant,
                site_key=done_key,
                display_name=done_key,
                adapter_key="html_page",
                product_url_pattern=f"https://{done_key}.example.test/p/{{page_id}}",
                page_id_pattern=r"/p/(\d+)",
                first_party_seller="Steward Kept",
                updated_by="steward@x",
            ),
        ]
    )
    session.flush()
    for key, url in (
        (rest_key, f"https://{rest_key}.example.test/x/ID12345678"),
        (html_key, f"https://{html_key}.example.test/dp/B0TEST0001"),
        (done_key, f"https://{done_key}.example.test/p/42"),
    ):
        session.add(
            CustomerListing(
                customer_id=int(customer.id),
                url=url,
                marketplace=key,
                status="active",
                source="manual",
            )
        )
    session.flush()
    session.close()
    return {"tenant": tenant, "rest": rest_key, "html": html_key, "done": done_key}


def _input(scratch: Path, seeded: dict) -> Path:
    """Same shape as docs/ops/listing_site_readers_20261113.json, fictional values."""
    rest, html, done = seeded["rest"], seeded["html"], seeded["done"]
    doc = {
        "about": "test input",
        "tenant_id": seeded["tenant"],
        "sites": {
            rest: {
                "adapter_key": "rest_buybox_json",
                "details_url_pattern": (
                    f"https://api.{rest}.example.test/rest/details/ID{{page_id}}?platform=desktop"
                ),
                "search_url_pattern": f"https://api.{rest}.example.test/rest/search?q={{query}}",
                "product_url_pattern": f"https://{rest}.example.test/OTHER/{{page_id}}",
                "page_id_pattern": r"ID(\d{5,12})",
                "first_party_seller": "Market Retail",
                "rate_limit_seconds": 2.0,
            },
            html: {"adapter_key": "html_page", "rate_limit_seconds": 2.0},
            done: {
                "adapter_key": "html_page",
                "first_party_seller": "From File",
                "rate_limit_seconds": 2.0,
            },
        },
        "provenance": {"note": "ignored by the script"},
    }
    path = scratch / "readers.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path


def _rows(conn, tenant: str) -> dict[str, dict]:
    cols = (
        "site_key, adapter_key, product_url_pattern, page_id_pattern, search_url_pattern, "
        "details_url_pattern, first_party_seller, rate_limit_seconds, updated_by"
    )
    rows = (
        conn.execute(
            text(f"select {cols} from listing_site where tenant_id = :t order by site_key"),
            {"t": tenant},
        )
        .mappings()
        .all()
    )
    return {r["site_key"]: dict(r) for r in rows}


def _poll(conn, keys: list[str]) -> dict:
    session = Session(bind=conn)
    try:
        return poll_active_listings(
            session,
            marketplaces=keys,
            http_get=lambda _url, headers=None: (
                200,
                json.dumps({"price": 10.0, "availability": "in_stock"}),
            ),
            pause_store=MemorySitePauseStore(),
            sleep=lambda _s: None,
            log_result=False,
        )
    finally:
        session.flush()
        session.close()


def test_restore_fills_only_empty_columns_once_and_the_poll_reads_the_restored_sites(
    conn, scratch, capsys
) -> None:
    script = _script()
    seeded = _seed(conn)
    tenant, rest, html, done = seeded["tenant"], seeded["rest"], seeded["html"], seeded["done"]
    path = _input(scratch, seeded)
    before = _rows(conn, tenant)

    # Before: the poll skips both sites without a reader (the regression); the third is read.
    first_poll = _poll(conn, [rest, html, done])
    assert first_poll["skipped_not_configured"] == {rest: 1, html: 1}
    assert first_poll["polled"] == 1

    # Dry run: a plan, nothing written.
    lines: list[str] = []
    assert script.run(conn, input_path=path, apply=False, say=lines.append) == 0
    report = "\n".join(lines)
    print(report)
    assert "current_database() = cip_test" in report
    assert f"{rest} (site " in report and "no reader (missing: adapter_key) -> reader OK" in report
    assert (
        "details sample: " in report
        and f"https://api.{rest}.example.test/rest/details/ID12345678?platform=desktop" in report
    )
    assert "kept   product_url_pattern" in report  # the row's own link pattern is not replaced
    assert "kept   first_party_seller: 'Steward Kept'" in report
    assert _rows(conn, tenant) == before

    # Apply needs --expect-db equal to the database.
    refused: list[str] = []
    assert script.run(conn, input_path=path, apply=True, expect_db="cip", say=refused.append) == 2
    assert any("refused" in line for line in refused)
    assert _rows(conn, tenant) == before

    # Apply.
    applied: list[str] = []
    assert (
        script.run(conn, input_path=path, apply=True, expect_db="cip_test", say=applied.append) == 0
    )
    print("\n".join(applied))
    after = _rows(conn, tenant)
    print(json.dumps({k: {c: str(v) for c, v in r.items()} for k, r in after.items()}, indent=1))
    assert after[rest]["adapter_key"] == "rest_buybox_json"
    assert after[rest]["details_url_pattern"].endswith("/rest/details/ID{page_id}?platform=desktop")
    assert after[rest]["search_url_pattern"].endswith("/rest/search?q={query}")
    assert after[rest]["product_url_pattern"] == before[rest]["product_url_pattern"]  # kept
    assert after[rest]["first_party_seller"] == "Market Retail"
    assert float(after[rest]["rate_limit_seconds"]) == 2.0
    assert after[html]["adapter_key"] == "html_page"
    assert after[html]["first_party_seller"] is None  # not in the file: left empty
    assert after[done]["first_party_seller"] == "Steward Kept"  # never overwritten
    assert after[done]["adapter_key"] == "html_page"
    assert float(after[done]["rate_limit_seconds"]) == 2.0
    assert after[done]["updated_by"] == script.ACTOR
    assert all(after[k]["updated_by"] == script.ACTOR for k in (rest, html))

    # One audit event with the before/after rows and working undo SQL.
    events = (
        conn.execute(
            text(
                "select id, tenant_id, area, action, target_type, detail_json "
                "from platform_audit_event "
                "where tenant_id = :t and action = 'listing_site_reader_restore'"
            ),
            {"t": tenant},
        )
        .mappings()
        .all()
    )
    assert len(events) == 1
    detail = events[0]["detail_json"]
    assert events[0]["area"] == "admin" and events[0]["target_type"] == "listing_site"
    # rest: adapter, details, search, first-party seller, spacing (5);
    # html: adapter, spacing (2); done: spacing (1).
    assert detail["columns_filled"] == 8
    assert detail["sites"][rest]["before"]["adapter_key"] is None
    assert detail["sites"][rest]["after"]["adapter_key"] == "rest_buybox_json"
    assert sorted(detail["sites"][done]["filled"]) == ["rate_limit_seconds"]
    assert detail["sites"][done]["kept"]["first_party_seller"]["current"] == "Steward Kept"

    # Re-run: nothing to fill, nothing written, no second audit event.
    again: list[str] = []
    assert (
        script.run(conn, input_path=path, apply=True, expect_db="cip_test", say=again.append) == 0
    )
    assert any("nothing to fill; nothing written" in line for line in again)
    assert _rows(conn, tenant) == after
    assert (
        conn.execute(
            text(
                "select count(*) from platform_audit_event "
                "where tenant_id = :t and action = 'listing_site_reader_restore'"
            ),
            {"t": tenant},
        ).scalar_one()
        == 1
    )

    # After: one poll reads both restored sites; nothing is skipped as not configured.
    second_poll = _poll(conn, [rest, html])
    assert second_poll["skipped_not_configured"] == {}
    assert second_poll["not_configured_sites"] == []
    assert second_poll["polled"] == 2

    # The undo SQL from the audit event puts the empty values back.
    for site_key in (rest, html, done):
        conn.execute(text(detail["sites"][site_key]["undo_sql"]))
    undone = _rows(conn, tenant)
    for site_key in (rest, html, done):
        for column in (
            "adapter_key",
            "details_url_pattern",
            "search_url_pattern",
            "first_party_seller",
            "rate_limit_seconds",
        ):
            assert undone[site_key][column] == before[site_key][column], (site_key, column)
        assert undone[site_key]["updated_by"] == before[site_key]["updated_by"]


def test_failure_before_commit_rolls_everything_back(conn, scratch) -> None:
    script = _script()
    seeded = _seed(conn)
    path = _input(scratch, seeded)
    before = _rows(conn, seeded["tenant"])
    lines: list[str] = []
    code = script.run(
        conn,
        input_path=path,
        apply=True,
        expect_db="cip_test",
        say=lines.append,
        fail_before_commit=True,
    )
    assert code == 3
    assert any("ROLLED BACK" in line for line in lines)
    assert _rows(conn, seeded["tenant"]) == before
    assert (
        conn.execute(
            text("select count(*) from platform_audit_event where tenant_id = :t"),
            {"t": seeded["tenant"]},
        ).scalar_one()
        == 0
    )


def test_unknown_site_or_bad_value_stops_before_any_write(conn, scratch) -> None:
    script = _script()
    seeded = _seed(conn)
    before = _rows(conn, seeded["tenant"])
    missing = scratch / "missing.json"
    missing.write_text(
        json.dumps(
            {
                "tenant_id": seeded["tenant"],
                "sites": {"rs-absent-site": {"adapter_key": "html_page"}},
            }
        ),
        encoding="utf-8",
    )
    lines: list[str] = []
    assert (
        script.run(conn, input_path=missing, apply=True, expect_db="cip_test", say=lines.append)
        == 2
    )
    assert any("no listing_site row" in line for line in lines)
    bad = scratch / "bad.json"
    bad.write_text(
        json.dumps(
            {
                "tenant_id": seeded["tenant"],
                "sites": {seeded["rest"]: {"adapter_key": "no_such_reader"}},
            }
        ),
        encoding="utf-8",
    )
    lines = []
    assert script.run(conn, input_path=bad, apply=True, expect_db="cip_test", say=lines.append) == 2
    assert any("unknown adapter_key" in line for line in lines)
    extra = scratch / "extra.json"
    extra.write_text(
        json.dumps(
            {"tenant_id": seeded["tenant"], "sites": {seeded["rest"]: {"is_active": False}}}
        ),
        encoding="utf-8",
    )
    lines = []
    assert (
        script.run(conn, input_path=extra, apply=True, expect_db="cip_test", say=lines.append) == 2
    )
    assert any("columns not allowed here: is_active" in line for line in lines)
    assert _rows(conn, seeded["tenant"]) == before


def test_cli_dry_run_is_read_only_and_apply_needs_expect_db(conn, scratch, capsys) -> None:
    """The command-line path: the dry run runs read-only; --apply without the right --expect-db
    is refused before anything is read from the input or written."""
    script = _script()
    path = scratch / "cli.json"
    absent = f"rs-cli-{uuid.uuid4().hex[:6]}"
    doc = {"tenant_id": f"t-cli-{absent}", "sites": {absent: {"adapter_key": "html_page"}}}
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert script.main(["--input", str(path)]) == 2  # the site has no row: planned, not written
    out = capsys.readouterr().out
    assert "current_database() = cip_test; transaction_read_only = on; dry run" in out
    assert "no listing_site row" in out
    assert script.main(["--input", str(path), "--apply", "--expect-db", "cip"]) == 2
    out = capsys.readouterr().out
    assert "refused: --apply needs --expect-db 'cip_test' (got 'cip')" in out
    from app.db.session_sync import sync_engine

    with sync_engine.connect() as again:  # the pooled connection is read-write again
        assert again.execute(text("SHOW transaction_read_only")).scalar() == "off"


def test_reviewed_data_file_passes_the_script_checks() -> None:
    """The recovered values in docs/ops validate with the Sites & sellers rules."""
    script = _script()
    tenant, sites, sha = script.load_input(DOCS_FILE)
    assert tenant == "default" and len(sha) == 64
    assert len(sites) == 3
    for values in sites.values():
        assert set(values) <= set(script.FIELDS)
        assert values["adapter_key"] in {"html_page", "rest_buybox_json"}
