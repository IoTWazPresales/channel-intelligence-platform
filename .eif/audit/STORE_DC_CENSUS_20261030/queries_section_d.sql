-- Read-only section D. First statement prints current_database() and must be cip.
-- D00_identity
SELECT current_database() AS db, current_user AS usr


-- D0_customers
SELECT c.id, c.name,
               (SELECT count(*) FROM fact_customer_sellthrough f WHERE f.customer_id = c.id) AS fact_rows,
               (SELECT count(*) FROM import_customer_sellthrough_staging_line s WHERE s.resolved_customer_id = c.id) AS staging_rows
        FROM dim_customer c
        WHERE c.merged_into_customer_id IS NULL
          AND (EXISTS (SELECT 1 FROM fact_customer_sellthrough f WHERE f.customer_id = c.id)
            OR EXISTS (SELECT 1 FROM import_customer_sellthrough_staging_line s WHERE s.resolved_customer_id = c.id)
            OR EXISTS (SELECT 1 FROM fact_inbound_shipment i WHERE COALESCE(i.resolved_customer_id, i.customer_id) = c.id))
        ORDER BY c.name


-- D1_fact_raw_keys
WITH den AS (SELECT customer_id, count(*) AS nrows FROM fact_customer_sellthrough GROUP BY customer_id)
        SELECT f.customer_id, e.key, d.nrows,
               count(*) FILTER (WHERE nullif(btrim(f.raw_source_row ->> e.key), '') IS NOT NULL) AS filled
        FROM fact_customer_sellthrough f
        JOIN den d ON d.customer_id = f.customer_id
        CROSS JOIN LATERAL jsonb_object_keys(f.raw_source_row) AS e(key)
        WHERE jsonb_typeof(f.raw_source_row) = 'object'
        GROUP BY f.customer_id, e.key, d.nrows


-- D1_staging_raw_keys
WITH den AS (
          SELECT resolved_customer_id AS customer_id, count(*) AS nrows
          FROM import_customer_sellthrough_staging_line GROUP BY 1)
        SELECT s.resolved_customer_id AS customer_id, e.key, d.nrows,
               count(*) FILTER (WHERE nullif(btrim(s.raw_row_payload ->> e.key), '') IS NOT NULL) AS filled
        FROM import_customer_sellthrough_staging_line s
        JOIN den d ON d.customer_id = s.resolved_customer_id
        CROSS JOIN LATERAL jsonb_object_keys(s.raw_row_payload) AS e(key)
        WHERE jsonb_typeof(s.raw_row_payload) = 'object'
        GROUP BY s.resolved_customer_id, e.key, d.nrows


-- D3_dc_like_site_labels_fact
SELECT f.customer_id, btrim(f.site_label) AS site_label, count(*) AS fact_rows,
               COALESCE(sum(f.units_sold), 0) AS units, COALESCE(sum(f.reported_soh), 0) AS soh,
               count(*) FILTER (WHERE f.reported_soh IS NOT NULL) AS soh_rows,
               count(DISTINCT COALESCE(f.week_start_date, f.period_start_date)) AS periods
        FROM fact_customer_sellthrough f
        WHERE nullif(btrim(f.site_label), '') IS NOT NULL AND lower(f.site_label) ~ %s
        GROUP BY 1, 2 ORDER BY 1, units DESC, 2


-- D3_dc_like_site_labels_staging
SELECT s.resolved_customer_id AS customer_id, btrim(COALESCE(nullif(btrim(s.site_label), ''), s.raw_location_token)) AS site_label,
               count(*) AS staging_rows, COALESCE(sum(s.units_sold), 0) AS units, COALESCE(sum(s.reported_soh), 0) AS soh
        FROM import_customer_sellthrough_staging_line s
        WHERE lower(COALESCE(nullif(btrim(s.site_label), ''), s.raw_location_token, '')) ~ %s
        GROUP BY 1, 2 ORDER BY 1, units DESC, 2


-- D4_ship_to_direct_customers
SELECT COALESCE(c.name, '(unresolved customer)') AS customer_name,
               COALESCE(d.name, '(no distributor)') AS distributor_name,
               COALESCE(nullif(btrim(i.ship_to_raw), ''), '(blank)') AS ship_to_raw,
               count(DISTINCT nullif(btrim(i.customer_dealer_token), '')) AS dealer_tokens,
               count(*) AS lines, COALESCE(sum(i.quantity), 0) AS units
        FROM fact_inbound_shipment i
        LEFT JOIN dim_customer c ON c.id = COALESCE(i.resolved_customer_id, i.customer_id)
        LEFT JOIN dim_distributor d ON d.id = COALESCE(i.resolved_distributor_id, i.distributor_id)
        WHERE COALESCE(i.resolved_customer_id, i.customer_id) IS NOT NULL
        GROUP BY 1, 2, 3 ORDER BY 1, units DESC, 3


-- D4_ship_to_dc_like_all
SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name, i.ship_to_raw, count(*) AS lines,
               COALESCE(sum(i.quantity), 0) AS units
        FROM fact_inbound_shipment i
        LEFT JOIN dim_distributor d ON d.id = COALESCE(i.resolved_distributor_id, i.distributor_id)
        WHERE i.ship_to_raw ~* %s OR i.ship_to_raw ~* '-DR-|-DC-|-WH-'
        GROUP BY 1, 2 ORDER BY 1, units DESC


-- D4_ship_to_dr_pattern_all
SELECT COALESCE(nullif(btrim(i.customer_dealer_token), ''), '(blank)') AS dealer_token,
               COALESCE(d.name, '(unresolved distributor)') AS distributor_name, i.ship_to_raw,
               count(*) AS lines, COALESCE(sum(i.quantity), 0) AS units
        FROM fact_inbound_shipment i
        LEFT JOIN dim_distributor d ON d.id = COALESCE(i.resolved_distributor_id, i.distributor_id)
        WHERE i.ship_to_raw ~* '-DR-'
        GROUP BY 1, 2, 3 ORDER BY units DESC


-- D5_customer_location_types
SELECT c.name AS customer_name, cl.location_type, count(*) AS n FROM customer_location cl JOIN dim_customer c ON c.id = cl.customer_id GROUP BY 1, 2 ORDER BY 1, 2

