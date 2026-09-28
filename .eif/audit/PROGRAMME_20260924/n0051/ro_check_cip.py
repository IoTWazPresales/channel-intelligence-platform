"""N-0051: run merged_id_leftover_check read-only against a DB (default cip)."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "apps" / "api"))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.services.customer_leftover_repair import (  # noqa: E402
    leftover_row_total_across_merged_losers,
    merged_id_leftover_check,
)

dbname = sys.argv[1] if len(sys.argv) > 1 else "cip"
eng = create_engine(f"postgresql+psycopg://cip:cip@localhost:5432/{dbname}")
with Session(eng) as db:
    db.execute(text("SET TRANSACTION READ ONLY"))
    print("current_database() =", db.execute(text("select current_database()")).scalar())
    print("merged customers:", db.execute(text(
        "select count(*) from dim_customer where merged_into_customer_id is not null "
        "or lower(coalesce(customer_status,''))='merged'")).scalar())
    print("merged distributors:", db.execute(text(
        "select count(*) from dim_distributor where merged_into_distributor_id is not null "
        "or lower(coalesce(distributor_status,''))='merged'")).scalar())
    t = time.perf_counter()
    r = merged_id_leftover_check(db)
    dt = time.perf_counter() - t
    print(json.dumps(r, indent=1))
    print(f"check_seconds={dt:.2f}")
    print("per-loser audit total (customer, existing helper):", leftover_row_total_across_merged_losers(db))
    db.rollback()
