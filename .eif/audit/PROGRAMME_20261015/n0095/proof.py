"""N-0095 proof: alias-seal backfill, OPEN_CHANNEL repair check and keeper change, clone before cip.

usage (repo root, apps/api venv python):
  python proof.py clone   clone cip -> cip_n0095; backfill dry run, apply, re-apply; OPEN_CHANNEL check;
                          Amazon keeper change 299 -> 26 and back ON THE CLONE ONLY; drop the clone
  python proof.py cip     backfill dry run, apply with --expect-db cip, dry run again; OPEN_CHANNEL check

The Amazon keeper is NOT changed on cip: Warren picks it in the panel.
Passwords are never printed. Writes N0095_CLONE_PROOF.md / N0095_CIP_APPLY.md beside this file.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
N0110 = HERE.parents[1] / "PROGRAMME_20261014" / "n0110"
API = HERE.parents[3] / "apps" / "api"
sys.path.insert(0, str(N0110))
sys.path.insert(0, str(API))

import psycopg  # noqa: E402

import clone_proof as cp  # noqa: E402
from n0110_numbers import url_for  # noqa: E402

CLONE = "cip_n0095"
OUT: list[str] = []
REAL = "(code ~ '^(TMP-CUST-|CUST-)' or code = 'OPEN_CHANNEL')"


def log(text: str) -> None:
    print(text, flush=True)
    OUT.append(text)


def numbers(db: str, label: str) -> dict:
    with psycopg.connect(url_for(db)) as conn:
        q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        n = {
            "db": q("select current_database()"),
            "customers_real": q(f"select count(*) from dim_customer where {REAL}"),
            "merged_real": q(f"select count(*) from dim_customer where merged_into_customer_id is not null and {REAL}"),
            "customers_all": q("select count(*) from dim_customer"),
            "global_aliases": q(
                "select count(*) from customer_source_token_alias where status='approved' "
                "and source_definition_id is null and distributor_id is null"
            ),
            "seal_aliases": q("select count(*) from customer_source_token_alias where notes like '[customer merge alias seal]%'"),
            "aliases_all": q("select count(*) from customer_source_token_alias"),
            "amazon_26_into": q("select merged_into_customer_id from dim_customer where id=26"),
            "amazon_299_into": q("select merged_into_customer_id from dim_customer where id=299"),
            "sellout_299": q("select count(*) from fact_sales_sellout where customer_id=299"),
            "sellout_26": q("select count(*) from fact_sales_sellout where customer_id=26"),
            "cst_299": q("select count(*) from fact_customer_sellthrough where customer_id=299"),
            "cases_299": q("select count(*) from cpor_case where customer_id=299"),
            "oc_into": q("select merged_into_customer_id from dim_customer where code='OPEN_CHANNEL'"),
        }
    log(f"- {label}: " + ", ".join(f"{k} {v}" for k, v in n.items()))
    return n


def run(db: str, *args: str) -> str:
    res = subprocess.run(
        [sys.executable, str(N0110 / "dbrun.py"), db, "--", "python", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    text = (res.stdout or "") + (res.stderr or "")
    keep = [ln for ln in text.splitlines() if not ln.startswith("DATABASE_URL")]
    log("  ```\n  " + "\n  ".join(keep[-40:]) + "\n  ```")
    if res.returncode != 0:
        raise SystemExit(f"step failed on {db}: {args[:2]}")
    return text


def keeper_change(db: str, current: int, new: int, note: str) -> None:
    code = (
        "from sqlalchemy import text\n"
        "from app.db.session_sync import SessionLocal\n"
        "from app.services.customer_merge_keeper import preview_change_keeper, confirm_change_keeper\n"
        "with SessionLocal() as s:\n"
        "    print('current_database()=' + s.execute(text('select current_database()')).scalar())\n"
        f"    p = preview_change_keeper(s, current_keeper_id={current}, new_keeper_id={new}, audit_note={note!r})\n"
        "    print('preview rows_to_move', p['rows_to_move'], 'other', p['other_merged_records_redirected'],"
        " 'seal', len(p['alias_seal_plan']['alias_seal_minted']), 'conflicts', len(p['alias_seal_plan']['alias_seal_conflicts']))\n"
        f"    o = confirm_change_keeper(s, current_keeper_id={current}, new_keeper_id={new}, audit_note={note!r}, performed_by='n0095-proof')\n"
        "    print('confirm rows_moved', o['rows_moved'], 'minted', len(o['alias_seal_minted']), 'reassigned', len(o['alias_seal_reassigned']), 'conflicts', len(o['alias_seal_conflicts']))\n"
    )
    run(db, "-c", code)


def resolve(db: str, tokens: list[str]) -> None:
    code = (
        "from app.db.session_sync import SessionLocal\n"
        "from app.services.imports.distributor_sales_inventory import _resolve_customer\n"
        "with SessionLocal() as s:\n"
        f"    for t in {tokens!r}:\n"
        "        print(repr(t), '->', _resolve_customer(s, source_id=None, distributor_id=None, customer_raw=t,"
        " dealer_group_raw=None, channel_raw=None, open_flag_raw=None))\n"
    )
    run(db, "-c", code)


def clone_proof() -> None:
    log("# N-0095 clone proof (2026-10-15)\n")
    src = numbers("cip", "source cip")
    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    cp.admin_exec(f"CREATE DATABASE {CLONE} OWNER cip")
    with tempfile.TemporaryDirectory() as tmp:
        dump = Path(tmp) / "cip.dump"
        subprocess.run([str(cp.PG_BIN / "pg_dump"), "-Fc", "-d", "cip", "-f", str(dump)], env=cp.pg_env(), check=True)
        subprocess.run([str(cp.PG_BIN / "pg_restore"), "-d", CLONE, str(dump)], env=cp.pg_env(), check=False)
    log(f"- clone {CLONE} made from cip with pg_dump/pg_restore")
    before = numbers(CLONE, "clone before")
    assert before["customers_all"] == src["customers_all"] and before["aliases_all"] == src["aliases_all"]

    log("\n## Alias-seal backfill on the clone")
    log("- dry run:")
    run(CLONE, "scripts/ops/backfill_merged_customer_alias_seals.py")
    numbers(CLONE, "clone after dry run (unchanged)")
    log("- apply:")
    run(CLONE, "scripts/ops/backfill_merged_customer_alias_seals.py", "--apply", "--expect-db", CLONE)
    applied = numbers(CLONE, "clone after apply")
    log("- apply again (must mint nothing):")
    again_text = run(CLONE, "scripts/ops/backfill_merged_customer_alias_seals.py", "--apply", "--expect-db", CLONE)
    again = numbers(CLONE, "clone after second apply")
    idempotent = again["aliases_all"] == applied["aliases_all"] and '"minted": 0' in again_text
    log(f"- second apply minted nothing and alias count unchanged: {idempotent}")
    log("- wrong --expect-db is refused:")
    res = subprocess.run(
        [sys.executable, str(N0110 / "dbrun.py"), CLONE, "--", "python", "scripts/ops/backfill_merged_customer_alias_seals.py", "--apply", "--expect-db", "cip"],
        capture_output=True, text=True,
    )
    log(f"  exit {res.returncode}: {[ln for ln in res.stdout.splitlines() if ln.startswith('refused')]}")

    log("\n## OPEN_CHANNEL repair check on the clone")
    run(CLONE, "scripts/ops/repair_open_channel_wrong_merge.py")

    log("\n## Amazon keeper change on the clone only (Warren picks on cip)")
    resolve(CLONE, ["Amazon", "AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)", "amazon"])
    keeper_change(CLONE, 299, 26, "n0095 clone proof: keep 26")
    swapped = numbers(CLONE, "clone after 299 -> 26")
    resolve(CLONE, ["Amazon", "AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)", "CUST-000260"])
    keeper_change(CLONE, 26, 299, "n0095 clone proof: back to 299")
    back = numbers(CLONE, "clone after 26 -> 299")
    resolve(CLONE, ["Amazon", "AMAZON COMMERCIAL SERVICES (SOUTH AFRICA)"])
    swap_ok = swapped["amazon_299_into"] == 26 and swapped["amazon_26_into"] is None and swapped["sellout_26"] == applied["sellout_299"]
    back_ok = (
        back["amazon_26_into"] == 299 and back["amazon_299_into"] is None
        and back["sellout_299"] == applied["sellout_299"] and back["cst_299"] == applied["cst_299"]
        and back["cases_299"] == applied["cases_299"]
    )
    log(f"- swap moved every sell-out row to 26: {swap_ok}; swap back restored 299 with the same counts: {back_ok}")

    cp.admin_exec(f"DROP DATABASE IF EXISTS {CLONE}")
    log("- clone dropped; dump removed")
    verdict = "PASS" if idempotent and swap_ok and back_ok and res.returncode == 2 else "FAIL"
    log(f"\nCLONE_PROOF {verdict}")
    (HERE / "N0095_CLONE_PROOF.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")
    if verdict != "PASS":
        raise SystemExit(1)


def cip_apply() -> None:
    log("# N-0095 cip apply: alias-seal backfill (2026-10-15)\n")
    log("The Amazon keeper is not changed here: Warren picks it in the panel.\n")
    numbers("cip", "cip before")
    log("- dry run:")
    run("cip", "scripts/ops/backfill_merged_customer_alias_seals.py")
    log("- apply:")
    run("cip", "scripts/ops/backfill_merged_customer_alias_seals.py", "--apply", "--expect-db", "cip")
    numbers("cip", "cip after apply")
    log("- dry run again (must plan nothing):")
    run("cip", "scripts/ops/backfill_merged_customer_alias_seals.py")
    log("- OPEN_CHANNEL check:")
    run("cip", "scripts/ops/repair_open_channel_wrong_merge.py")
    (HERE / "N0095_CIP_APPLY.md").write_text("\n".join(OUT) + "\n", encoding="utf-8")


if __name__ == "__main__":
    {"clone": clone_proof, "cip": cip_apply}[sys.argv[1]]()
