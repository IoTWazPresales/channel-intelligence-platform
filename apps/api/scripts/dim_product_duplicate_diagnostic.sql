-- Read-only: duplicate dim_product rows by normalised SKU (lower(trim(sku))).
-- Run with psql or any SQL client; does not modify data.

SELECT lower(trim(sku)) AS sku_norm,
       count(*)::int AS row_count,
       array_agg(id ORDER BY id) AS ids,
       array_agg(sku ORDER BY id) AS sku_raw_values
FROM dim_product
GROUP BY 1
HAVING count(*) > 1
ORDER BY sku_norm;
