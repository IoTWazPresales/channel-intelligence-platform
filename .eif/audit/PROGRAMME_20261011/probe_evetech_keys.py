"""Evetech JSON-LD key names only."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from sqlalchemy import text  # noqa: E402

from app.db.session_sync import SessionLocal  # noqa: E402
from app.services.listing_capture.observation import decompress_snapshot  # noqa: E402


def main() -> None:
    sql = text(
        """
        SELECT o.raw_snapshot
        FROM listing_observation o
        JOIN customer_listing l ON l.id = o.listing_id
        WHERE o.raw_snapshot IS NOT NULL AND l.marketplace = 'evetech' AND o.parse_status = 'ok'
        ORDER BY o.fetched_at DESC
        LIMIT 1
        """
    )
    with SessionLocal() as session:
        blob = session.execute(sql).scalar()
        raw = decompress_snapshot(blob)
        blocks = re.findall(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            raw,
            flags=re.I | re.S,
        )
        for needle in (
            '\\"brand\\"', '\\"name\\"', '\\"description\\"', '\\"image\\"',
            '\\"sku\\"', "og:title", "<img", "breadcrumb", "InStock", "OutOfStock",
        ):
            print("count", needle.replace("\\", ""), raw.count(needle))
        print("type_product", raw.count('"@type":"Product"'))
        print("at_type", raw.count("@type"))
        start = 0
        for n in range(4):
            idx = raw.lower().find("ld+json", start)
            if idx < 0:
                break
            window = raw[max(0, idx - 30) : idx + 50].replace("\n", " ")
            print("win", n, window)
            start = idx + 6
        print("schema_product", raw.lower().count("schema.org/product"))
        print("ldjson_mentions", raw.lower().count("ld+json"))
        idx = raw.lower().find("ld+json")
        if idx >= 0:
            start = raw.rfind("<", 0, idx)
            end = raw.find(">", idx)
            tag = raw[start : end + 1] if start >= 0 and end > start else ""
            print("ldjson_tag", tag[:120])
        print("jsonld_blocks", len(blocks))
        for block in blocks:
            try:
                data = json.loads(block)
            except json.JSONDecodeError:
                print("bad_json")
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                print("type", item.get("@type"))
                print("keys", ",".join(sorted(item.keys())))
                brand = item.get("brand")
                if isinstance(brand, dict):
                    print("brand_keys", ",".join(sorted(brand.keys())))
                image = item.get("image")
                print("image_kind", type(image).__name__, "image_n", len(image) if isinstance(image, list) else (1 if image else 0))
        print("img_tags", len(re.findall(r"<img\\b", raw, flags=re.I)))


if __name__ == "__main__":
    main()
