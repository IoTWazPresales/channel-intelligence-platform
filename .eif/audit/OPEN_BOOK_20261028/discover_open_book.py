"""Read-only census of the ACZA open book on the connected database.

Writes discovery text to stdout. Refuses any connection whose current_database()
is not the name passed in, and sets the transaction read-only before the first
SELECT. Does not INSERT, UPDATE, or DELETE.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_FILE_DATE = re.compile(r"(20\d{2})(\d{2})(\d{2})")

from sqlalchemy import text

API_ROOT = Path(__file__).resolve().parents[3] / "apps" / "api"
sys.path.insert(0, str(API_ROOT))

from app.db.session_sync import SessionLocal  # noqa: E402


def main() -> None:
    expect = sys.argv[1] if len(sys.argv) > 1 else "cip"
    db = SessionLocal()
    try:
        db.execute(text("SET TRANSACTION READ ONLY"))
        name = db.execute(text("SELECT current_database()")).scalar()
        print(f"current_database={name}")
        if name != expect:
            raise SystemExit(f"refusing database {name!r}; expected {expect!r}")
        _report_dates(db)
        _open_book(db)
        _null_confirm(db)
    finally:
        db.rollback()
        db.close()


def _report_dates(db) -> None:
    print("\n=== staged_metadata keys on applied inbound_shipments jobs ===")
    rows = db.execute(
        text(
            """
            SELECT k, count(*)
            FROM import_job j
            CROSS JOIN LATERAL jsonb_object_keys(coalesce(j.staged_metadata, '{}'::jsonb)) AS k
            WHERE j.template_slug = 'inbound_shipments'
              AND j.status = 'completed'
            GROUP BY k
            ORDER BY count(*) DESC, k
            """
        )
    ).all()
    for key, n in rows:
        print(f"  {key}: {n}")

    print("\n=== ACZA jobs: file name, created_at, completed_at, report types ===")
    jobs = db.execute(
        text(
            """
            SELECT j.id,
                   j.tenant_id,
                   j.file_name,
                   j.created_at,
                   j.completed_at,
                   j.status,
                   j.stage,
                   array_agg(DISTINCT l.report_type ORDER BY l.report_type) AS report_types,
                   array_agg(DISTINCT l.source_sheet ORDER BY l.source_sheet) AS sheets,
                   count(l.id) AS lines
            FROM import_job j
            JOIN shipment_evidence_line l ON l.import_job_id = j.id
            WHERE j.template_slug = 'inbound_shipments'
              AND j.status = 'completed'
              AND l.report_type IN ('acza_workbook_shipped', 'acza_workbook_unship')
            GROUP BY j.id
            ORDER BY j.created_at, j.id
            """
        )
    ).all()
    print(f"applied_acza_jobs={len(jobs)}")
    dated = 0
    for row in jobs:
        match = _FILE_DATE.search(row.file_name or "")
        parsed = f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else "NONE"
        if match:
            dated += 1
        print(
            f"  job={row.id} tenant={row.tenant_id} file_date={parsed} "
            f"created={row.created_at} completed={row.completed_at} "
            f"status={row.status}/{row.stage} lines={row.lines} "
            f"types={list(row.report_types)} sheets={list(row.sheets)} file={row.file_name}"
        )
    print(f"acza_jobs_with_yyyymmdd_in_file_name={dated} of {len(jobs)}")

    print("\n=== shipment_evidence metadata keys and mail date presence (no addresses) ===")
    inner = db.execute(
        text(
            """
            SELECT k, count(*)
            FROM import_job j
            CROSS JOIN LATERAL jsonb_object_keys(
                CASE WHEN jsonb_typeof(j.staged_metadata->'shipment_evidence') = 'object'
                     THEN j.staged_metadata->'shipment_evidence' ELSE '{}'::jsonb END
            ) AS k
            WHERE j.template_slug = 'inbound_shipments' AND j.status = 'completed'
            GROUP BY k
            ORDER BY 2 DESC, 1
            """
        )
    ).all()
    for key, n in inner:
        print(f"  shipment_evidence.{key}: {n}")
    mail = db.execute(
        text(
            """
            SELECT j.id,
                   (j.staged_metadata->'mail'->>'received_at') AS received_at,
                   (j.staged_metadata->'mail'->>'attachment_name') AS attachment_name,
                   (j.staged_metadata->'mail' ? 'subject') AS has_subject
            FROM import_job j
            WHERE j.template_slug = 'inbound_shipments'
              AND j.status = 'completed'
              AND j.staged_metadata ? 'mail'
            ORDER BY j.id
            """
        )
    ).all()
    for row in mail:
        print(
            f"  job={row.id} mail_received_at={row.received_at} "
            f"attachment={row.attachment_name} has_subject={row.has_subject}"
        )

    print("\n=== every inbound job whose file name mentions ACZA, BOM, or Shipped ===")
    named = db.execute(
        text(
            """
            SELECT id, status, stage, created_at::date AS created, file_name
            FROM import_job
            WHERE template_slug = 'inbound_shipments'
              AND (
                    file_name ILIKE '%acza%'
                    OR file_name ILIKE '%bom%'
                    OR file_name ILIKE '%shipped%'
                  )
            ORDER BY id
            """
        )
    ).all()
    for row in named:
        print(f"  job={row.id} {row.status}/{row.stage} created={row.created} file={row.file_name}")

    print("\n=== source sheets on shipment evidence ===")
    sheets = db.execute(
        text(
            """
            SELECT coalesce(source_sheet, '(none)') AS sheet, report_type, count(*) AS lines
            FROM shipment_evidence_line
            GROUP BY 1, 2
            ORDER BY lines DESC
            """
        )
    ).all()
    for row in sheets:
        print(f"  sheet={row.sheet!r} type={row.report_type} lines={row.lines}")


def _open_book(db) -> None:
    print("\n=== open_order facts not on the newest applied Unship lines ===")
    rows = db.execute(
        text(
            """
            WITH unship AS (
                SELECT l.import_job_id,
                       j.tenant_id,
                       l.report_type,
                       coalesce(l.operating_unit, '') AS operating_unit,
                       lower(trim(coalesce(l.operating_unit, ''))) AS ou_key,
                       lower(trim(l.order_no)) AS order_key,
                       lower(trim(l.item_code)) AS item_key,
                       j.created_at,
                       j.completed_at,
                       j.file_name
                FROM shipment_evidence_line l
                JOIN import_job j ON j.id = l.import_job_id
                WHERE j.template_slug = 'inbound_shipments'
                  AND j.status = 'completed'
                  AND (
                        l.report_type = 'acza_workbook_unship'
                        OR lower(coalesce(l.source_sheet, '')) IN ('unship', 'unshipped')
                      )
                  AND l.order_no IS NOT NULL
                  AND l.item_code IS NOT NULL
                  AND trim(l.order_no) <> ''
                  AND trim(l.item_code) <> ''
            ),
            newest AS (
                SELECT DISTINCT ON (tenant_id, report_type, operating_unit)
                       tenant_id, report_type, operating_unit, import_job_id,
                       created_at, completed_at, file_name
                FROM unship
                ORDER BY tenant_id, report_type, operating_unit,
                         completed_at DESC NULLS LAST, created_at DESC, import_job_id DESC
            ),
            book AS (
                SELECT n.tenant_id, n.report_type, n.operating_unit, n.import_job_id,
                       u.ou_key, u.order_key, u.item_key
                FROM newest n
                JOIN unship u
                  ON u.import_job_id = n.import_job_id
                 AND u.tenant_id = n.tenant_id
                 AND u.report_type = n.report_type
                 AND u.operating_unit = n.operating_unit
            ),
            facts AS (
                SELECT f.id,
                       f.tenant_id,
                       f.report_type,
                       coalesce(f.operating_unit, '') AS operating_unit,
                       f.bill_to_raw,
                       coalesce(f.quantity, 0) AS quantity,
                       lower(trim(coalesce(f.operating_unit, ''))) AS ou_key,
                       lower(trim(f.order_no)) AS order_key,
                       lower(trim(f.item_code)) AS item_key,
                       (f.order_no IS NOT NULL AND f.item_code IS NOT NULL
                        AND trim(f.order_no) <> '' AND trim(f.item_code) <> '') AS keyed
                FROM fact_inbound_shipment f
                WHERE lower(f.line_state) = 'open_order'
            ),
            stale AS (
                SELECT f.*
                FROM facts f
                LEFT JOIN book b
                  ON b.tenant_id = f.tenant_id
                 AND b.report_type = f.report_type
                 AND b.operating_unit = f.operating_unit
                 AND b.ou_key = f.ou_key
                 AND b.order_key = f.order_key
                 AND b.item_key = f.item_key
                WHERE f.keyed
                  AND b.import_job_id IS NULL
            )
            SELECT tenant_id, report_type, operating_unit, coalesce(bill_to_raw, '(blank)') AS bill_to,
                   count(*) AS lines, sum(quantity) AS units
            FROM stale
            GROUP BY tenant_id, report_type, operating_unit, coalesce(bill_to_raw, '(blank)')
            ORDER BY units DESC, lines DESC, bill_to
            """
        )
    ).all()
    total_lines = 0
    total_units = 0
    for row in rows:
        total_lines += int(row.lines)
        total_units += float(row.units or 0)
        print(
            f"  tenant={row.tenant_id} report_type={row.report_type} ou={row.operating_unit!r} "
            f"bill_to={row.bill_to} lines={row.lines} units={row.units}"
        )
    print(f"stale_keyed_lines={total_lines} stale_keyed_units={total_units}")

    extra = db.execute(
        text(
            """
            SELECT
              count(*) FILTER (WHERE lower(line_state) = 'open_order') AS open_lines,
              coalesce(sum(quantity) FILTER (WHERE lower(line_state) = 'open_order'), 0) AS open_units,
              count(*) FILTER (
                WHERE lower(line_state) = 'open_order'
                  AND (order_no IS NULL OR item_code IS NULL OR trim(order_no) = '' OR trim(item_code) = '')
              ) AS open_unkeyed_lines,
              count(*) FILTER (WHERE lower(line_state) = 'shipped') AS shipped_lines,
              coalesce(sum(quantity) FILTER (WHERE lower(line_state) = 'shipped'), 0) AS shipped_units,
              count(*) FILTER (
                WHERE lower(line_state) = 'shipped' AND ship_confirm_date IS NULL
              ) AS shipped_null_confirm_lines,
              coalesce(sum(quantity) FILTER (
                WHERE lower(line_state) = 'shipped' AND ship_confirm_date IS NULL
              ), 0) AS shipped_null_confirm_units
            FROM fact_inbound_shipment
            """
        )
    ).one()
    print(
        f"all_open_lines={extra.open_lines} all_open_units={extra.open_units} "
        f"open_unkeyed_lines={extra.open_unkeyed_lines} "
        f"shipped_lines={extra.shipped_lines} shipped_units={extra.shipped_units} "
        f"shipped_null_confirm_lines={extra.shipped_null_confirm_lines} "
        f"shipped_null_confirm_units={extra.shipped_null_confirm_units}"
    )

    print("\n=== newest unship job per scope ===")
    newest = db.execute(
        text(
            """
            WITH unship AS (
                SELECT l.import_job_id, j.tenant_id, l.report_type,
                       coalesce(l.operating_unit, '') AS operating_unit,
                       j.completed_at, j.created_at, j.file_name,
                       count(*) AS lines,
                       coalesce(sum(l.quantity), 0) AS units
                FROM shipment_evidence_line l
                JOIN import_job j ON j.id = l.import_job_id
                WHERE j.status = 'completed'
                  AND (
                        l.report_type = 'acza_workbook_unship'
                        OR lower(coalesce(l.source_sheet, '')) IN ('unship', 'unshipped')
                      )
                GROUP BY l.import_job_id, j.tenant_id, l.report_type,
                         coalesce(l.operating_unit, ''), j.completed_at, j.created_at, j.file_name
            )
            SELECT DISTINCT ON (tenant_id, report_type, operating_unit)
                   *
            FROM unship
            ORDER BY tenant_id, report_type, operating_unit,
                     completed_at DESC NULLS LAST, created_at DESC, import_job_id DESC
            """
        )
    ).all()
    for row in newest:
        print(
            f"  job={row.import_job_id} tenant={row.tenant_id} type={row.report_type} "
            f"ou={row.operating_unit!r} lines={row.lines} units={row.units} "
            f"completed={row.completed_at} file={row.file_name}"
        )


def _null_confirm(db) -> None:
    print("\n=== shipped facts with null ship_confirm_date ===")
    rows = db.execute(
        text(
            """
            SELECT f.report_type, coalesce(f.source_sheet, '') AS sheet,
                   coalesce(f.bill_to_raw, '(blank)') AS bill_to,
                   f.import_job_id, count(*) AS lines, coalesce(sum(f.quantity), 0) AS units
            FROM fact_inbound_shipment f
            WHERE lower(f.line_state) = 'shipped'
              AND f.ship_confirm_date IS NULL
            GROUP BY f.report_type, coalesce(f.source_sheet, ''), coalesce(f.bill_to_raw, '(blank)'),
                     f.import_job_id
            ORDER BY units DESC
            """
        )
    ).all()
    for row in rows:
        print(
            f"  job={row.import_job_id} type={row.report_type} sheet={row.sheet!r} "
            f"bill_to={row.bill_to} lines={row.lines} units={row.units}"
        )
    print("\n=== open_order facts by job ===")
    by_job = db.execute(
        text(
            """
            SELECT f.import_job_id, j.file_name, f.report_type,
                   count(*) AS lines, coalesce(sum(f.quantity), 0) AS units
            FROM fact_inbound_shipment f
            LEFT JOIN import_job j ON j.id = f.import_job_id
            WHERE lower(f.line_state) = 'open_order'
            GROUP BY f.import_job_id, j.file_name, f.report_type
            ORDER BY lines DESC
            """
        )
    ).all()
    for row in by_job:
        print(
            f"  job={row.import_job_id} type={row.report_type} lines={row.lines} "
            f"units={row.units} file={row.file_name}"
        )
    print("\n=== open_order source_key shared across jobs ===")
    shared = db.execute(
        text(
            """
            SELECT count(*) AS keys
            FROM (
                SELECT source_key
                FROM fact_inbound_shipment
                WHERE lower(line_state) = 'open_order'
                GROUP BY source_key
                HAVING count(DISTINCT import_job_id) > 1
            ) s
            """
        )
    ).scalar()
    print(f"open_source_keys_shared_by_jobs={shared}")


if __name__ == "__main__":
    main()
