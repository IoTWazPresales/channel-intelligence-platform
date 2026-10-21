"""N-0110 repair: read-only. Raw files behind applied CST jobs, and fact rows per job.

usage: python probe_files.py <dbname>
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_collapse import API, url_for  # noqa: E402

import psycopg  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    db = sys.argv[1]
    s = get_settings()
    roots = [getattr(s, a) for a in dir(s) if "storage" in a.lower() and isinstance(getattr(s, a, None), str)]
    print("storage settings", roots)
    with psycopg.connect(url_for(db)) as conn:
        conn.read_only = True
        q = lambda sql: conn.execute(sql).fetchall()  # noqa: E731
        print("current_database()", q("select current_database()")[0][0])
        rows = q(
            """
            select j.id, j.file_name, j.template_slug, j.status, r.storage_key, r.checksum,
                   (select count(*) from fact_customer_sellthrough f where f.import_job_id = j.id) facts,
                   (select coalesce(sum(units_sold),0) from fact_customer_sellthrough f where f.import_job_id = j.id) units
            from import_job j left join raw_file_metadata r on r.job_id = j.id
            where j.id in (select distinct import_job_id from import_customer_sellthrough_staging_line where apply_status='applied')
            order by j.id, r.id
            """
        )
        for r in rows:
            key = r[4]
            exists = None
            if key:
                for base in [API / "storage", API]:
                    if (base / key).exists():
                        exists = str(base / key)
                        break
            print(r[:4], (r[5] or "")[:12], "facts", r[6], "units", r[7], "file", "yes" if exists else f"no ({key})")
        print("facts by job null", q("select count(*) from fact_customer_sellthrough where import_job_id is null"))
        print("fact keys by site part", q("select split_part(source_key, ':', 3) = '0' as site0, count(*) from fact_customer_sellthrough group by 1"))


if __name__ == "__main__":
    main()
