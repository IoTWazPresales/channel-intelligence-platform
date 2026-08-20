#!/usr/bin/env python3
"""Read-only steward + CPOR queue depth against cip. SELECT only; never commit.

Usage (from apps/api):
  .venv/Scripts/python.exe scripts/ops/steward_queue_depth.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db.session_sync import SessionLocal  # noqa: E402
from app.models.commercial_lineup import CommercialLineupCase, CommercialLineupLine  # noqa: E402
from app.models.cpor import CporCase, CporCaseEvent  # noqa: E402
from app.models.customer_code_mint_setting import CustomerCodeMintSetting  # noqa: E402
from app.models.customer_cst_report_slot import CustomerCstReportSlot  # noqa: E402
from app.models.dimensions import DimCustomer, DimDistributor  # noqa: E402
from app.models.import_distributor_si import ImportEntityMappingCandidate  # noqa: E402
from app.models.ingestion import ImportJob, RawFileMetadata  # noqa: E402
from app.services.customer_leftover_repair import leftover_row_total_across_merged_losers  # noqa: E402
from app.services.distributor_full_repoint import count_distributor_fk_refs  # noqa: E402

_DIST_LEFTOVER_SKIP = {("dim_distributor", "merged_into_distributor_id")}


class Row:
    def __init__(self, queue: str, count: str, surface: str, decision: str) -> None:
        self.queue = queue
        self.count = count
        self.surface = surface
        self.decision = decision


def _has_table(insp, name: str) -> bool:
    return name in insp.get_table_names()


def _has_column(insp, table: str, column: str) -> bool:
    if not _has_table(insp, table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _fmt_pairs(pairs: list[tuple[str, int]]) -> str:
    if not pairs:
        return "0"
    return "; ".join(f"{k}={v}" for k, v in pairs)


def _count(db, sql: str, params: dict | None = None) -> int:
    return int(db.execute(text(sql), params or {}).scalar() or 0)


def _mask_url(url: str) -> str:
    parsed = urlparse(url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.password:
        netloc = parsed.netloc.replace(f":{parsed.password}", ":***", 1)
        parsed = parsed._replace(netloc=netloc)
    return urlunparse(parsed)


def main() -> int:
    rows: list[Row] = []
    zeros: list[str] = []
    not_found: list[str] = []

    print(f"DATABASE_URL_SYNC (masked)={_mask_url(get_settings().database_url_sync)}")

    with SessionLocal() as db:
        dbinfo = db.execute(text("SELECT current_database()")).scalar()
        print(f"current_database()={dbinfo!r}")
        if str(dbinfo) != "cip":
            print("STOP: refusing to run against any database other than cip")
            return 2
        db.rollback()
        db.execute(text("SET TRANSACTION READ ONLY"))

        insp = inspect(db.get_bind())

        # --- a) mapping candidates, live vs dead jobs ---
        if not _has_table(insp, ImportEntityMappingCandidate.__tablename__):
            not_found.append("import_entity_mapping_candidate")
            rows.append(Row("a mapping candidates", "NOT FOUND", "/admin/imports/dsi", "map token → dim"))
        elif not _has_table(insp, ImportJob.__tablename__):
            not_found.append("import_job")
            rows.append(Row("a mapping candidates", "NOT FOUND: import_job", "/admin/imports/dsi", "map token → dim"))
        else:
            live_sql = """
                SELECT c.entity_type, coalesce(c.status, '<null>'), count(*)
                FROM import_entity_mapping_candidate c
                JOIN import_job j ON j.id = c.import_job_id
                WHERE j.archived_at IS NULL
                  AND lower(coalesce(j.status, '')) NOT IN
                      ('applied', 'completed', 'failed', 'cancelled', 'archived')
                GROUP BY 1, 2
                ORDER BY 1, 2
            """
            dead_sql = """
                SELECT c.entity_type, coalesce(c.status, '<null>'), count(*)
                FROM import_entity_mapping_candidate c
                JOIN import_job j ON j.id = c.import_job_id
                WHERE j.archived_at IS NOT NULL
                   OR lower(coalesce(j.status, '')) IN
                      ('applied', 'completed', 'failed', 'cancelled', 'archived')
                GROUP BY 1, 2
                ORDER BY 1, 2
            """
            live = [(f"{r[0]}×{r[1]}", int(r[2])) for r in db.execute(text(live_sql)).all()]
            dead = [(f"{r[0]}×{r[1]}", int(r[2])) for r in db.execute(text(dead_sql)).all()]
            live_n = sum(v for _, v in live)
            dead_n = sum(v for _, v in dead)
            rows.append(
                Row(
                    "a live-job candidates (entity_type×status)",
                    _fmt_pairs(live) if live else "0 (empty queue)",
                    "/admin/imports/dsi (and shipment/CST steward mounts)",
                    "confirm suggested dim or search+map one token",
                )
            )
            rows.append(
                Row(
                    "a dead-job candidates (not a decision)",
                    _fmt_pairs(dead) if dead else "0 (empty)",
                    "no UI — closed/applied jobs",
                    "do not steward; candidate on a dead job is leftover",
                )
            )
            if live_n == 0:
                zeros.append("a live-job candidates")

        # --- b) distributor attribution: hint was case; real column is line ---
        if _has_column(insp, CommercialLineupCase.__tablename__, "distributor_attribution_status"):
            b_table = CommercialLineupCase.__tablename__
        elif _has_column(insp, CommercialLineupLine.__tablename__, "distributor_attribution_status"):
            not_found.append(
                "commercial_lineup_case.distributor_attribution_status "
                "(hint); counted commercial_lineup_line.distributor_attribution_status"
            )
            b_table = CommercialLineupLine.__tablename__
        else:
            b_table = None
        if b_table is None:
            not_found.append("distributor_attribution_status")
            rows.append(Row("b distributor_attribution_status", "NOT FOUND", "/lineup", "set/confirm distributor"))
        else:
            b_pairs = [
                (str(r[0]) if r[0] is not None else "<NULL>", int(r[1]))
                for r in db.execute(
                    text(
                        f"SELECT distributor_attribution_status, count(*) "
                        f"FROM {b_table} GROUP BY 1 ORDER BY 1 NULLS FIRST"
                    )
                ).all()
            ]
            rows.append(
                Row(
                    f"b {b_table}.distributor_attribution_status",
                    _fmt_pairs(b_pairs),
                    "/lineup",
                    "steward_set / shipment_confirmed / resolve conflict on one line",
                )
            )
            if sum(v for _, v in b_pairs) == 0:
                zeros.append("b distributor_attribution_status")

        # --- c) TMP codes excluding merged losers ---
        if not _has_column(insp, DimCustomer.__tablename__, "merged_into_customer_id"):
            not_found.append("dim_customer.merged_into_customer_id")
        if not _has_column(insp, DimDistributor.__tablename__, "merged_into_distributor_id"):
            not_found.append("dim_distributor.merged_into_distributor_id")
        tmp_cust_open = _count(
            db,
            "SELECT count(*) FROM dim_customer "
            "WHERE code LIKE 'TMP-CUST%' AND merged_into_customer_id IS NULL",
        )
        tmp_cust_excl = _count(
            db,
            "SELECT count(*) FROM dim_customer "
            "WHERE code LIKE 'TMP-CUST%' AND merged_into_customer_id IS NOT NULL",
        )
        tmp_dist_open = _count(
            db,
            "SELECT count(*) FROM dim_distributor "
            "WHERE code LIKE 'TMP-DIST%' AND merged_into_distributor_id IS NULL",
        )
        tmp_dist_excl = _count(
            db,
            "SELECT count(*) FROM dim_distributor "
            "WHERE code LIKE 'TMP-DIST%' AND merged_into_distributor_id IS NOT NULL",
        )
        rows.append(
            Row(
                "c TMP-CUST open (merged losers excluded)",
                str(tmp_cust_open),
                "/admin mappings / customer master (promote)",
                "promote one TMP row to a minted or operator-supplied code",
            )
        )
        rows.append(
            Row(
                "c TMP-CUST excluded merged losers",
                str(tmp_cust_excl),
                "no UI — merge residue",
                "do not promote a loser",
            )
        )
        rows.append(
            Row(
                "c TMP-DIST open (merged losers excluded)",
                str(tmp_dist_open),
                "/admin distributor master",
                "promote one TMP distributor",
            )
        )
        rows.append(
            Row(
                "c TMP-DIST excluded merged losers",
                str(tmp_dist_excl),
                "no UI — merge residue",
                "do not promote a loser",
            )
        )
        for label, n in (
            ("c TMP-CUST open", tmp_cust_open),
            ("c TMP-DIST open", tmp_dist_open),
        ):
            if n == 0:
                zeros.append(label)

        # --- d) mint setting ---
        if not _has_table(insp, CustomerCodeMintSetting.__tablename__):
            not_found.append("customer_code_mint_setting")
            rows.append(Row("d customer_code_mint_setting", "NOT FOUND", "no UI", "n/a"))
        else:
            mint_n = _count(db, "SELECT count(*) FROM customer_code_mint_setting")
            detail = str(mint_n)
            if mint_n:
                mint_rows = db.execute(
                    text(
                        "SELECT tenant_id, prefix, pattern_template, next_seq "
                        "FROM customer_code_mint_setting ORDER BY tenant_id"
                    )
                ).all()
                detail = (
                    f"{mint_n} row(s): "
                    + "; ".join(
                        f"tenant={r[0]!s} prefix={r[1]!s} pattern={r[2]!s} next_seq={r[3]}"
                        for r in mint_rows
                    )
                )
            rows.append(
                Row(
                    "d customer_code_mint_setting",
                    detail,
                    "no UI (BACKLOG-140 mint path not shipped)",
                    "settings row exists ≠ production mint on promote",
                )
            )
            if mint_n == 0:
                zeros.append("d customer_code_mint_setting")

        # --- e) DSI unresolved product tokens (live jobs) ---
        if _has_table(insp, ImportEntityMappingCandidate.__tablename__):
            e_all = _count(
                db,
                """
                SELECT count(*) FROM import_entity_mapping_candidate
                WHERE entity_type = 'product_identifier'
                  AND status IN ('needs_review', 'ignored')
                """,
            )
            e_nr = _count(
                db,
                """
                SELECT count(*) FROM import_entity_mapping_candidate
                WHERE entity_type = 'product_identifier'
                  AND status = 'needs_review'
                """,
            )
            e_live = _count(
                db,
                """
                SELECT count(*) FROM import_entity_mapping_candidate c
                JOIN import_job j ON j.id = c.import_job_id
                WHERE c.entity_type = 'product_identifier'
                  AND c.status IN ('needs_review', 'ignored')
                  AND j.archived_at IS NULL
                  AND lower(coalesce(j.status, '')) NOT IN
                      ('applied', 'completed', 'failed', 'cancelled', 'archived')
                """,
            )
            rows.append(
                Row(
                    "e DSI product_identifier needs_review|ignored (gap worklist grain)",
                    f"all_jobs={e_all}; needs_review={e_nr}; live_jobs={e_live}",
                    "/admin/product-master-gaps",
                    "map token → dim_product or ignore_no_catalogue",
                )
            )
            if e_all == 0:
                zeros.append("e DSI product catalogue gap")
        else:
            not_found.append("e import_entity_mapping_candidate.product_identifier")
            rows.append(Row("e DSI product catalogue gap", "NOT FOUND", "/admin/product-master-gaps", "n/a"))

        # --- f) CST hydration ---
        if not _has_table(insp, RawFileMetadata.__tablename__):
            not_found.append("raw_file_metadata")
        stub_cols = []
        if _has_table(insp, RawFileMetadata.__tablename__):
            stub_cols = [
                c["name"]
                for c in insp.get_columns(RawFileMetadata.__tablename__)
                if "stub" in c["name"].lower() or "hydrat" in c["name"].lower()
            ]
        if not stub_cols:
            not_found.append(
                "raw_file_metadata stub/hydrated flag (none; columns are "
                "id, job_id, storage_key, byte_size, checksum + timestamps)"
            )
        cst_jobs = 0
        cst_files = 0
        if _has_table(insp, ImportJob.__tablename__):
            cst_jobs = _count(
                db,
                "SELECT count(*) FROM import_job WHERE template_slug = 'customer_sell_through'",
            )
            if _has_table(insp, RawFileMetadata.__tablename__):
                cst_files = _count(
                    db,
                    """
                    SELECT count(*) FROM raw_file_metadata r
                    JOIN import_job j ON j.id = r.job_id
                    WHERE j.template_slug = 'customer_sell_through'
                    """,
                )
        slot_pairs: list[tuple[str, int]] = []
        if _has_table(insp, CustomerCstReportSlot.__tablename__):
            slot_pairs = [
                (str(r[0]), int(r[1]))
                for r in db.execute(
                    text(
                        "SELECT coalesce(status, '<null>'), count(*) "
                        "FROM customer_cst_report_slot GROUP BY 1 ORDER BY 1"
                    )
                ).all()
            ]
        else:
            not_found.append("customer_cst_report_slot")
        rows.append(
            Row(
                "f CST jobs (template_slug=customer_sell_through) + raw files",
                f"jobs={cst_jobs}; raw_file_metadata={cst_files}; stub_flag=none",
                "/admin/imports (CST)",
                "upload/apply a CST file — no stub-vs-hydrated column on raw_file_metadata",
            )
        )
        rows.append(
            Row(
                "f CST report slots by status",
                _fmt_pairs(slot_pairs) if slot_pairs else ("0 (empty queue)" if _has_table(insp, CustomerCstReportSlot.__tablename__) else "NOT FOUND"),
                "/admin CST expected-report tracker",
                "mark a week received or chase a due/late slot",
            )
        )
        if cst_jobs == 0:
            zeros.append("f CST import jobs")

        # --- g) leftovers — reuse customer_leftover_repair; distributor via same FK discovery ---
        try:
            cust_left = leftover_row_total_across_merged_losers(db)
        except SQLAlchemyError as exc:
            cust_left = f"QUERY ERROR: {exc.__class__.__name__}"
            not_found.append(f"g customer leftover query: {exc}")
        rows.append(
            Row(
                "g merged-customer leftover FK rows",
                str(cust_left),
                "no UI — ops leftover repair script",
                "repoint one loser's FK set onto the survivor (do not run from this script)",
            )
        )
        if cust_left == 0:
            zeros.append("g customer leftovers")

        dist_left = 0
        try:
            dist_losers = db.execute(
                text(
                    "SELECT id FROM dim_distributor WHERE merged_into_distributor_id IS NOT NULL"
                )
            ).scalars().all()
            for did in dist_losers:
                counts = count_distributor_fk_refs(db, int(did))
                dist_left += sum(
                    n
                    for key, n in counts.items()
                    if tuple(key.split(".", 1)) not in _DIST_LEFTOVER_SKIP
                )
        except SQLAlchemyError as exc:
            dist_left = f"QUERY ERROR: {exc.__class__.__name__}"
            not_found.append(f"g distributor leftover query: {exc}")
        rows.append(
            Row(
                "g merged-distributor leftover FK rows",
                str(dist_left),
                "no UI — distributor full merge leftover",
                "repoint via distributor merge engine (not this script)",
            )
        )
        if dist_left == 0:
            zeros.append("g distributor leftovers")

        # --- h) CPOR status vs workflow_status ---
        if not _has_table(insp, CporCase.__tablename__):
            not_found.append("cpor_case")
            for q in ("h status", "h workflow_status", "h disagree"):
                rows.append(Row(q, "NOT FOUND", "/commercial-planner/cpor-cases", "n/a"))
        else:
            st = [
                (str(r[0]), int(r[1]))
                for r in db.execute(text("SELECT status, count(*) FROM cpor_case GROUP BY 1 ORDER BY 1")).all()
            ]
            wf = [
                (str(r[0]), int(r[1]))
                for r in db.execute(
                    text("SELECT workflow_status, count(*) FROM cpor_case GROUP BY 1 ORDER BY 1")
                ).all()
            ]
            disagree = _count(
                db,
                "SELECT count(*) FROM cpor_case WHERE status IS DISTINCT FROM workflow_status",
            )
            rows.append(
                Row(
                    "h cpor_case by status",
                    _fmt_pairs(st),
                    "/commercial-planner/cpor-cases",
                    "lifecycle action on one case (propose/approve/…)",
                )
            )
            rows.append(
                Row(
                    "h cpor_case by workflow_status",
                    _fmt_pairs(wf),
                    "/commercial-planner/cpor-cases",
                    "same surface; BACKLOG-139 if drifted",
                )
            )
            rows.append(
                Row(
                    "h cpor_case status≠workflow_status",
                    str(disagree),
                    "no UI — BACKLOG-139",
                    "pick the canonical column and repair one drifted row",
                )
            )
            if disagree == 0:
                zeros.append("h status/workflow disagree")

            # --- i) past window_end, not settled ---
            today = date.today().isoformat()
            past = _count(
                db,
                "SELECT count(*) FROM cpor_case "
                "WHERE window_end < CAST(:today AS date) "
                "AND lower(coalesce(status, '')) NOT IN ('settled', 'cancelled')",
                {"today": today},
            )
            rows.append(
                Row(
                    "i past window_end and not settled/cancelled",
                    str(past),
                    "/commercial-planner/cpor-cases (settlement UI not built — spec §8)",
                    "settle or cancel one ended case",
                )
            )
            if past == 0:
                zeros.append("i settlement backlog")

            # --- j) superseded pointer ---
            if not _has_column(insp, CporCase.__tablename__, "superseded_by_case_id"):
                not_found.append("cpor_case.superseded_by_case_id")
                rows.append(Row("j superseded_by_case_id IS NOT NULL", "NOT FOUND", "no UI", "n/a"))
            else:
                sup = _count(
                    db,
                    "SELECT count(*) FROM cpor_case WHERE superseded_by_case_id IS NOT NULL",
                )
                rows.append(
                    Row(
                        "j cpor_case.superseded_by_case_id IS NOT NULL",
                        str(sup),
                        "no UI — BACKLOG-138 (readers filter; nothing writes)",
                        "soft-supersede would set the pointer on one case",
                    )
                )
                if sup == 0:
                    zeros.append("j CPOR superseded pointer")

            # --- k) case customer still TMP-CUST ---
            tmp_cases = _count(
                db,
                """
                SELECT count(*) FROM cpor_case c
                JOIN dim_customer d ON d.id = c.customer_id
                WHERE d.code LIKE 'TMP-CUST%'
                """,
            )
            rows.append(
                Row(
                    "k cpor_case whose customer code is TMP-CUST%",
                    str(tmp_cases),
                    "/commercial-planner/cpor-cases + customer promote (BACKLOG-140)",
                    "mint/promote the case customer then cases display a real code",
                )
            )
            if tmp_cases == 0:
                zeros.append("k TMP-CUST on CPOR cases")

        # --- l) null actor events ---
        if not _has_table(insp, CporCaseEvent.__tablename__):
            not_found.append("cpor_case_event")
            rows.append(Row("l cpor_case_event null actor", "NOT FOUND", "no UI", "n/a"))
        else:
            null_actor = _count(db, "SELECT count(*) FROM cpor_case_event WHERE actor IS NULL")
            rows.append(
                Row(
                    "l cpor_case_event actor IS NULL",
                    str(null_actor),
                    "no UI — spec §7 audit (pre-R1 rows)",
                    "cannot backfill a real actor; new writes must stamp user id",
                )
            )
            if null_actor == 0:
                zeros.append("l null-actor events")

        db.rollback()

    print()
    print(f"{'queue':<62} {'count':<72} {'decision surface':<52} {'one decision'}")
    print("-" * 220)
    for r in rows:
        print(f"{r.queue:<62} {r.count:<72} {r.surface:<52} {r.decision}")
    print()
    print("zeros:")
    if zeros:
        for z in zeros:
            print(f"  - {z}")
    else:
        print("  (none)")
    print()
    print("NOT FOUND / model-hint mismatches:")
    if not_found:
        for n in not_found:
            print(f"  - {n}")
    else:
        print("  (none)")

    # Housekeeping report: clone size (SELECT on catalog; still read-only)
    print()
    print("--- housekeeping (catalog SELECT; no DROP) ---")
    with SessionLocal() as db:
        dbinfo = db.execute(text("SELECT current_database()")).scalar()
        if str(dbinfo) != "cip":
            print("STOP: catalog check not on cip")
            return 2
        db.rollback()
        db.execute(text("SET TRANSACTION READ ONLY"))
        exists = db.execute(
            text("SELECT 1 FROM pg_database WHERE datname = 'cip_merged_leftover_repair'")
        ).first()
        if exists is None:
            print("cip_merged_leftover_repair: NOT PRESENT")
        else:
            size = db.execute(
                text("SELECT pg_size_pretty(pg_database_size('cip_merged_leftover_repair'))")
            ).scalar()
            mtime = None
            try:
                mtime = db.execute(
                    text(
                        """
                        SELECT (pg_stat_file('base/' || oid::text || '/PG_VERSION')).modification
                        FROM pg_database
                        WHERE datname = 'cip_merged_leftover_repair'
                        """
                    )
                ).scalar()
            except SQLAlchemyError as exc:
                mtime = f"unavailable ({exc.__class__.__name__})"
                db.rollback()
                db.execute(text("SET TRANSACTION READ ONLY"))
            print(
                f"cip_merged_leftover_repair: present size={size} "
                f"PG_VERSION mtime={mtime!s} (clone-age proxy). NOT DROPPED."
            )
        db.rollback()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ProgrammingError as exc:
        print(f"QUERY ERROR (broken, not empty): {exc}")
        raise SystemExit(1)
