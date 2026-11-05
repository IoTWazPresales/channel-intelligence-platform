"""Upsert listing_seed seller names/ids and curated site patterns.

``feed_profile_json`` lives on ``customer_report_config`` (one row per
``dim_customer`` id). ``dim_customer`` has no ``feed_profile_json`` column;
this script writes the config row importers and autoconfigure read.

Dry-run is the default. ``--apply`` commits. Refuses database ``cip`` unless
``--allow-cip`` is passed. Prints ``current_database()`` and a before/after
``listing_seed`` diff. Other feed-profile keys are left as they are.
Creating a missing config row does not set ``reports_expected``.

Config file (JSON)::

    {
      "customers": [
        {
          "customer_id": 1,
          "marketplace": "<site key>",
          "seller_names": ["Seller"],
          "seller_ids": ["s1"],
          "site": {
            "adapter_key": "html_page",
            "product_url_pattern": "https://host.example.test/p/{page_id}",
            "page_id_pattern": "/p/([^/]+)",
            "details_url_pattern": "https://host.example.test/d/{page_id}",
            "search_url_pattern": "https://host.example.test/s?q={query}"
          }
        }
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SITE_KEYS = frozenset(
    {
        "adapter_key",
        "product_url_pattern",
        "page_id_pattern",
        "search_url_pattern",
        "details_url_pattern",
        "first_party_seller",
        "rate_limit_seconds",
        "display_name",
    }
)


class DatabaseRefused(SystemExit):
    """The connected database is not an allowed target."""


def ensure_database_allowed(database_name: str, *, allow_cip: bool) -> None:
    if database_name == "cip" and not allow_cip:
        raise DatabaseRefused("refusing database cip; pass --allow-cip to run against cip")


def merge_listing_seed(profile: dict[str, Any] | None, patch: dict[str, Any]) -> dict[str, Any]:
    """Merge seller names/ids and curated site fields. Other keys stay."""
    base = dict(profile or {})
    current = base.get("listing_seed")
    seed = dict(current) if isinstance(current, dict) else {}
    marketplace = patch.get("marketplace")
    if isinstance(marketplace, str) and marketplace.strip():
        seed["marketplace"] = marketplace.strip().lower()
    if "seller_names" in patch:
        seed["seller_names"] = [str(value) for value in (patch.get("seller_names") or [])]
    if "seller_ids" in patch:
        seed["seller_ids"] = [str(value) for value in (patch.get("seller_ids") or [])]
    site_patch = patch.get("site")
    if isinstance(site_patch, dict):
        current_site = seed.get("site")
        site = dict(current_site) if isinstance(current_site, dict) else {}
        for key, value in site_patch.items():
            if key in _SITE_KEYS:
                site[key] = value
        seed["site"] = site
    base["listing_seed"] = seed
    return base


def _listing_seed(profile: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {}
    seed = profile.get("listing_seed")
    return dict(seed) if isinstance(seed, dict) else {}


def apply_listing_seed_config(
    session: Any,
    payload: dict[str, Any],
    *,
    apply: bool,
    allow_cip: bool,
) -> list[dict[str, Any]]:
    """Print the database name and each before/after diff. Write only when ``apply``."""
    from sqlalchemy import select, text

    from app.models.customer_report_config import CustomerReportConfig
    from app.models.dimensions import DimCustomer

    database_name = session.execute(text("select current_database()")).scalar_one()
    print(f"current_database() {database_name}")
    ensure_database_allowed(str(database_name), allow_cip=allow_cip)

    results: list[dict[str, Any]] = []
    customers = payload.get("customers") if isinstance(payload, dict) else None
    if not isinstance(customers, list):
        raise DatabaseRefused("config must be an object with a customers list")
    for item in customers:
        if not isinstance(item, dict) or item.get("customer_id") is None:
            print("skip entry with no customer_id")
            results.append({"customer_id": None, "error": "missing_customer_id"})
            continue
        customer_id = int(item["customer_id"])
        customer = session.get(DimCustomer, customer_id)
        if customer is None:
            print(f"customer_id={customer_id} missing")
            results.append({"customer_id": customer_id, "error": "missing_customer"})
            continue
        config = session.scalar(
            select(CustomerReportConfig).where(CustomerReportConfig.customer_id == customer_id)
        )
        before_profile = (
            dict(config.feed_profile_json)
            if config is not None and isinstance(config.feed_profile_json, dict)
            else {}
        )
        after_profile = merge_listing_seed(before_profile, item)
        before_seed = _listing_seed(before_profile)
        after_seed = _listing_seed(after_profile)
        changed = before_seed != after_seed
        print(f"customer_id={customer_id} changed={str(changed).lower()} apply={str(apply).lower()}")
        print("before " + json.dumps(before_seed, sort_keys=True, default=str))
        print("after " + json.dumps(after_seed, sort_keys=True, default=str))
        if apply and changed:
            if config is None:
                config = CustomerReportConfig(
                    customer_id=customer_id,
                    reports_expected=False,
                    feed_profile_json=after_profile,
                )
                session.add(config)
            else:
                config.feed_profile_json = after_profile
            session.flush()
        results.append({"customer_id": customer_id, "changed": changed, "applied": bool(apply and changed)})
    return results


def _ensure_api_path() -> None:
    api_root = Path(__file__).resolve().parents[2]
    text = str(api_root)
    if text not in sys.path:
        sys.path.insert(0, text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upsert listing_seed seller and site patterns into feed_profile_json.")
    parser.add_argument("config", type=Path, help="JSON config file path")
    parser.add_argument("--apply", action="store_true", help="Commit. Default is dry-run.")
    parser.add_argument("--allow-cip", action="store_true", help="Permit the database named cip.")
    args = parser.parse_args(argv)
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    _ensure_api_path()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.core.config import get_settings

    url = get_settings().database_url_sync
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    engine = create_engine(url)
    with Session(engine) as session:
        apply_listing_seed_config(session, payload, apply=args.apply, allow_cip=args.allow_cip)
        if args.apply:
            session.commit()
        else:
            session.rollback()
    engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DatabaseRefused as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
