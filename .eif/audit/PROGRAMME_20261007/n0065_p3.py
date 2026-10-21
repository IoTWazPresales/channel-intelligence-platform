"""N-0065 perf probe 3: per-call cost of the as-built RLS predicate vs candidate forms,
over 200k real product ids from a non-RLS source (generate_series). Read-only."""
import time

from n0065_dbh import engine, ro, sa

N = 200000
BASE = f"""with ids as (select array_agg(id order by id) a, count(*) n from dim_product)
select count(*) from ids, generate_series(1, {N}) g
where {{pred}}"""
PID = "(ids.a[1 + (g % ids.n)::int])::bigint"
PREDS = {
    "baseline_true": "true",
    "as_built_cip_product_id_visible": f"cip_product_id_visible({PID})",
    "inline_exists_line_visible": f"exists (select 1 from dim_product p where p.id = {PID} and cip_product_line_visible(p.product_line))",
    "short_circuit_then_fn": (
        "(current_setting('cip.product_lines', true) is null or current_setting('cip.product_lines', true) = '*'"
        f" or cip_product_id_visible({PID}))"),
    "short_circuit_then_in_allowed_set": (
        "(current_setting('cip.product_lines', true) is null or current_setting('cip.product_lines', true) = '*'"
        f" or {PID} in (select p.id from dim_product p where p.product_line = any (string_to_array("
        "current_setting('cip.product_lines', true), ','))))"),
}


def run(c, label):
    for name, pred in PREDS.items():
        sql = BASE.replace("{pred}", pred)
        t = time.perf_counter()
        n = c.execute(sa.text(sql)).scalar()
        ms = (time.perf_counter() - t) * 1000
        print(f"{label:6} {name:36} rows={n:7} {ms:8.0f}ms")


e = engine()
for label, val in (("unset", None), ("star", "*"), ("NB", "NB"), ("empty", "")):
    with e.connect() as c:  # fresh connection: 'unset' must be a genuine NULL
        ro(c)
        if val is not None:
            c.execute(sa.text("select set_config('cip.product_lines', :v, true)"), {"v": val})
        print("guc:", repr(c.execute(sa.text("select current_setting('cip.product_lines', true)")).scalar()))
        run(c, label)
