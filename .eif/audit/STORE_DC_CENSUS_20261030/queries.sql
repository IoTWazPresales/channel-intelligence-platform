-- Read-only census. First statement prints current_database() and must be cip.
-- 00_identity
SELECT current_database() AS current_database, current_user AS current_user


-- 01_columns
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


-- A0_period_grain
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


-- A1_A2_A3_C9_customer_store
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


-- A3_label_variant_groups
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


-- A4_customer_location
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


-- A5_fact_raw_source_row_keys
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


-- A5_staging_raw_keys
WITH lines AS (
          SELECT s.resolved_customer_id AS customer_id,
                 '(customer file)' AS source_name,
                 s.raw_row_payload, s.raw_location_token, s.site_label
          FROM import_customer_sellthrough_staging_line s
          JOIN import_job j ON j.id = s.import_job_id
          
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


-- B6_distributor_location
SELECT d.name AS distributor_name, dl.location_type,
               count(*) AS location_rows,
               count(*) FILTER (WHERE nullif(btrim(dl.address_summary), '') IS NOT NULL) AS with_address,
               count(*) FILTER (WHERE nullif(btrim(dl.address_summary), '') IS NULL) AS without_address
        FROM distributor_location dl
        JOIN dim_distributor d ON d.id = dl.distributor_id
        GROUP BY d.name, dl.location_type
        ORDER BY d.name, dl.location_type


-- B7_distributor_staging_keys
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


-- B7_inventory_facts
SELECT d.name AS distributor_name, count(*) AS inventory_rows,
               count(DISTINCT f.as_of_date) AS as_of_dates,
               count(DISTINCT f.product_id) AS products,
               min(f.as_of_date) AS first_as_of, max(f.as_of_date) AS last_as_of
        FROM fact_inventory_distributor f
        JOIN dim_distributor d ON d.id = f.distributor_id
        GROUP BY d.name
        ORDER BY d.name


-- B7_sellout_fact_distributors
SELECT d.name AS distributor_name, count(*) AS sellout_rows
        FROM fact_sales_sellout f
        JOIN dim_distributor d ON d.id = f.distributor_id
        GROUP BY d.name
        ORDER BY d.name


-- B8_ship_to_raw
SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name,
               COALESCE(nullif(btrim(f.ship_to_raw), ''), '(blank)') AS ship_to_raw,
               count(*) AS lines, COALESCE(sum(f.quantity), 0) AS units
        FROM fact_inbound_shipment f
        LEFT JOIN dim_distributor d ON d.id = COALESCE(f.resolved_distributor_id, f.distributor_id)
        GROUP BY d.name, COALESCE(nullif(btrim(f.ship_to_raw), ''), '(blank)')
        ORDER BY d.name NULLS LAST, units DESC, ship_to_raw


-- C10_ship_confirm_and_pod
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


-- C11_cpor_json_keys
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


-- C11_cpor_counts
SELECT (SELECT count(*) FROM cpor_case) AS cases,
               (SELECT count(*) FROM cpor_case_line) AS case_lines,
               (SELECT count(*) FROM cpor_case WHERE notes ~* '(store|location|site)') AS cases_notes_mention,
               (SELECT count(*) FROM cpor_case_line WHERE remark ~* '(store|location|site)') AS lines_remark_mention

