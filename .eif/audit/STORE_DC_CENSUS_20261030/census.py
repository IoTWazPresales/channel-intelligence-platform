"""Read-only store / DC census. Writes REPORT.md and queries.sql beside this file."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from app.core.config import get_settings

OUT = Path(__file__).resolve().parent
CUSTOMER_KEY_RE = re.compile(
    r"(store|site|outlet|shop|address|suburb|city|town|province|region|"
    r"postal|post[_ ]?code|zip|latitude|longitude|(^|[^a-z])lat([^a-z]|$)|"
    r"(^|[^a-z])lng([^a-z]|$)|(^|[^a-z])lon([^a-z]|$)|coord|gps|geocode|location)",
    re.I,
)
DIST_KEY_RE = re.compile(
    r"(branch|warehouse|(^|[^a-z])dc([^a-z]|$)|depot|location|(^|[^a-z])loc([^a-z]|$)|"
    r"site|store|plant|godown|address)",
    re.I,
)
SCOPE_COL_RE = re.compile(r"(store|location|site|branch|outlet)", re.I)
QUERIES: list[tuple[str, str]] = []


def record(name: str, sql: str) -> str:
    QUERIES.append((name, sql.strip() + "\n"))
    return sql


def ident(name: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise SystemExit(f"unexpected column name: {name}")
    return name


def libpq_dsn(url: str) -> str:
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    return url


def num(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        if value == value.to_integral():
            return f"{int(value):,}"
        return f"{value:,.2f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def pct(part, whole) -> str:
    if whole in (None, 0):
        return ""
    return f"{(Decimal(part or 0) / Decimal(whole) * 100):.1f}%"


def cell(value) -> str:
    if value is None:
        text = ""
    elif isinstance(value, (int, float, Decimal)):
        text = num(value)
    else:
        text = str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def md_table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_No rows._\n"
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(cell(v) for v in row) + " |")
    return "\n".join(out) + "\n"


def main() -> None:
    dsn = libpq_dsn(get_settings().database_url_sync)
    conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
    conn.execute("SET default_transaction_read_only = on")
    conn.execute("SET lock_timeout = '5s'")
    conn.execute("SET statement_timeout = '120s'")
    conn.execute("SET TIME ZONE 'UTC'")

    def run(name: str, sql: str, params=None, timeout_ms: int = 300000):
        record(name, sql)
        conn.execute("SELECT set_config('statement_timeout', %s, false)", (str(timeout_ms),))
        print(f"run {name}", flush=True)
        return conn.execute(sql, params).fetchall()

    identity = run(
        "00_identity",
        "SELECT current_database() AS current_database, current_user AS current_user",
        timeout_ms=30000,
    )[0]
    print(identity["current_database"], identity["current_user"], flush=True)
    if identity["current_database"] != "cip":
        raise SystemExit("refusing because current_database() is not cip")

    columns = run(
        "01_columns",
        """
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN (
            'fact_customer_sellthrough', 'customer_location',
            'import_customer_sellthrough_staging_line', 'import_job', 'source_definition',
            'fact_sales_sellout', 'fact_inventory_distributor', 'fact_returns',
            'import_distributor_si_staging_line', 'distributor_location',
            'fact_inbound_shipment', 'cpor_case', 'cpor_case_line',
            'dim_customer', 'dim_distributor'
          )
        ORDER BY table_name, ordinal_position
        """,
        timeout_ms=60000,
    )
    by_table: dict[str, set[str]] = defaultdict(set)
    for row in columns:
        by_table[row["table_name"]].add(row["column_name"])

    def has(table: str, column: str) -> bool:
        return column in by_table[table]

    job_customer = "customer_id" if has("import_job", "customer_id") else None
    job_source = "source_definition_id" if has("import_job", "source_definition_id") else None
    source_name = "name" if has("source_definition", "name") else None
    location_fact_cols = [
        f"{row['table_name']}.{row['column_name']}"
        for row in columns
        if row["table_name"] in ("fact_sales_sellout", "fact_inventory_distributor", "fact_returns")
        and SCOPE_COL_RE.search(row["column_name"])
    ]

    grain = run(
        "A0_period_grain",
        """
        SELECT COALESCE(period_grain, '(null)') AS period_grain,
               COALESCE(period_type, '(null)') AS period_type,
               count(*) AS rows,
               count(*) FILTER (WHERE week_start_date IS NOT NULL) AS with_week_start,
               count(*) FILTER (WHERE nullif(btrim(site_label), '') IS NOT NULL) AS with_site_label,
               count(*) FILTER (WHERE customer_location_id IS NOT NULL) AS with_location_id,
               count(*) FILTER (WHERE reported_soh IS NOT NULL) AS with_reported_soh,
               count(*) FILTER (
                 WHERE period_start_date IS NOT NULL
                   AND EXTRACT(ISODOW FROM period_start_date) = 1
               ) AS period_on_monday
        FROM fact_customer_sellthrough
        GROUP BY 1, 2
        ORDER BY rows DESC
        """,
    )
    customer_summary = run(
        "A1_A2_A3_C9_customer_store",
        """
        WITH marked AS (
          SELECT
            customer_id,
            nullif(btrim(site_label), '') AS site_label,
            customer_location_id,
            period_start_date,
            units_sold,
            reported_soh,
            in_transit_units,
            on_order_units,
            (
              nullif(btrim(site_label), '') IS NOT NULL
              OR customer_location_id IS NOT NULL
            ) AS is_store,
            CASE
              WHEN week_start_date IS NOT NULL THEN week_start_date
              WHEN lower(coalesce(period_grain, '')) IN ('week', 'w') THEN period_start_date
              WHEN lower(coalesce(period_type, '')) IN ('week', 'w', 'weekly') THEN period_start_date
              ELSE NULL
            END AS explicit_week,
            COALESCE(week_start_date, period_start_date) AS period_bucket,
            COALESCE(
              nullif(btrim(site_label), ''),
              CASE
                WHEN customer_location_id IS NOT NULL THEN 'loc:' || customer_location_id::text
              END
            ) AS store_key
          FROM fact_customer_sellthrough
        ),
        base AS (
          SELECT
            customer_id,
            count(*) AS fact_rows,
            count(*) FILTER (WHERE site_label IS NOT NULL) AS rows_with_site_label,
            count(DISTINCT site_label) AS distinct_site_labels,
            count(*) FILTER (WHERE customer_location_id IS NOT NULL) AS rows_with_location_id,
            count(DISTINCT customer_location_id) AS distinct_locations,
            count(*) FILTER (WHERE is_store) AS store_rows,
            count(*) FILTER (WHERE is_store AND explicit_week IS NOT NULL) AS explicit_week_rows,
            count(*) FILTER (
              WHERE is_store AND period_start_date IS NOT NULL
                AND EXTRACT(ISODOW FROM period_start_date) = 1
            ) AS store_periods_on_monday,
            min(explicit_week) FILTER (WHERE is_store) AS first_explicit_week,
            max(explicit_week) FILTER (WHERE is_store) AS last_explicit_week,
            count(DISTINCT explicit_week) FILTER (WHERE is_store) AS explicit_weeks,
            min(period_bucket) FILTER (WHERE is_store) AS first_store_period,
            max(period_bucket) FILTER (WHERE is_store) AS last_store_period,
            count(DISTINCT period_bucket) FILTER (WHERE is_store) AS store_periods,
            count(*) FILTER (WHERE is_store AND reported_soh IS NOT NULL) AS store_rows_with_soh,
            count(*) FILTER (WHERE is_store AND in_transit_units IS NOT NULL) AS store_rows_with_in_transit,
            count(*) FILTER (WHERE is_store AND on_order_units IS NOT NULL) AS store_rows_with_on_order,
            count(*) FILTER (
              WHERE is_store AND explicit_week IS NOT NULL AND reported_soh IS NOT NULL
            ) AS explicit_week_rows_with_soh,
            count(*) FILTER (
              WHERE is_store AND explicit_week IS NOT NULL AND in_transit_units IS NOT NULL
            ) AS explicit_week_rows_with_in_transit,
            count(*) FILTER (
              WHERE is_store AND explicit_week IS NOT NULL AND on_order_units IS NOT NULL
            ) AS explicit_week_rows_with_on_order,
            count(*) FILTER (
              WHERE is_store AND units_sold IS NOT NULL AND units_sold <> 0 AND reported_soh IS NOT NULL
            ) AS store_rows_units_and_soh
          FROM marked
          GROUP BY customer_id
        ),
        label_weeks AS (
          SELECT customer_id, site_label,
                 count(DISTINCT explicit_week) AS weeks_present,
                 count(*) AS row_n
          FROM marked
          WHERE is_store AND site_label IS NOT NULL AND explicit_week IS NOT NULL
          GROUP BY customer_id, site_label
        ),
        cust_weeks AS (
          SELECT customer_id, count(DISTINCT explicit_week) AS n_weeks
          FROM marked
          WHERE is_store AND explicit_week IS NOT NULL
          GROUP BY customer_id
        ),
        stability AS (
          SELECT l.customer_id,
                 count(*) AS labels_with_a_week,
                 count(*) FILTER (WHERE l.weeks_present::numeric / c.n_weeks >= 0.8) AS stable_labels,
                 count(*) FILTER (WHERE l.weeks_present = 1) AS labels_in_one_week,
                 count(*) FILTER (WHERE l.row_n = 1) AS labels_on_one_row
          FROM label_weeks l
          JOIN cust_weeks c USING (customer_id)
          GROUP BY l.customer_id
        ),
        store_weeks AS (
          SELECT customer_id, store_key, explicit_week,
                 bool_or(reported_soh IS NOT NULL) AS has_soh,
                 bool_or(units_sold IS NOT NULL AND units_sold <> 0) AS has_units
          FROM marked
          WHERE is_store AND store_key IS NOT NULL AND explicit_week IS NOT NULL
          GROUP BY customer_id, store_key, explicit_week
        ),
        week_both AS (
          SELECT customer_id,
                 count(*) AS store_weeks,
                 count(*) FILTER (WHERE has_soh AND has_units) AS store_weeks_units_and_soh,
                 count(*) FILTER (WHERE has_soh) AS store_weeks_with_soh
          FROM store_weeks
          GROUP BY customer_id
        )
        SELECT c.id AS customer_id, c.name AS customer_name, c.code AS customer_code,
               b.fact_rows, b.rows_with_site_label, b.distinct_site_labels,
               b.rows_with_location_id, b.distinct_locations, b.store_rows, b.explicit_week_rows,
               b.store_periods_on_monday, b.first_explicit_week, b.last_explicit_week, b.explicit_weeks,
               b.first_store_period, b.last_store_period, b.store_periods,
               b.store_rows_with_soh, b.store_rows_with_in_transit, b.store_rows_with_on_order,
               b.explicit_week_rows_with_soh, b.explicit_week_rows_with_in_transit,
               b.explicit_week_rows_with_on_order, b.store_rows_units_and_soh,
               COALESCE(s.labels_with_a_week, 0) AS labels_with_a_week,
               COALESCE(s.stable_labels, 0) AS stable_labels,
               COALESCE(s.labels_in_one_week, 0) AS labels_in_one_week,
               COALESCE(s.labels_on_one_row, 0) AS labels_on_one_row,
               COALESCE(w.store_weeks, 0) AS store_weeks,
               COALESCE(w.store_weeks_units_and_soh, 0) AS store_weeks_units_and_soh,
               COALESCE(w.store_weeks_with_soh, 0) AS store_weeks_with_soh
        FROM base b
        JOIN dim_customer c ON c.id = b.customer_id
        LEFT JOIN stability s ON s.customer_id = b.customer_id
        LEFT JOIN week_both w ON w.customer_id = b.customer_id
        ORDER BY c.name
        """,
        timeout_ms=600000,
    )
    variants = run(
        "A3_label_variant_groups",
        """
        WITH labels AS (
          SELECT DISTINCT customer_id,
                 nullif(btrim(site_label), '') AS site_label,
                 lower(regexp_replace(btrim(site_label), '[^[:alnum:]]+', '', 'g')) AS norm
          FROM fact_customer_sellthrough
          WHERE nullif(btrim(site_label), '') IS NOT NULL
        )
        SELECT c.id AS customer_id, c.name AS customer_name, l.norm,
               count(*) AS label_forms,
               string_agg(l.site_label, ' | ' ORDER BY l.site_label) AS forms
        FROM labels l
        JOIN dim_customer c ON c.id = l.customer_id
        WHERE l.norm <> ''
        GROUP BY c.id, c.name, l.norm
        HAVING count(*) > 1
        ORDER BY c.name, l.norm
        """,
        timeout_ms=600000,
    )
    locations = run(
        "A4_customer_location",
        """
        SELECT c.id AS customer_id, c.name AS customer_name, cl.location_type,
               COALESCE(r.name, '(none)') AS region,
               count(*) AS location_rows,
               count(*) FILTER (WHERE linked.customer_location_id IS NOT NULL) AS linked_to_facts,
               COALESCE(sum(linked.fact_rows), 0) AS fact_rows
        FROM customer_location cl
        JOIN dim_customer c ON c.id = cl.customer_id
        LEFT JOIN dim_region r ON r.id = cl.region_id
        LEFT JOIN (
          SELECT customer_location_id, count(*) AS fact_rows
          FROM fact_customer_sellthrough
          WHERE customer_location_id IS NOT NULL
          GROUP BY customer_location_id
        ) linked ON linked.customer_location_id = cl.id
        GROUP BY c.id, c.name, cl.location_type, r.name
        ORDER BY c.name, cl.location_type, region
        """,
    )

    if job_customer:
        staging_customer_expr = f"COALESCE(j.{ident(job_customer)}, s.resolved_customer_id)"
    else:
        staging_customer_expr = "s.resolved_customer_id"
    if job_source and source_name:
        source_select = f"COALESCE(sd.{ident(source_name)}, '(no source)') AS source_name"
        source_join = f"LEFT JOIN source_definition sd ON sd.id = j.{ident(job_source)}"
    else:
        source_select = "'(customer file)' AS source_name"
        source_join = ""
    fact_keys = run(
        "A5_fact_raw_source_row_keys",
        """
        WITH den AS (
          SELECT customer_id, count(*) AS nrows
          FROM fact_customer_sellthrough
          GROUP BY customer_id
        ),
        keys AS (
          SELECT f.customer_id, e.key,
                 count(*) FILTER (
                   WHERE nullif(btrim(f.raw_source_row ->> e.key), '') IS NOT NULL
                 ) AS filled
          FROM fact_customer_sellthrough f
          CROSS JOIN LATERAL jsonb_object_keys(f.raw_source_row) AS e(key)
          WHERE jsonb_typeof(f.raw_source_row) = 'object'
          GROUP BY f.customer_id, e.key
        )
        SELECT c.name AS customer_name, k.key, k.filled, d.nrows
        FROM keys k
        JOIN den d ON d.customer_id = k.customer_id
        JOIN dim_customer c ON c.id = k.customer_id
        ORDER BY c.name, k.key
        """,
        timeout_ms=600000,
    )
    staging_keys = run(
        "A5_staging_raw_keys",
        f"""
        WITH lines AS (
          SELECT {staging_customer_expr} AS customer_id,
                 {source_select},
                 s.raw_row_payload, s.raw_location_token, s.site_label
          FROM import_customer_sellthrough_staging_line s
          JOIN import_job j ON j.id = s.import_job_id
          {source_join}
        ),
        den AS (
          SELECT customer_id, source_name, count(*) AS nrows,
                 count(*) FILTER (WHERE nullif(btrim(raw_location_token), '') IS NOT NULL) AS location_token_filled,
                 count(*) FILTER (WHERE nullif(btrim(site_label), '') IS NOT NULL) AS site_label_filled
          FROM lines
          GROUP BY customer_id, source_name
        ),
        keys AS (
          SELECT l.customer_id, l.source_name, e.key,
                 count(*) FILTER (
                   WHERE nullif(btrim(l.raw_row_payload ->> e.key), '') IS NOT NULL
                 ) AS filled
          FROM lines l
          CROSS JOIN LATERAL jsonb_object_keys(l.raw_row_payload) AS e(key)
          WHERE jsonb_typeof(l.raw_row_payload) = 'object'
          GROUP BY l.customer_id, l.source_name, e.key
        )
        SELECT COALESCE(c.name, '(unresolved customer)') AS customer_name,
               d.source_name, d.nrows, d.location_token_filled, d.site_label_filled,
               k.key, k.filled
        FROM den d
        LEFT JOIN keys k ON k.customer_id IS NOT DISTINCT FROM d.customer_id
                        AND k.source_name = d.source_name
        LEFT JOIN dim_customer c ON c.id = d.customer_id
        ORDER BY customer_name, d.source_name, k.key
        """,
        timeout_ms=600000,
    )
    dist_locations = run(
        "B6_distributor_location",
        """
        SELECT d.name AS distributor_name, dl.location_type,
               count(*) AS location_rows,
               count(*) FILTER (WHERE nullif(btrim(dl.address_summary), '') IS NOT NULL) AS with_address,
               count(*) FILTER (WHERE nullif(btrim(dl.address_summary), '') IS NULL) AS without_address
        FROM distributor_location dl
        JOIN dim_distributor d ON d.id = dl.distributor_id
        GROUP BY d.name, dl.location_type
        ORDER BY d.name, dl.location_type
        """,
    )
    dist_raw = run(
        "B7_distributor_staging_keys",
        """
        WITH lines AS (
          SELECT resolved_distributor_id AS distributor_id, quantity_sold, stock_on_hand, raw_row_payload
          FROM import_distributor_si_staging_line
        ),
        den AS (
          SELECT distributor_id,
                 count(*) FILTER (WHERE quantity_sold IS NOT NULL) AS sellout_rows,
                 count(*) FILTER (WHERE stock_on_hand IS NOT NULL) AS inventory_rows
          FROM lines
          GROUP BY distributor_id
        ),
        keys AS (
          SELECT l.distributor_id, e.key,
                 count(*) FILTER (
                   WHERE l.quantity_sold IS NOT NULL
                     AND nullif(btrim(l.raw_row_payload ->> e.key), '') IS NOT NULL
                 ) AS sellout_filled,
                 count(*) FILTER (
                   WHERE l.stock_on_hand IS NOT NULL
                     AND nullif(btrim(l.raw_row_payload ->> e.key), '') IS NOT NULL
                 ) AS inventory_filled
          FROM lines l
          CROSS JOIN LATERAL jsonb_object_keys(l.raw_row_payload) AS e(key)
          WHERE jsonb_typeof(l.raw_row_payload) = 'object'
          GROUP BY l.distributor_id, e.key
        )
        SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name,
               den.sellout_rows, den.inventory_rows, k.key, k.sellout_filled, k.inventory_filled
        FROM den
        LEFT JOIN keys k ON k.distributor_id IS NOT DISTINCT FROM den.distributor_id
        LEFT JOIN dim_distributor d ON d.id = den.distributor_id
        ORDER BY distributor_name, k.key
        """,
        timeout_ms=600000,
    )
    inventory = run(
        "B7_inventory_facts",
        """
        SELECT d.name AS distributor_name, count(*) AS inventory_rows,
               count(DISTINCT f.as_of_date) AS as_of_dates,
               count(DISTINCT f.product_id) AS products,
               min(f.as_of_date) AS first_as_of, max(f.as_of_date) AS last_as_of
        FROM fact_inventory_distributor f
        JOIN dim_distributor d ON d.id = f.distributor_id
        GROUP BY d.name
        ORDER BY d.name
        """,
    )
    sellout_facts = run(
        "B7_sellout_fact_distributors",
        """
        SELECT d.name AS distributor_name, count(*) AS sellout_rows
        FROM fact_sales_sellout f
        JOIN dim_distributor d ON d.id = f.distributor_id
        GROUP BY d.name
        ORDER BY d.name
        """,
    )
    matching_dist_keys = sorted({row["key"] for row in dist_raw if row["key"] and DIST_KEY_RE.search(row["key"])})
    dist_values: list[dict] = []
    dist_stability: list[dict] = []
    if matching_dist_keys:
        dist_values = run(
            "B7_location_like_distinct_values",
            """
            WITH exploded AS (
              SELECT s.resolved_distributor_id AS distributor_id, e.key,
                     nullif(btrim(s.raw_row_payload ->> e.key), '') AS value,
                     (s.quantity_sold IS NOT NULL) AS is_sellout,
                     (s.stock_on_hand IS NOT NULL) AS is_inventory
              FROM import_distributor_si_staging_line s
              CROSS JOIN LATERAL jsonb_object_keys(s.raw_row_payload) AS e(key)
              WHERE jsonb_typeof(s.raw_row_payload) = 'object'
                AND e.key = ANY(%s)
            ),
            counted AS (
              SELECT distributor_id, key, value,
                     count(*) FILTER (WHERE is_sellout) AS sellout_rows,
                     count(*) FILTER (WHERE is_inventory) AS inventory_rows
              FROM exploded
              WHERE value IS NOT NULL
              GROUP BY distributor_id, key, value
            ),
            ranked AS (
              SELECT *,
                     row_number() OVER (
                       PARTITION BY distributor_id, key
                       ORDER BY (sellout_rows + inventory_rows) DESC, value
                     ) AS rn,
                     count(*) OVER (PARTITION BY distributor_id, key) AS distinct_values
              FROM counted
            )
            SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name,
                   r.key, r.value, r.sellout_rows, r.inventory_rows, r.distinct_values
            FROM ranked r
            LEFT JOIN dim_distributor d ON d.id = r.distributor_id
            WHERE r.rn <= 25
            ORDER BY distributor_name, r.key, r.rn
            """,
            params=(matching_dist_keys,),
            timeout_ms=600000,
        )
        dist_stability = run(
            "B7_location_value_stability",
            """
            WITH exploded AS (
              SELECT s.resolved_distributor_id AS distributor_id, e.key,
                     nullif(btrim(s.raw_row_payload ->> e.key), '') AS value,
                     (s.stock_on_hand IS NOT NULL) AS is_inventory
              FROM import_distributor_si_staging_line s
              CROSS JOIN LATERAL jsonb_object_keys(s.raw_row_payload) AS e(key)
              WHERE jsonb_typeof(s.raw_row_payload) = 'object'
                AND e.key = ANY(%s)
            ),
            counted AS (
              SELECT distributor_id, key, value,
                     count(*) FILTER (WHERE is_inventory) AS inventory_rows
              FROM exploded
              WHERE value IS NOT NULL
              GROUP BY distributor_id, key, value
            )
            SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name,
                   c.key,
                   count(*) AS distinct_values,
                   count(*) FILTER (WHERE c.inventory_rows <= 1) AS values_on_one_inventory_row
            FROM counted c
            LEFT JOIN dim_distributor d ON d.id = c.distributor_id
            GROUP BY d.name, c.key
            ORDER BY distributor_name, c.key
            """,
            params=(matching_dist_keys,),
            timeout_ms=600000,
        )
    ship_to = run(
        "B8_ship_to_raw",
        """
        SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name,
               COALESCE(nullif(btrim(f.ship_to_raw), ''), '(blank)') AS ship_to_raw,
               count(*) AS lines, COALESCE(sum(f.quantity), 0) AS units
        FROM fact_inbound_shipment f
        LEFT JOIN dim_distributor d ON d.id = COALESCE(f.resolved_distributor_id, f.distributor_id)
        GROUP BY d.name, COALESCE(nullif(btrim(f.ship_to_raw), ''), '(blank)')
        ORDER BY d.name NULLS LAST, units DESC, ship_to_raw
        """,
        timeout_ms=600000,
    )
    lead_time = run(
        "C10_ship_confirm_and_pod",
        """
        SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name,
               f.line_state, count(*) AS lines,
               count(*) FILTER (
                 WHERE f.ship_confirm_date IS NOT NULL AND f.pod_date IS NOT NULL
               ) AS lines_with_both,
               min(f.ship_confirm_date) FILTER (
                 WHERE f.ship_confirm_date IS NOT NULL AND f.pod_date IS NOT NULL
               ) AS min_ship_confirm,
               max(f.ship_confirm_date) FILTER (
                 WHERE f.ship_confirm_date IS NOT NULL AND f.pod_date IS NOT NULL
               ) AS max_ship_confirm,
               min(f.pod_date) FILTER (
                 WHERE f.ship_confirm_date IS NOT NULL AND f.pod_date IS NOT NULL
               ) AS min_pod,
               max(f.pod_date) FILTER (
                 WHERE f.ship_confirm_date IS NOT NULL AND f.pod_date IS NOT NULL
               ) AS max_pod
        FROM fact_inbound_shipment f
        LEFT JOIN dim_distributor d ON d.id = COALESCE(f.resolved_distributor_id, f.distributor_id)
        GROUP BY d.name, f.line_state
        ORDER BY d.name NULLS LAST, f.line_state
        """,
        timeout_ms=600000,
    )
    cpor_cols = [
        row for row in columns
        if row["table_name"] in ("cpor_case", "cpor_case_line") and SCOPE_COL_RE.search(row["column_name"])
    ]
    cpor_json_keys = run(
        "C11_cpor_json_keys",
        """
        SELECT 'cpor_case_line.source_snapshot_json' AS source, e.key, count(*) AS rows_with_key
        FROM cpor_case_line
        CROSS JOIN LATERAL jsonb_object_keys(source_snapshot_json) AS e(key)
        WHERE jsonb_typeof(source_snapshot_json) = 'object'
        GROUP BY e.key
        UNION ALL
        SELECT 'cpor_case_line.cost_evidence_json', e.key, count(*)
        FROM cpor_case_line
        CROSS JOIN LATERAL jsonb_object_keys(cost_evidence_json) AS e(key)
        WHERE jsonb_typeof(cost_evidence_json) = 'object'
        GROUP BY e.key
        ORDER BY 1, 2
        """,
    )
    cpor_counts = run(
        "C11_cpor_counts",
        """
        SELECT (SELECT count(*) FROM cpor_case) AS cases,
               (SELECT count(*) FROM cpor_case_line) AS case_lines,
               (SELECT count(*) FROM cpor_case WHERE notes ~* '(store|location|site)') AS cases_notes_mention,
               (SELECT count(*) FROM cpor_case_line WHERE remark ~* '(store|location|site)') AS lines_remark_mention
        """,
    )
    (OUT / "queries.sql").write_text(
        "-- Read-only census. First statement prints current_database() and must be cip.\n"
        + "\n".join(f"-- {name}\n{sql}\n" for name, sql in QUERIES),
        encoding="utf-8",
    )
    write_report(
        identity=identity,
        grain=grain,
        customer_summary=customer_summary,
        variants=variants,
        locations=locations,
        fact_keys=fact_keys,
        staging_keys=staging_keys,
        location_fact_cols=location_fact_cols,
        dist_locations=dist_locations,
        dist_raw=dist_raw,
        dist_values=dist_values,
        dist_stability=dist_stability,
        inventory=inventory,
        sellout_facts=sellout_facts,
        ship_to=ship_to,
        lead_time=lead_time,
        cpor_cols=cpor_cols,
        cpor_json_keys=cpor_json_keys,
        cpor_counts=cpor_counts,
        job_customer=job_customer,
    )
    print(f"wrote {OUT / 'REPORT.md'}", flush=True)


def write_report(**kw) -> None:
    customers = kw["customer_summary"]
    variants = kw["variants"]
    locations = kw["locations"]
    loc_by_customer: dict[int, int] = defaultdict(int)
    for row in locations:
        loc_by_customer[row["customer_id"]] += row["location_rows"]
    variant_by_customer: dict[int, list] = defaultdict(list)
    for row in variants:
        variant_by_customer[row["customer_id"]].append(row)
    identity = kw["identity"]
    lines: list[str] = []
    a = lines.append
    a("# Store and distribution-centre census")
    a("")
    a(f"Database `{identity['current_database']}` as `{identity['current_user']}`, read at {datetime.now().strftime('%Y-%m-%d %H:%M')}.")
    a("Branch at handover: `feat/ns-2-brief-nav-collapse` @ `08031f86`. Session was read-only (`default_transaction_read_only=on`). No migration and no master writes.")
    a("")
    a("Display name is `dim_customer.name`. A store-grain fact row has a non-blank `site_label` or a `customer_location_id`. An explicit week is `week_start_date`, or `period_start_date` when `period_grain` or `period_type` is week. The 80% test uses that customer's distinct explicit weeks. A one-week label appears in exactly one of those weeks. Variant groups are site labels that match after lowercasing and removing every character that is not a letter or digit.")
    a("")
    a("READY for a customer requires at least 8 explicit weeks, at least one site label in 80% or more of those weeks, one-week labels under 20% of distinct site labels, no variant groups, and reported SOH on at least half of explicit-week store rows. PARTIAL means a site label, a fact location id, or a `customer_location` row exists and READY fails. NONE means account-level sell-through only.")
    a("")
    a("READY for a distributor requires a location-like staging column filled on at least half of inventory staging rows (`stock_on_hand` not null), fewer than half of that column's distinct values appearing on only one inventory row, and at least 4 inventory as-of dates. A location master, any filled location-like raw column, or a non-blank `ship_to_raw` is otherwise PARTIAL. NONE means distributor-level facts only.")
    a("")
    a("## A0. Period grain on fact_customer_sellthrough")
    a("")
    a(md_table(
        ["period_grain", "period_type", "rows", "week_start", "site_label", "location_id", "reported_soh", "period on Monday"],
        [[r["period_grain"], r["period_type"], r["rows"], r["with_week_start"], r["with_site_label"], r["with_location_id"], r["with_reported_soh"], r["period_on_monday"]] for r in kw["grain"]],
    ))
    a("## A1. Customer stores")
    a("")
    a(md_table(
        ["Customer", "Rows", "Rows with site_label", "Distinct site_labels", "Rows with location id", "Distinct locations", "First explicit week", "Last explicit week", "Explicit weeks", "First store period", "Last store period", "Store periods"],
        [[r["customer_name"], r["fact_rows"], r["rows_with_site_label"], r["distinct_site_labels"], r["rows_with_location_id"], r["distinct_locations"], r["first_explicit_week"], r["last_explicit_week"], r["explicit_weeks"], r["first_store_period"], r["last_store_period"], r["store_periods"]] for r in customers],
    ))
    a("## A2. Stock at store grain")
    a("")
    a("Shares use store-grain rows. Explicit-week shares use only rows that have an explicit week. In-transit and on-order count when the column is not null, including zero.")
    a("")
    a(md_table(
        ["Customer", "Store rows", "SOH", "In transit", "On order", "Explicit-week rows", "SOH of those", "In transit of those", "On order of those"],
        [[r["customer_name"], r["store_rows"], pct(r["store_rows_with_soh"], r["store_rows"]), pct(r["store_rows_with_in_transit"], r["store_rows"]), pct(r["store_rows_with_on_order"], r["store_rows"]), r["explicit_week_rows"], pct(r["explicit_week_rows_with_soh"], r["explicit_week_rows"]), pct(r["explicit_week_rows_with_in_transit"], r["explicit_week_rows"]), pct(r["explicit_week_rows_with_on_order"], r["explicit_week_rows"])] for r in customers],
    ))
    a("## A3. Site-label stability")
    a("")
    a(md_table(
        ["Customer", "Explicit weeks", "Labels in those weeks", "Labels in >=80% of weeks", "Labels in one week", "Labels on one row", "Variant groups"],
        [[r["customer_name"], r["explicit_weeks"], r["labels_with_a_week"], r["stable_labels"], r["labels_in_one_week"], r["labels_on_one_row"], len(variant_by_customer[r["customer_id"]])] for r in customers],
    ))
    a("")
    a("Groups that differ only by case, spacing, or punctuation:")
    a("")
    shown = variants[:400]
    a(md_table(
        ["Customer", "Normalized", "Forms", "Labels"],
        [[r["customer_name"], r["norm"], r["label_forms"], r["forms"]] for r in shown],
    ))
    if len(variants) > len(shown):
        a(f"Showing {len(shown)} of {len(variants)} groups.")
        a("")
    a("## A4. customer_location")
    a("")
    a(md_table(
        ["Customer", "location_type", "Region", "Rows", "Linked to facts", "Fact rows"],
        [[r["customer_name"], r["location_type"], r["region"], r["location_rows"], r["linked_to_facts"], r["fact_rows"]] for r in locations],
    ))
    a("## A5. Raw store, address, and coordinate columns")
    a("")
    a("A key is included when its name matches store, site, outlet, shop, location, address, suburb, city, town, province, region, postal code, zip, or coordinates. Fill rate is non-blank values over all rows for that customer, or that customer and source on staging.")
    a("")
    fact_match = [r for r in kw["fact_keys"] if CUSTOMER_KEY_RE.search(r["key"] or "")]
    a("### Fact raw_source_row")
    a("")
    a(md_table(
        ["Customer", "Key", "Filled", "Rows", "Fill rate"],
        [[r["customer_name"], r["key"], r["filled"], r["nrows"], pct(r["filled"], r["nrows"])] for r in fact_match],
    ))
    a("")
    a("### Staging raw_row_payload")
    a("")
    if kw["job_customer"]:
        a(f"Customer is `import_job.{kw['job_customer']}`, or `resolved_customer_id` when the job has none.")
    else:
        a("`import_job` has no customer column. Customer is `resolved_customer_id` on the staging line.")
    a("")
    structured: dict[tuple, dict] = {}
    staging_match = []
    for row in kw["staging_keys"]:
        structured[(row["customer_name"], row["source_name"])] = row
        if row["key"] and CUSTOMER_KEY_RE.search(row["key"]):
            staging_match.append(row)
    a(md_table(
        ["Customer", "Source", "Staging rows", "raw_location_token fill", "site_label fill"],
        [[name, source, row["nrows"], pct(row["location_token_filled"], row["nrows"]), pct(row["site_label_filled"], row["nrows"])] for (name, source), row in sorted(structured.items(), key=lambda item: (item[0][0] or "", item[0][1] or ""))],
    ))
    a("")
    a(md_table(
        ["Customer", "Source", "Key", "Filled", "Rows", "Fill rate"],
        [[r["customer_name"], r["source_name"], r["key"], r["filled"], r["nrows"], pct(r["filled"], r["nrows"])] for r in staging_match],
    ))
    a("## B6. distributor_location")
    a("")
    a(md_table(
        ["Distributor", "location_type", "Rows", "With address_summary", "Without address_summary"],
        [[r["distributor_name"], r["location_type"], r["location_rows"], r["with_address"], r["without_address"]] for r in kw["dist_locations"]],
    ))
    a("## B7. Distributor sell-out and inventory location columns")
    a("")
    if kw["location_fact_cols"]:
        a("Location-like columns on sell-out, returns, or distributor inventory facts: " + ", ".join(kw["location_fact_cols"]) + ".")
    else:
        a("`fact_sales_sellout`, `fact_returns`, and `fact_inventory_distributor` have no column whose name matches store, location, site, branch, or outlet.")
    a("")
    a("Staging keys match branch, warehouse, DC, depot, location, site, store, plant, godown, or address. Sell-out fill uses rows with `quantity_sold`. Inventory fill uses rows with `stock_on_hand`. A staged row can be both.")
    a("")
    dist_match = [r for r in kw["dist_raw"] if r["key"] and DIST_KEY_RE.search(r["key"])]
    a(md_table(
        ["Distributor", "Key", "Sell-out filled", "Sell-out rows", "Sell-out fill", "Inventory filled", "Inventory rows", "Inventory fill"],
        [[r["distributor_name"], r["key"], r["sellout_filled"], r["sellout_rows"], pct(r["sellout_filled"], r["sellout_rows"]), r["inventory_filled"], r["inventory_rows"], pct(r["inventory_filled"], r["inventory_rows"])] for r in dist_match],
    ))
    a("")
    a("Distinct non-blank values, top 25 by row count:")
    a("")
    a(md_table(
        ["Distributor", "Key", "Value", "Sell-out rows", "Inventory rows", "Distinct values for key"],
        [[r["distributor_name"], r["key"], r["value"], r["sellout_rows"], r["inventory_rows"], r["distinct_values"]] for r in kw["dist_values"]],
    ))
    a("")
    a("### Inventory facts: as-of dates and products")
    a("")
    a(md_table(
        ["Distributor", "Rows", "As-of dates", "Products", "First as-of", "Last as-of"],
        [[r["distributor_name"], r["inventory_rows"], r["as_of_dates"], r["products"], r["first_as_of"], r["last_as_of"]] for r in kw["inventory"]],
    ))
    a("## B8. Shipment ship_to_raw")
    a("")
    filled = [r for r in kw["ship_to"] if r["ship_to_raw"] != "(blank)"]
    a(md_table(
        ["Distributor", "ship_to_raw", "Lines", "Units"],
        [[r["distributor_name"], r["ship_to_raw"], r["lines"], r["units"]] for r in filled[:500]],
    ))
    if len(filled) > 500:
        a(f"Showing 500 of {len(filled)} non-blank ship-to values, highest units first within each distributor.")
        a("")
    blank = [r for r in kw["ship_to"] if r["ship_to_raw"] == "(blank)"]
    if blank:
        a("Lines with a blank ship_to_raw:")
        a("")
        a(md_table(["Distributor", "Lines", "Units"], [[r["distributor_name"], r["lines"], r["units"]] for r in blank]))
    a("## C9. Store-week history and stock beside sales")
    a("")
    a("A store-week is one store key and one explicit week. The store key is the site label, or `loc:` plus the location id when the label is blank. The store-week has both when some row has units sold not zero and some row has reported SOH. The same-row share is store-grain rows where that one row has both.")
    a("")
    a(md_table(
        ["Customer", "Explicit weeks", "Store-weeks", "Store-weeks with units and SOH", "Same-row units and SOH"],
        [[r["customer_name"], r["explicit_weeks"], r["store_weeks"], pct(r["store_weeks_units_and_soh"], r["store_weeks"]), pct(r["store_rows_units_and_soh"], r["store_rows"])] for r in customers],
    ))
    a("## C10. Ship confirm date and POD date")
    a("")
    a("A line counts when both `ship_confirm_date` and `pod_date` are present. The range is the earliest and latest of each date on those lines. `line_state` is the stored value.")
    a("")
    both = [r for r in kw["lead_time"] if r["lines_with_both"]]
    a(md_table(
        ["Distributor", "line_state", "Lines", "Lines with both dates", "First ship confirm", "Last ship confirm", "First POD", "Last POD"],
        [[r["distributor_name"], r["line_state"], r["lines"], r["lines_with_both"], r["min_ship_confirm"], r["max_ship_confirm"], r["min_pod"], r["max_pod"]] for r in both],
    ))
    a("## C11. Promotion scope")
    a("")
    counts = kw["cpor_counts"][0]
    a(f"`cpor_case` rows: {num(counts['cases'])}. `cpor_case_line` rows: {num(counts['case_lines'])}.")
    if kw["cpor_cols"]:
        a("Columns whose names match store, location, site, branch, or outlet: " + ", ".join(f"{r['table_name']}.{r['column_name']}" for r in kw["cpor_cols"]) + ".")
    else:
        a("`cpor_case` and `cpor_case_line` have no column whose name matches store, location, site, branch, or outlet.")
    scope_keys = [r for r in kw["cpor_json_keys"] if SCOPE_COL_RE.search(r["key"] or "")]
    a("")
    a("JSON keys on `source_snapshot_json` and `cost_evidence_json` that match those words:")
    a("")
    a(md_table(["Source", "Key", "Rows with key"], [[r["source"], r["key"], r["rows_with_key"]] for r in scope_keys]))
    a("")
    a(f"Case notes mentioning store, location, or site: {num(counts['cases_notes_mention'])} of {num(counts['cases'])}. Line remarks mentioning those words: {num(counts['lines_remark_mention'])} of {num(counts['case_lines'])}. A text mention is not a store-scope column.")
    a("")
    a("## Classification")
    a("")
    customer_class = []
    seen = set()
    for row in customers:
        seen.add(row["customer_id"])
        label, why = classify_customer(row, len(variant_by_customer[row["customer_id"]]), loc_by_customer[row["customer_id"]])
        customer_class.append([row["customer_name"], label, why])
    named_locations = {}
    for row in locations:
        named_locations[row["customer_id"]] = row["customer_name"]
    for customer_id, name in sorted(named_locations.items(), key=lambda item: item[1] or ""):
        if customer_id in seen:
            continue
        customer_class.append([name, "PARTIAL", "customer_location rows exist and there are no sell-through fact rows"])
    customer_class.sort(key=lambda item: (item[1], item[0] or ""))
    a("### Customers")
    a("")
    a(md_table(["Customer", "Class", "Basis"], customer_class))
    dist_class = classify_distributors(
        kw["dist_locations"], dist_match, kw["dist_stability"], kw["inventory"], kw["sellout_facts"], kw["ship_to"],
    )
    a("### Distributors")
    a("")
    a("Included when the distributor has a location master row, distributor staging, a sell-out fact, an inventory fact, or a shipment.")
    a("")
    a(md_table(["Distributor", "Class", "Basis"], dist_class))
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def classify_customer(row: dict, variant_groups: int, location_rows: int) -> tuple[str, str]:
    has_store = (row["rows_with_site_label"] or 0) > 0 or (row["rows_with_location_id"] or 0) > 0
    if not has_store and location_rows <= 0:
        return "NONE", "sell-through has no site label, no location id, and no customer_location row"
    reasons = []
    weeks = row["explicit_weeks"] or 0
    distinct = row["distinct_site_labels"] or 0
    once = row["labels_in_one_week"] or 0
    stable = row["stable_labels"] or 0
    soh_share = None
    if row["explicit_week_rows"]:
        soh_share = Decimal(row["explicit_week_rows_with_soh"] or 0) / Decimal(row["explicit_week_rows"])
    elif row["store_rows"]:
        soh_share = Decimal(row["store_rows_with_soh"] or 0) / Decimal(row["store_rows"])
    if weeks < 8:
        reasons.append(f"{weeks} explicit weeks")
    if row["store_rows"] and weeks < 8:
        monday = Decimal(row["store_periods_on_monday"] or 0) / Decimal(row["store_rows"])
        if monday >= Decimal("0.8"):
            reasons.append(
                f"period_start_date is Monday on {(monday * 100):.1f}% of store rows; those dates were not counted as explicit weeks"
            )
    if stable < 1:
        reasons.append("no site label reaches 80% of explicit weeks")
    if distinct and (Decimal(once) / Decimal(distinct)) >= Decimal("0.2"):
        reasons.append(f"{once} of {distinct} site labels appear in one week")
    if variant_groups:
        reasons.append(f"{variant_groups} case, spacing, or punctuation groups")
    if soh_share is None or soh_share < Decimal("0.5"):
        shown = "none" if soh_share is None else f"{(soh_share * 100):.1f}%"
        reasons.append(f"reported SOH on {shown} of store rows in the week test")
    if not has_store and location_rows > 0:
        return "PARTIAL", "customer_location rows exist and facts are not at store grain"
    if not reasons:
        return "READY", "stable site labels and reported SOH on at least half of explicit-week store rows"
    return "PARTIAL", "; ".join(reasons)


def classify_distributors(locations, key_rows, stability, inventory, sellout_facts, ship_to) -> list[list]:
    names = set()
    master = defaultdict(int)
    for row in locations:
        names.add(row["distributor_name"])
        master[row["distributor_name"]] += row["location_rows"]
    inv = {}
    for row in inventory:
        names.add(row["distributor_name"])
        inv[row["distributor_name"]] = row
    sell = {}
    for row in sellout_facts:
        names.add(row["distributor_name"])
        sell[row["distributor_name"]] = row
    key_by = defaultdict(list)
    for row in key_rows:
        names.add(row["distributor_name"])
        key_by[row["distributor_name"]].append(row)
    stable_of = {}
    for row in stability:
        names.add(row["distributor_name"])
        distinct = row["distinct_values"] or 0
        once = row["values_on_one_inventory_row"] or 0
        if distinct and Decimal(once) / Decimal(distinct) < Decimal("0.5"):
            stable_of[(row["distributor_name"], row["key"])] = (distinct, once)
    ship_names = defaultdict(int)
    for row in ship_to:
        names.add(row["distributor_name"])
        if row["ship_to_raw"] != "(blank)":
            ship_names[row["distributor_name"]] += 1
    # staging distributors with no location-like key still arrive via key_rows only.
    # key_rows is the filtered list. Callers pass dist_match. Sell-out facts cover fact distributors.
    out = []
    for name in sorted(names, key=lambda item: item or ""):
        as_of = inv[name]["as_of_dates"] if name in inv else 0
        ready_key = None
        weak = None
        for row in key_by[name]:
            denom = row["inventory_rows"] or 0
            if not denom:
                if (row["sellout_filled"] or 0) > 0:
                    weak = f"{row['key']} is filled on sell-out staging and inventory staging rows are {denom}"
                continue
            fill = Decimal(row["inventory_filled"] or 0) / Decimal(denom)
            if fill < Decimal("0.5"):
                weak = f"{row['key']} inventory fill is {(fill * 100):.1f}%"
                continue
            found = stable_of.get((name, row["key"]))
            if found:
                ready_key = row["key"]
                break
            weak = f"{row['key']} is filled on inventory staging and at least half its values appear once"
        if ready_key and as_of >= 4:
            out.append([name, "READY", f"{ready_key} repeats on inventory staging; {as_of} inventory as-of dates"])
            continue
        reasons = []
        if master[name]:
            reasons.append(f"{master[name]} distributor_location rows")
        if key_by[name]:
            reasons.append("location-like staging column present")
        if ship_names[name]:
            reasons.append(f"{ship_names[name]} non-blank ship_to_raw values")
        if name in inv:
            reasons.append(f"inventory facts have {as_of} as-of dates and no location column")
        elif name in sell:
            reasons.append("sell-out facts have no location column")
        if weak:
            reasons.append(weak)
        if as_of and ready_key and as_of < 4:
            reasons.append(f"location column repeats but only {as_of} as-of dates")
        if reasons:
            out.append([name, "PARTIAL", "; ".join(reasons)])
        elif name in sell or name in inv:
            out.append([name, "NONE", "distributor-level sell-out or inventory only"])
        else:
            out.append([name, "NONE", "no location master, location-like raw column, or ship-to"])
    return out


if __name__ == "__main__":
    main()
