"""N-0065 perf probe 2: is pg_stat_statements available; heaviest product-keyed reads. Read-only."""
from n0065_dbh import engine, ro, sa

e = engine()
with e.connect() as c:
    ro(c)
    print(c.execute(sa.text("select extname, extversion from pg_extension")).fetchall())
    print(c.execute(sa.text("select name, setting from pg_settings where name in"
                            " ('shared_preload_libraries','log_min_duration_statement','jit','work_mem',"
                            "'max_parallel_workers_per_gather','track_functions')")).fetchall())
    has = c.execute(sa.text("select count(*) from pg_extension where extname='pg_stat_statements'")).scalar()
    if has:
        for r in c.execute(sa.text(
                """select calls, round(mean_exec_time)::bigint ms, round(max_exec_time)::bigint mx,
                          left(regexp_replace(query, '\\s+', ' ', 'g'), 260)
                   from pg_stat_statements where query ilike 'select%' and mean_exec_time > 300
                   order by mean_exec_time*calls desc limit 40""")):
            print(r)
    print("-- function stats")
    for r in c.execute(sa.text("select funcname, calls, total_time, self_time from pg_stat_user_functions"
                               " where funcname like 'cip_%'")):
        print(r)
