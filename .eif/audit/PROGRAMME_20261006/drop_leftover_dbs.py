"""Drop named leftover databases. Refuses cip and cip_test."""
import os
import psycopg
from psycopg import sql

ALLOW = (
    "cip_alembic_empty",
    "cip_alembic_smoke",
    "cip_bulk_smoke",
    "cip_clone_dup066",
    "cip_invoice_grad_smoke",
    "cip_lineup_month_smoke",
    "cip_merged_leftover_repair",
    "cip_ns4_settle_clone",
    "cip_oc_absorb_smoke",
    "cip_planD_smoke",
    "cip_pland_smoke",
    "cip_po_carry_smoke",
    "cip_unit3_smoke",
    "cip_unit4_smoke",
    "cip_unit6a_smoke",
    "cip_unit6c_smoke",
)
KEEP = {"cip", "cip_test"}

owner = os.environ.get("PG_OWNER")
if not owner:
    raise SystemExit("PG_OWNER is not set")

conn = psycopg.connect(
    host="127.0.0.1",
    port=5432,
    user="postgres",
    password=owner,
    dbname="postgres",
    autocommit=True,
)
present = {
    row[0]
    for row in conn.execute(
        "SELECT datname FROM pg_database WHERE datname LIKE 'cip%'"
    ).fetchall()
}
for name in KEEP:
    if name not in present:
        raise SystemExit(f"refusing to continue; {name} is missing")

targets = [name for name in ALLOW if name in present]
unexpected = sorted(present - KEEP - set(ALLOW))
if unexpected:
    raise SystemExit("unexpected cip database, not dropping: " + ", ".join(unexpected))

for name in targets:
    if name in KEEP:
        raise SystemExit(f"refusing {name}")
    conn.execute(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
        (name,),
    )
    conn.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
    print(f"dropped {name}")

left = [
    row[0]
    for row in conn.execute(
        "SELECT datname FROM pg_database WHERE datname LIKE 'cip%' ORDER BY 1"
    ).fetchall()
]
print("remaining " + ", ".join(left))
conn.close()
