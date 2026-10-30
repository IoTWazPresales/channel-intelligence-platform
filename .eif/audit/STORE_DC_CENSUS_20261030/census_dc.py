"""Read-only customer distribution-centre census (section D). Replaces section D in REPORT.md."""

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
SQL_LOG: list[tuple[str, str]] = []

DC_WORDS = (
    r"distribution|warehouse|depot|midrand|centurion|(^|[^a-z])(dc|d/c|wh|hub|jhb|cpt|dbn)([^a-z]|$)"
    r"|d/c|dc[0-9]|[0-9]dc"
)
PLACE_WORDS = (
    r"dc|d/c|distribution|warehouse|wh|depot|hub|jhb|cpt|dbn|midrand|centurion|store|site|branch|location|loc"
)
KEY_RE = re.compile(
    rf"({DC_WORDS})|((stock|soh|on.?hand).*({PLACE_WORDS}))|(({PLACE_WORDS}).*(stock|soh|on.?hand))",
    re.I,
)
# Same shape, as a Postgres regex for label/value scans (POSIX, case-insensitive via ~*).
PG_DC_RE = (
    r"(distribution|warehouse|depot|midrand|centurion|(^|[^a-z])(dc|wh|hub|jhb|cpt|dbn)([^a-z]|$)|d/c|dc[0-9]|[0-9]dc)"
)


def libpq_dsn(url: str) -> str:
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql+asyncpg://"):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix):]
    return url


def num(v) -> str:
    if v is None:
        return ""
    if isinstance(v, Decimal):
        return f"{int(v):,}" if v == v.to_integral() else f"{v:,.2f}"
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def pct(part, whole) -> str:
    if not whole:
        return ""
    return f"{Decimal(part or 0) / Decimal(whole) * 100:.1f}%"


def cell(v) -> str:
    return num(v).replace("|", "\\|").replace("\n", " ")


def md_table(headers, rows) -> str:
    if not rows:
        return "_No rows._\n"
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def main() -> None:
    conn = psycopg.connect(libpq_dsn(get_settings().database_url_sync), autocommit=True, row_factory=dict_row)
    conn.execute("SET default_transaction_read_only = on")
    conn.execute("SET lock_timeout = '5s'")
    conn.execute("SET TIME ZONE 'UTC'")

    def run(name, sql, params=None, timeout_ms=300000):
        SQL_LOG.append((name, sql.strip() + "\n"))
        conn.execute("SELECT set_config('statement_timeout', %s, false)", (str(timeout_ms),))
        print(f"run {name}", flush=True)
        return conn.execute(sql, params).fetchall()

    ident = run("D00_identity", "SELECT current_database() AS db, current_user AS usr", timeout_ms=30000)[0]
    if ident["db"] != "cip":
        raise SystemExit("refusing because current_database() is not cip")

    customers = run(
        "D0_customers",
        """
        SELECT c.id, c.name,
               (SELECT count(*) FROM fact_customer_sellthrough f WHERE f.customer_id = c.id) AS fact_rows,
               (SELECT count(*) FROM import_customer_sellthrough_staging_line s WHERE s.resolved_customer_id = c.id) AS staging_rows
        FROM dim_customer c
        WHERE c.merged_into_customer_id IS NULL
          AND (EXISTS (SELECT 1 FROM fact_customer_sellthrough f WHERE f.customer_id = c.id)
            OR EXISTS (SELECT 1 FROM import_customer_sellthrough_staging_line s WHERE s.resolved_customer_id = c.id)
            OR EXISTS (SELECT 1 FROM fact_inbound_shipment i WHERE COALESCE(i.resolved_customer_id, i.customer_id) = c.id))
        ORDER BY c.name
        """,
        timeout_ms=120000,
    )

    # D1: every raw key with its fill rate (fact raw_source_row and staging raw_row_payload).
    fact_keys = run(
        "D1_fact_raw_keys",
        """
        WITH den AS (SELECT customer_id, count(*) AS nrows FROM fact_customer_sellthrough GROUP BY customer_id)
        SELECT f.customer_id, e.key, d.nrows,
               count(*) FILTER (WHERE nullif(btrim(f.raw_source_row ->> e.key), '') IS NOT NULL) AS filled
        FROM fact_customer_sellthrough f
        JOIN den d ON d.customer_id = f.customer_id
        CROSS JOIN LATERAL jsonb_object_keys(f.raw_source_row) AS e(key)
        WHERE jsonb_typeof(f.raw_source_row) = 'object'
        GROUP BY f.customer_id, e.key, d.nrows
        """,
        timeout_ms=600000,
    )
    stg_keys = run(
        "D1_staging_raw_keys",
        """
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
        """,
        timeout_ms=600000,
    )
    key_rows = []  # (customer_id, origin, key, filled, nrows)
    for origin, rows in (("fact raw_source_row", fact_keys), ("staging raw_row_payload", stg_keys)):
        for r in rows:
            if r["key"] and KEY_RE.search(r["key"]):
                key_rows.append((r["customer_id"], origin, r["key"], r["filled"], r["nrows"]))
    matched_fact = sorted({k for (_, o, k, _, _) in key_rows if o.startswith("fact")})
    matched_stg = sorted({k for (_, o, k, _, _) in key_rows if o.startswith("staging")})

    samples: dict[tuple, list[str]] = defaultdict(list)
    if matched_fact:
        for r in run(
            "D2_fact_key_samples",
            """
            WITH v AS (
              SELECT f.customer_id, e.key, btrim(f.raw_source_row ->> e.key) AS value, count(*) AS n
              FROM fact_customer_sellthrough f
              CROSS JOIN LATERAL unnest(%s::text[]) AS e(key)
              WHERE jsonb_typeof(f.raw_source_row) = 'object'
                AND nullif(btrim(f.raw_source_row ->> e.key), '') IS NOT NULL
              GROUP BY 1, 2, 3),
            r AS (SELECT *, row_number() OVER (PARTITION BY customer_id, key ORDER BY n DESC, value) AS rn FROM v)
            SELECT customer_id, key, value, n FROM r WHERE rn <= 4 ORDER BY customer_id, key, rn
            """,
            params=(matched_fact,),
            timeout_ms=600000,
        ):
            samples[(r["customer_id"], "fact raw_source_row", r["key"])].append(f"{r['value']} ({r['n']:,})")
    if matched_stg:
        for r in run(
            "D2_staging_key_samples",
            """
            WITH v AS (
              SELECT s.resolved_customer_id AS customer_id, e.key, btrim(s.raw_row_payload ->> e.key) AS value, count(*) AS n
              FROM import_customer_sellthrough_staging_line s
              CROSS JOIN LATERAL unnest(%s::text[]) AS e(key)
              WHERE jsonb_typeof(s.raw_row_payload) = 'object'
                AND nullif(btrim(s.raw_row_payload ->> e.key), '') IS NOT NULL
              GROUP BY 1, 2, 3),
            r AS (SELECT *, row_number() OVER (PARTITION BY customer_id, key ORDER BY n DESC, value) AS rn FROM v)
            SELECT customer_id, key, value, n FROM r WHERE rn <= 4 ORDER BY customer_id, key, rn
            """,
            params=(matched_stg,),
            timeout_ms=600000,
        ):
            samples[(r["customer_id"], "staging raw_row_payload", r["key"])].append(f"{r['value']} ({r['n']:,})")

    # D3: site labels that look like a DC (fact and staging), with rows, units and SOH.
    dc_labels = run(
        "D3_dc_like_site_labels_fact",
        f"""
        SELECT f.customer_id, btrim(f.site_label) AS site_label, count(*) AS fact_rows,
               COALESCE(sum(f.units_sold), 0) AS units, COALESCE(sum(f.reported_soh), 0) AS soh,
               count(*) FILTER (WHERE f.reported_soh IS NOT NULL) AS soh_rows,
               count(DISTINCT COALESCE(f.week_start_date, f.period_start_date)) AS periods
        FROM fact_customer_sellthrough f
        WHERE nullif(btrim(f.site_label), '') IS NOT NULL AND lower(f.site_label) ~ %s
        GROUP BY 1, 2 ORDER BY 1, units DESC, 2
        """,
        params=(PG_DC_RE,),
        timeout_ms=600000,
    )
    dc_labels_stg = run(
        "D3_dc_like_site_labels_staging",
        """
        SELECT s.resolved_customer_id AS customer_id, btrim(COALESCE(nullif(btrim(s.site_label), ''), s.raw_location_token)) AS site_label,
               count(*) AS staging_rows, COALESCE(sum(s.units_sold), 0) AS units, COALESCE(sum(s.reported_soh), 0) AS soh
        FROM import_customer_sellthrough_staging_line s
        WHERE lower(COALESCE(nullif(btrim(s.site_label), ''), s.raw_location_token, '')) ~ %s
        GROUP BY 1, 2 ORDER BY 1, units DESC, 2
        """,
        params=(PG_DC_RE,),
        timeout_ms=600000,
    )

    # D4: ship_to_raw for lines that resolve to a customer (direct), plus bill_to / dealer token.
    ship_direct = run(
        "D4_ship_to_direct_customers",
        """
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
        """,
        timeout_ms=600000,
    )
    ship_dc_like = run(
        "D4_ship_to_dc_like_all",
        """
        SELECT COALESCE(d.name, '(unresolved distributor)') AS distributor_name, i.ship_to_raw, count(*) AS lines,
               COALESCE(sum(i.quantity), 0) AS units
        FROM fact_inbound_shipment i
        LEFT JOIN dim_distributor d ON d.id = COALESCE(i.resolved_distributor_id, i.distributor_id)
        WHERE i.ship_to_raw ~* %s OR i.ship_to_raw ~* '-DR-|-DC-|-WH-'
        GROUP BY 1, 2 ORDER BY 1, units DESC
        """,
        params=(PG_DC_RE,),
    )
    ship_codes = run(
        "D4_ship_to_dr_pattern_all",
        """
        SELECT COALESCE(nullif(btrim(i.customer_dealer_token), ''), '(blank)') AS dealer_token,
               COALESCE(d.name, '(unresolved distributor)') AS distributor_name, i.ship_to_raw,
               count(*) AS lines, COALESCE(sum(i.quantity), 0) AS units
        FROM fact_inbound_shipment i
        LEFT JOIN dim_distributor d ON d.id = COALESCE(i.resolved_distributor_id, i.distributor_id)
        WHERE i.ship_to_raw ~* '-DR-'
        GROUP BY 1, 2, 3 ORDER BY units DESC
        """,
    )

    # D5: customer_location rows that look like a DC.
    loc_dc = run(
        "D5_customer_location_types",
        "SELECT c.name AS customer_name, cl.location_type, count(*) AS n FROM customer_location cl "
        "JOIN dim_customer c ON c.id = cl.customer_id GROUP BY 1, 2 ORDER BY 1, 2",
    )

    (OUT / "queries_section_d.sql").write_text(
        "-- Read-only section D. First statement prints current_database() and must be cip.\n"
        + "\n".join(f"-- {n}\n{s}\n" for n, s in SQL_LOG),
        encoding="utf-8",
    )

    # ---- classify ----
    names = {c["id"]: c["name"] for c in customers}
    labels_by = defaultdict(list)
    for r in dc_labels:
        labels_by[r["customer_id"]].append(("fact", r))
    for r in dc_labels_stg:
        if r["customer_id"] is not None:
            labels_by[r["customer_id"]].append(("staging", r))
    keys_by = defaultdict(list)
    for row in key_rows:
        keys_by[row[0]].append(row)
    ship_by = defaultdict(list)
    for r in ship_direct:
        ship_by[r["customer_name"]].append(r)

    def classify(cid: int) -> tuple[str, str]:
        reported = []
        named = []
        for lab_origin, r in labels_by[cid]:
            if lab_origin == "fact" and (r["fact_rows"] or 0) > 0:
                if (r["soh_rows"] or 0) > 0 or (r["units"] or 0) != 0:
                    reported.append(f"site label `{r['site_label']}` carries {num(r['fact_rows'])} fact rows, {num(r['units'])} units, SOH {num(r['soh'])}")
                else:
                    named.append(f"site label `{r['site_label']}` has rows but no units or SOH")
            elif lab_origin == "staging":
                named.append(f"staging label `{r['site_label']}` ({num(r['staging_rows'])} rows)")
        for (_, origin, key, filled, nrows) in keys_by[cid]:
            if filled and re.search(r"(stock|soh|on.?hand)", key, re.I):
                reported.append(f"{origin} column `{key}` filled on {pct(filled, nrows)} of rows")
            elif filled:
                named.append(f"{origin} column `{key}` filled on {pct(filled, nrows)} of rows")
        for r in ship_by.get(names.get(cid, ""), []):
            if re.search(r"-(DR|DC|WH)-", r["ship_to_raw"] or "", re.I):
                named.append(f"shipments go to `{r['ship_to_raw']}` ({num(r['lines'])} lines, {num(r['units'])} units) with no stock reported there")
        if reported:
            return "DC STOCK REPORTED", "; ".join(reported[:3])
        if named:
            return "DC NAMED ONLY", "; ".join(named[:3])
        return "NO DC DATA", "no DC-like raw key, no DC-like site label, no DC-style ship-to"

    # ---- write ----
    L = []
    a = L.append
    a("## D. Customer distribution centres")
    a("")
    a(f"Read {datetime.now().strftime('%Y-%m-%d %H:%M')} on `{ident['db']}` as `{ident['usr']}`, read-only (`default_transaction_read_only=on`). Produced by `census_dc.py`; queries in `queries_section_d.sql`.")
    a("")
    a("Model (Warren, 30 Oct): customers run their own distribution centres, distributors deliver into them, and the DCs supply the stores. So DC stock and DC-level sell-in are a separate level between distributor and store.")
    a("")
    a("Raw key match: names containing `dc`, `d/c`, `distribution`, `warehouse`, `wh`, `depot`, `hub`, `jhb`, `cpt`, `dbn`, `midrand`, `centurion` (short tokens only as whole words), or `stock`/`soh`/`on hand` combined with a place word (dc, warehouse, depot, hub, store, site, branch, location, and the city codes). Site-label match uses the same words on the label value. Fill rate is non-blank values over all rows for that customer (fact `raw_source_row`, or staging `raw_row_payload`).")
    a("")
    a("Classes: DC STOCK REPORTED = rows or columns with units or SOH at a DC-like place. DC NAMED ONLY = a DC-like key or label exists with no stock or sales figure on it. NO DC DATA = nothing DC-like found. A negative describes this search and its patterns, not proof of absence.")
    a("")
    a("### D1. Raw keys matching a DC word")
    a("")
    a(md_table(
        ["Customer", "Origin", "Key", "Filled", "Rows", "Fill rate", "Samples (value, rows)"],
        [[names.get(cid, str(cid)), o, k, f, n, pct(f, n), "; ".join(samples.get((cid, o, k), []))]
         for (cid, o, k, f, n) in sorted(key_rows, key=lambda x: (names.get(x[0], ""), x[1], x[2]))],
    ))
    a("")
    a("### D2. Site labels that look like a DC")
    a("")
    rows2 = []
    for cid in sorted(labels_by, key=lambda x: names.get(x, "")):
        for origin, r in labels_by[cid]:
            if origin == "fact":
                rows2.append([names.get(cid, "(unresolved)"), "fact", r["site_label"], r["fact_rows"], r["units"], r["soh"], r["soh_rows"], r["periods"]])
            else:
                rows2.append([names.get(cid, "(unresolved)"), "staging", r["site_label"], r["staging_rows"], r["units"], r["soh"], "", ""])
    a(md_table(["Customer", "Origin", "Label", "Rows", "Units", "SOH (sum)", "Rows with SOH", "Periods"], rows2))
    a("")
    a("### D3. ship_to_raw on lines that resolve to a customer (direct)")
    a("")
    a(f"{len(ship_direct)} customer/ship-to pairs across {len(ship_by)} customers; the top three ship-to values per customer by units are shown. Every pair is in `queries_section_d.sql` (D4_ship_to_direct_customers). Ship-to codes look like `DISTRIBUTOR-COUNTRY-CHANNEL-NN`; the DC-style ones are in D4.")
    a("")
    top3 = []
    for cname in sorted(ship_by):
        for r in ship_by[cname][:3]:
            top3.append([cname, r["distributor_name"], r["ship_to_raw"], r["dealer_tokens"], r["lines"], r["units"]])
    a(md_table(["Customer", "Distributor", "ship_to_raw", "Dealer tokens", "Lines", "Units"], top3))
    a("")
    a("### D4. ship_to_raw with a `-DR-`, `-DC-`, `-WH-` or DC word, all lines")
    a("")
    a(md_table(["Distributor", "ship_to_raw", "Lines", "Units"], [[r["distributor_name"], r["ship_to_raw"], r["lines"], r["units"]] for r in ship_dc_like]))
    a("")
    a("`-DR-` lines by customer/dealer token (who is the receiver):")
    a("")
    a(md_table(["Dealer token", "Distributor", "ship_to_raw", "Lines", "Units"], [[r["dealer_token"], r["distributor_name"], r["ship_to_raw"], r["lines"], r["units"]] for r in ship_codes]))
    a("")
    a("### D5. customer_location types")
    a("")
    a(md_table(["Customer", "location_type", "Rows"], [[r["customer_name"], r["location_type"], r["n"]] for r in loc_dc]))
    a("")
    a("### D6. Classification")
    a("")
    cls = []
    for c in customers:
        label, why = classify(c["id"])
        cls.append([c["name"], label, why])
    # direct customers seen only on shipments
    shipped_only = [n for n in ship_by if n not in {c["name"] for c in customers}]
    for n in shipped_only:
        cls.append([n, "DC NAMED ONLY" if any("DR" in (r["ship_to_raw"] or "") for r in ship_by[n]) else "NO DC DATA", "shipment ship_to only"])
    cls.sort(key=lambda x: (x[1], x[0] or ""))
    with_st = {c["name"] for c in customers if c["fact_rows"] or c["staging_rows"]}
    shown = [r for r in cls if r[0] in with_st or r[1] != "NO DC DATA"]
    rest = [r for r in cls if r not in shown]
    a(md_table(["Customer", "Class", "Basis"], shown))
    a("")
    a(f"{len(rest)} further customers appear only on shipment lines (no sell-through rows) and show no DC-like ship-to: NO DC DATA. Counts by class over all {len(cls)} customers: " + ", ".join(f"{k} {sum(1 for r in cls if r[1] == k)}" for k in ("DC STOCK REPORTED", "DC NAMED ONLY", "NO DC DATA")) + ".")

    path = OUT / "REPORT.md"
    text = path.read_text(encoding="utf-8")
    text = re.split(r"\n## D\. Customer distribution centres\n", text)[0].rstrip("\n") + "\n\n"
    path.write_text(text + "\n".join(L) + "\n", encoding="utf-8")
    print("wrote section D", flush=True)


if __name__ == "__main__":
    main()
