#!/usr/bin/env python3
"""Generate docs/memory/CLAUDE_CATCHUP.md for Claude-in-browser.

Manual invocation only. Not Cursor session tooling. Not wired to CI, git hooks,
or restart-dev. All SQL is SELECT/count. Does not edit .env or run alembic upgrade.

Run (repo root, API venv so psycopg is available):

  apps/api/.venv/Scripts/python.exe scripts/claude_catchup.py --since 2026-08-08
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse
from xml.etree import ElementTree

SCRIPT_VERSION = "1.1.0"
AUDIENCE = (
    "AUDIENCE: Claude-in-browser. Not a Cursor context file. "
    "Do not consume or overwrite."
)
BANNED = re.compile(r"handover", re.I)

REPO_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPO_ROOT / "apps" / "api"
ENV_FILE = API_ROOT / ".env"
OUT_PATH = REPO_ROOT / "docs" / "memory" / "CLAUDE_CATCHUP.md"
LOG_PATH = REPO_ROOT / "docs" / "memory" / "claude_catchup_log.jsonl"
ALEMBIC_VERSIONS = API_ROOT / "alembic" / "versions"

# Steward queues discovered in code (quoted in section [5]). Keys are stable.
WORKLIST_SPECS: list[dict[str, str]] = [
    {
        "key": "unresolved_product_dsi",
        "sql": (
            "SELECT count(*)::bigint FROM import_entity_mapping_candidate "
            "WHERE entity_type = 'product_identifier' "
            "AND status NOT IN ('resolved', 'ignored', 'waived_open_channel')"
        ),
        "found": (
            "apps/api/app/services/imports/dsi_mapping_candidates_list.py "
            "_ENTITY_MAP['product']='product_identifier'; TERMINAL_STATUSES="
            "{resolved, ignored, waived_open_channel}"
        ),
    },
    {
        "key": "ambiguous_product_dsi",
        "sql": (
            "SELECT count(*)::bigint FROM import_entity_mapping_candidate "
            "WHERE entity_type = 'product_identifier' "
            "AND status NOT IN ('resolved', 'ignored', 'waived_open_channel') "
            "AND context->>'product_match_status' IN "
            "('ambiguous', 'ambiguous_eligible')"
        ),
        "found": (
            "apps/api/app/services/imports/dsi_mapping_candidates_tab_counts.py "
            "product_match_status_count_stmt groups context.product_match_status "
            "for open product_identifier rows"
        ),
    },
    {
        "key": "unresolved_product_shipment",
        "sql": (
            "SELECT count(*)::bigint FROM shipment_evidence_current "
            "WHERE product_resolution_status IN "
            "('no_match', 'inactive_only', 'ambiguous', 'no_identifier')"
        ),
        "found": (
            "apps/api/app/services/imports/product_master_gap_worklist.py "
            "_SHIPMENT_UNRESOLVED_STATUSES = {no_match, inactive_only, "
            "ambiguous, no_identifier}"
        ),
    },
    {
        "key": "unresolved_product_cst",
        "sql": (
            "SELECT count(*)::bigint FROM import_entity_mapping_candidate "
            "WHERE entity_type = 'cst_product_token' "
            "AND status NOT IN ('resolved', 'ignored')"
        ),
        "found": (
            "apps/api/app/services/imports/cst_mapping_candidates.py "
            "CST_PRODUCT_ENTITY = 'cst_product_token'"
        ),
    },
    {
        "key": "customer_ambiguity",
        "sql": (
            "SELECT count(*)::bigint FROM import_entity_mapping_candidate "
            "WHERE entity_type IN ('customer_dealer_token', 'customer') "
            "AND status NOT IN ('resolved', 'ignored', 'waived_open_channel')"
        ),
        "found": (
            "apps/api/app/services/imports/dsi_mapping_candidates_list.py "
            "_ENTITY_MAP['customer']='customer_dealer_token'; plus shipment "
            "candidates entity_type='customer' in shipment_evidence.py"
        ),
    },
    {
        "key": "unlinked_po_gap_rows",
        "sql": (
            "WITH covered AS ("
            "  SELECT DISTINCT clcp.purchase_order_id, cll.product_id"
            "  FROM commercial_lineup_case_po clcp"
            "  JOIN commercial_lineup_line cll ON cll.case_id = clcp.case_id"
            "  JOIN commercial_lineup_case clc ON clc.id = clcp.case_id"
            "  WHERE cll.product_id IS NOT NULL"
            "    AND cll.row_status <> 'superseded'"
            "    AND clc.superseded_by_case_id IS NULL"
            "    AND clc.commercial_status NOT IN ('cancelled', 'superseded')"
            "), shipped AS ("
            "  SELECT purchase_order_id, product_id"
            "  FROM fact_inbound_shipment"
            "  WHERE purchase_order_id IS NOT NULL AND product_id IS NOT NULL"
            "  GROUP BY 1, 2"
            "  HAVING SUM(CASE WHEN line_state = 'shipped' THEN quantity ELSE 0 END) > 0"
            ") SELECT count(*)::bigint FROM shipped s"
            " WHERE NOT EXISTS ("
            "   SELECT 1 FROM covered c"
            "   WHERE c.purchase_order_id = s.purchase_order_id"
            "     AND c.product_id = s.product_id"
            " ) AND s.purchase_order_id NOT IN ("
            "   SELECT id FROM purchase_order WHERE dismiss_reason_code IS NOT NULL"
            " )"
        ),
        "found": (
            "apps/api/app/services/commercial_planner/lineup_po_gap.py "
            "po_gap_worklist / _po_gap_worklist_inner; active_lineup_case_filters "
            "in lineup_period_canonical.py"
        ),
    },
    {
        "key": "distributor_attribution_token_proposed",
        "sql": (
            "SELECT count(*)::bigint FROM commercial_lineup_line "
            "WHERE distributor_attribution_status = 'token_proposed'"
        ),
        "found": (
            "apps/api/app/models/commercial_lineup.py "
            "DISTRIBUTOR_ATTRIBUTION_STATUSES; "
            "lineup_distributor_attribution.py STATUS_TOKEN_PROPOSED='token_proposed'"
        ),
    },
    {
        "key": "distributor_attribution_conflict",
        "sql": (
            "SELECT count(*)::bigint FROM commercial_lineup_line "
            "WHERE distributor_attribution_status = 'conflict'"
        ),
        "found": (
            "apps/api/app/services/commercial_planner/lineup_distributor_attribution.py "
            "STATUS_CONFLICT='conflict'"
        ),
    },
    {
        "key": "not_in_catalogue",
        "sql": (
            "SELECT count(*)::bigint FROM import_entity_mapping_candidate "
            "WHERE coalesce(context->>'catalogue_gap', '') IN ('true', 'True') "
            "OR context->>'steward_ignore_reason_code' = 'ignore_no_catalogue'"
        ),
        "found": (
            "apps/api/app/services/imports/cst_mapping_candidates.py "
            "reason_code default ignore_no_catalogue; "
            "product_master_gap_worklist.py _merge_cst_tokens / _merge_dsi_tokens"
        ),
    },
    {
        "key": "tmp_cust_provisional",
        "sql": "SELECT count(*)::bigint FROM dim_customer WHERE starts_with(code, 'TMP-CUST')",
        "found": (
            "apps/api/app/api/v1/endpoints/customers.py "
            "TMP_CUSTOMER_CODE_PREFIX = 'TMP-CUST'"
        ),
    },
    {
        "key": "tmp_dist_provisional",
        "sql": "SELECT count(*)::bigint FROM dim_distributor WHERE starts_with(code, 'TMP-DIST')",
        "found": (
            "apps/api/app/api/v1/endpoints/distributors.py "
            "BACKLOG-061 TMP-DIST promote/park paths"
        ),
    },
    {
        "key": "cst_article_alias_proposed",
        "sql": (
            "SELECT count(*)::bigint FROM customer_article_alias "
            "WHERE status = 'proposed'"
        ),
        "found": (
            "apps/api/app/models/customer_article_alias.py status default proposed; "
            "apps/api/app/api/v1/endpoints/cst_steward.py list_article_aliases"
        ),
    },
    {
        "key": "entity_mapping_queue_open",
        "sql": (
            "SELECT count(*)::bigint FROM entity_mapping_queue "
            "WHERE status IN ('review_required', 'needs_review', 'open')"
        ),
        "found": (
            "apps/api/app/models/mapping.py EntityMappingQueue "
            "status default review_required"
        ),
    },
]


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(code)


def git(args: list[str], check: bool = True) -> str:
    r = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and r.returncode != 0:
        die(f"git {' '.join(args)} failed: {r.stderr.strip() or r.stdout.strip()}")
    return (r.stdout or "").rstrip("\n")


def load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip("'").strip('"')
        out[k.strip()] = v
    return out


def resolve_sync_url() -> str:
    env = {**load_env_file(ENV_FILE), **os.environ}
    url = (env.get("DATABASE_URL_SYNC") or env.get("database_url_sync") or "").strip()
    if not url:
        die("DATABASE_URL_SYNC not set in environment or apps/api/.env")
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url.split("://", 1)[1]
    elif url.startswith("postgresql+asyncpg://"):
        url = "postgresql://" + url.split("://", 1)[1]
    return url


def mask_url(url: str) -> str:
    p = urlparse(url)
    if not p.password:
        return url
    netloc = p.netloc.replace(f":{p.password}@", ":***@")
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


def assert_select(sql: str) -> str:
    stripped = sql.strip().lstrip("(").strip()
    head = stripped.split(None, 1)[0].upper() if stripped else ""
    if head not in {"SELECT", "WITH"}:
        die(f"refusing non-SELECT SQL: {sql[:80]}")
    return sql


def _exec(cur: Any, sql: str, params: tuple[Any, ...] | None = None) -> None:
    sql = assert_select(sql)
    if params:
        cur.execute(sql, params)
    else:
        cur.execute(sql)


def fetch_one(cur: Any, sql: str, params: tuple[Any, ...] | None = None) -> Any:
    _exec(cur, sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def fetch_all(cur: Any, sql: str, params: tuple[Any, ...] | None = None) -> list[tuple[Any, ...]]:
    _exec(cur, sql, params)
    return list(cur.fetchall())


def read_log() -> list[dict[str, Any]]:
    if not LOG_PATH.is_file():
        return []
    lines: list[dict[str, Any]] = []
    for raw in LOG_PATH.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        lines.append(json.loads(raw))
    return lines


def parse_since(raw: str, log: list[dict[str, Any]]) -> dict[str, Any]:
    """Return floor metadata. Keys: kind, label, sha, fingerprint, row_counts, worklist_counts."""
    floor: dict[str, Any] = {
        "kind": "since",
        "label": raw,
        "sha": None,
        "fingerprint": None,
        "row_counts": {},
        "worklist_counts": {},
        "alembic_current": None,
        "schema_sets": None,
    }
    if re.fullmatch(r"\d+", raw):
        idx = int(raw)
        if idx < 0 or idx >= len(log):
            die(f"--since log-index {idx} out of range (log has {len(log)} lines)")
        rec = log[idx]
        floor.update(
            {
                "kind": "log-index",
                "label": f"log[{idx}] utc_ts={rec.get('utc_ts')} sha={rec.get('head_sha')}",
                "sha": rec.get("head_sha"),
                "fingerprint": rec.get("schema_fingerprint"),
                "row_counts": rec.get("row_counts") or {},
                "worklist_counts": rec.get("worklist_counts") or {},
                "alembic_current": rec.get("alembic_current"),
                "schema_sets": rec.get("schema_sets"),
            }
        )
        return floor
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", raw):
        full = git(["rev-parse", raw])
        floor["kind"] = "sha"
        floor["sha"] = full
        floor["label"] = f"sha {full[:12]}"
        for rec in reversed(log):
            hs = str(rec.get("head_sha") or "")
            if hs.startswith(raw) or raw.startswith(hs[:7]):
                floor["fingerprint"] = rec.get("schema_fingerprint")
                floor["row_counts"] = rec.get("row_counts") or {}
                floor["worklist_counts"] = rec.get("worklist_counts") or {}
                floor["alembic_current"] = rec.get("alembic_current")
                floor["schema_sets"] = rec.get("schema_sets")
                floor["label"] = f"sha {full[:12]} (matched log utc_ts={rec.get('utc_ts')})"
                break
        return floor
    # ISO date (YYYY-MM-DD or full ISO)
    try:
        if len(raw) == 10:
            datetime.strptime(raw, "%Y-%m-%d")
        else:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        die(f"--since not iso-date, sha, or log-index: {raw}")
    floor["kind"] = "iso-date"
    floor["label"] = f"git --since={raw}"
    # Prefer last log line at or before this date for fingerprints.
    cutoff = raw[:10]
    for rec in reversed(log):
        ts = str(rec.get("utc_ts") or "")[:10]
        if ts and ts <= cutoff:
            floor["fingerprint"] = rec.get("schema_fingerprint")
            floor["row_counts"] = rec.get("row_counts") or {}
            floor["worklist_counts"] = rec.get("worklist_counts") or {}
            floor["alembic_current"] = rec.get("alembic_current")
            floor["schema_sets"] = rec.get("schema_sets")
            floor["sha"] = rec.get("head_sha")
            floor["label"] = f"iso-date {raw}; fingerprint from log utc_ts={rec.get('utc_ts')}"
            break
    if not floor["sha"]:
        hashes = [
            h.strip()
            for h in git(
                ["log", f"--since={raw}", "--pretty=format:%H"],
                check=False,
            ).splitlines()
            if h.strip()
        ]
        if hashes:
            oldest = hashes[-1]
            parent = git(["rev-parse", f"{oldest}^"], check=False).strip()
            floor["sha"] = parent if parent else oldest
            floor["label"] = f"iso-date {raw}; git floor {floor['sha'][:12]}"
    return floor


def parse_alembic_files() -> tuple[dict[str, str | None], list[str]]:
    """revision -> down_revision; list of revision ids."""
    graph: dict[str, str | None] = {}
    for path in sorted(ALEMBIC_VERSIONS.glob("*.py")):
        if path.name.startswith("__"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(
            r"^revision(?:\s*:\s*[\w\[\],. |]+)?\s*=\s*['\"]([^'\"]+)",
            text,
            re.M,
        )
        if not m:
            continue
        rev = m.group(1)
        dm = re.search(
            r"^down_revision(?:\s*:\s*[\w\[\],. |]+)?\s*=\s*(.+)$",
            text,
            re.M,
        )
        down_raw = dm.group(1).strip() if dm else "None"
        if down_raw in {"None", "none"}:
            graph[rev] = None
        else:
            qm = re.match(r"['\"]([^'\"]+)['\"]", down_raw)
            graph[rev] = qm.group(1) if qm else down_raw.split(",")[0].strip().strip("'\"")
    return graph, list(graph.keys())


def children_of(graph: dict[str, str | None], current: str) -> list[str]:
    kids = [r for r, d in graph.items() if d == current]
    out = list(kids)
    for k in kids:
        out.extend(children_of(graph, k))
    return out


def heads(graph: dict[str, str | None]) -> list[str]:
    downs = set(graph.values()) - {None}
    return sorted(r for r in graph if r not in downs)


def schema_fingerprint(cur: Any) -> tuple[str, dict[str, set[str]]]:
    cols = fetch_all(
        cur,
        "SELECT table_name, column_name, data_type "
        "FROM information_schema.columns "
        "WHERE table_schema = 'public' "
        "ORDER BY table_name, column_name",
    )
    cons = fetch_all(
        cur,
        "SELECT c.conname FROM pg_constraint c "
        "JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname = 'public' ORDER BY c.conname",
    )
    idxs = fetch_all(
        cur,
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' ORDER BY indexname",
    )
    lines = [f"col:{t}.{c}:{typ}" for t, c, typ in cols]
    lines += [f"con:{n[0]}" for n in cons]
    lines += [f"idx:{n[0]}" for n in idxs]
    digest = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    sets = {
        "tables": {t for t, _, _ in cols},
        "columns": {f"{t}.{c}" for t, c, _ in cols},
        "constraints": {n[0] for n in cons},
        "indexes": {n[0] for n in idxs},
    }
    return digest, sets


def delta_sets(now: set[str], then: set[str] | None) -> str:
    if then is None:
        return "(no prior fingerprint — delta unavailable)"
    added = sorted(now - then)
    dropped = sorted(then - now)
    bits = []
    if added:
        bits.append("added: " + ", ".join(added[:80]) + (" …" if len(added) > 80 else ""))
    if dropped:
        bits.append("dropped: " + ", ".join(dropped[:80]) + (" …" if len(dropped) > 80 else ""))
    return "; ".join(bits) if bits else "(none)"


CLOSED_STATUS_RE = re.compile(
    r"\b(Done|Closed|Shipped|Resolved|Proven live)\b",
    re.I,
)

# Derived from SELECT file_name, count(*) FROM import_job GROUP BY 1 on cip (2026-08-16):
# pytest stubs only. The previous `dsi([._].*)?` branch matched production names such as
# dsi_week32.xlsx. Tightened 2026-08-16: dsi / dsi.csv / dsi.xlsx / dsi_<one-char>.csv|xlsx.
# `position('test' in lower(file_name))` still false-positives on "latest" (jobs 276/763).
IMPORT_JOB_FIXTURE_FILENAME_RE = (
    r"^(dsi(\.(csv|xlsx))?|dsi_[a-z0-9]\.(csv|xlsx)|run[0-9]+\.xlsx|"
    r"validate\.xlsx|multi\.xlsx|stamp_gate\.csv|week[0-9].*|lineup_api_.*|"
    r"ambig_.*|historical_lineup\.xlsx|bulk_lineup_preview_.*)$"
)
IMPORT_JOB_FIXTURE_SQL = (
    "(position('test' in lower(coalesce(file_name, ''))) > 0 "
    f"OR coalesce(file_name, '') ~* '{IMPORT_JOB_FIXTURE_FILENAME_RE}')"
)
IMPORT_JOB_FIXTURE_PREDICATE = (
    "position('test' in lower(file_name)) > 0 OR file_name ~* "
    f"'{IMPORT_JOB_FIXTURE_FILENAME_RE}'"
)


def parse_backlog_entries(text: str) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    blocks = re.split(r"\n(?=## BACKLOG-)", text)
    for block in blocks:
        hm = re.match(r"## (BACKLOG-\S+)\s+—\s+(.+)", block)
        if not hm:
            continue
        sm = re.search(r"\| \*\*Status / parked\*\* \| ([^\n]+)", block)
        items.append(
            {
                "id": hm.group(1),
                "title": hm.group(2).strip(),
                "status": sm.group(1).strip() if sm else "",
            }
        )
    return items


def open_backlog_items(text: str | None = None) -> list[str]:
    if text is None:
        text = (REPO_ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8-sig")
    items: list[str] = []
    for ent in parse_backlog_entries(text):
        if CLOSED_STATUS_RE.search(ent["status"]):
            continue
        items.append(f"{ent['id']} — {ent['title']}")
    return items


def _skip_artifact_dir(path: Path) -> bool:
    skip = {"node_modules", ".venv", "venv", ".git", ".tmp", ".next"}
    return any(part in skip for part in path.parts)


def _parse_junit(path: Path) -> dict[str, Any] | None:
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError):
        return None
    suites = [root] if root.tag.endswith("testsuite") else list(root.iter())
    tests = failures = skipped = errors = 0
    failed_names: list[str] = []
    skipped_names: list[str] = []
    for el in suites:
        tag = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if tag != "testsuite":
            continue
        tests += int(el.attrib.get("tests") or 0)
        failures += int(el.attrib.get("failures") or 0)
        skipped += int(el.attrib.get("skipped") or 0)
        errors += int(el.attrib.get("errors") or 0)
        for case in el.iter():
            ctag = case.tag.split("}")[-1] if "}" in case.tag else case.tag
            if ctag != "testcase":
                continue
            name = f"{case.attrib.get('classname', '')}::{case.attrib.get('name', '')}".strip(":")
            for child in list(case):
                cht = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if cht in {"failure", "error"}:
                    failed_names.append(name)
                elif cht == "skipped":
                    skipped_names.append(name)
    return {
        "tests": tests,
        "failures": failures,
        "skipped": skipped,
        "errors": errors,
        "failed_names": failed_names,
        "skipped_names": skipped_names,
    }


def last_test_section(floor_ts: int | None) -> list[str]:
    """JUnit/xml newer than floor only. Does not consult pytest cache."""
    candidates: list[Path] = []
    for pat in ("**/junit*.xml", "**/*pytest*.xml", "**/test-results/**/*.xml"):
        candidates.extend(REPO_ROOT.glob(pat))
    artifacts: list[Path] = []
    for path in candidates:
        if _skip_artifact_dir(path) or not path.is_file():
            continue
        if floor_ts is not None and path.stat().st_mtime < floor_ts:
            continue
        artifacts.append(path)
    if not artifacts:
        return [
            "NO TEST EVIDENCE — suites not executed by this script; no artifact newer than floor"
        ]
    lines: list[str] = []
    for path in sorted(artifacts)[:8]:
        parsed = _parse_junit(path)
        rel = path.relative_to(REPO_ROOT).as_posix()
        if not parsed:
            lines.append(f"artifact {rel}: unreadable xml")
            continue
        lines.append(
            f"artifact {rel}: pass={parsed['tests'] - parsed['failures'] - parsed['errors'] - parsed['skipped']} "
            f"fail={parsed['failures']} error={parsed['errors']} skip={parsed['skipped']} tests={parsed['tests']}"
        )
        for n in parsed["failed_names"][:40]:
            lines.append(f"  FAILED: {n}")
        if parsed["skipped_names"]:
            lines.append("SKIPPED test names:")
            for n in parsed["skipped_names"][:80]:
                lines.append(f"  {n}")
        else:
            lines.append("SKIPPED test names: (none in artifact)")
    return lines


def git_show_ok(spec: str) -> str | None:
    r = subprocess.run(
        ["git", "show", spec],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode != 0:
        return None
    return r.stdout


def normalize_doc(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")


def file_identical_to_remote(rel: str, branch: str, working: str) -> bool:
    remote = git_show_ok(f"origin/{branch}:{rel}")
    if remote is None:
        return False
    return normalize_doc(remote) == normalize_doc(working)


def is_ancestor(maybe_anc: str, desc: str) -> bool:
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", maybe_anc, desc],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return r.returncode == 0


def change_area(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("apps/api/alembic/versions/"):
        return "alembic versions"
    if p.startswith("apps/api/"):
        return "apps/api"
    if p.startswith("apps/web/"):
        return "apps/web"
    if p.startswith("docs/"):
        return "docs"
    return "other"


def format_jobs(rows: list[tuple[Any, ...]]) -> list[str]:
    if not rows:
        return ["  (none)"]
    lines = []
    for jid, st, stage, slug, fname, created in rows:
        lines.append(f"  #{jid} {st}/{stage} {slug} {fname} {created}")
    return lines


def build_narrative(
    *,
    context_md: str,
    current_md: str,
    floor_sha: str | None,
    head_sha: str,
    beyond: list[str],
    commits_since: str,
) -> list[str]:
    """Assessment, not a restatement of [1] or [7]. Every item line ends in a sha."""
    in_window: set[str] = set()
    for ln in (commits_since or "").splitlines():
        if ln.strip():
            in_window.add(ln.strip().split()[0])

    def in_floor_window(sha: str) -> bool:
        if not sha:
            return False
        if any(sha.startswith(h) or h.startswith(sha[:7]) for h in in_window):
            return True
        if floor_sha and is_ancestor(floor_sha, sha) and is_ancestor(sha, head_sha) and sha != floor_sha:
            return True
        return False

    complete: list[str] = []
    for ln in context_md.splitlines():
        if "VERIFY PASS" not in ln:
            continue
        shas = re.findall(r"`([0-9a-f]{7,40})`", ln)
        title_m = re.search(r"\*\*(.+?)\*\*", ln)
        title = title_m.group(1) if title_m else ln.strip()[:80]
        impl = shas[0] if shas else ""
        if not impl or not in_floor_window(impl):
            continue
        complete.append(f"  {title} {impl}")
        if len(complete) >= 6:
            break

    partial: list[str] = []
    for ln in current_md.splitlines():
        if not ln.startswith("- "):
            continue
        if "VERIFY PASS" in ln:
            continue
        sm = re.search(r"`([0-9a-f]{7,40})`", ln)
        if not sm:
            continue
        sha = sm.group(1)
        if not in_floor_window(sha):
            continue
        text = re.sub(r"^-\s+", "", ln).strip()
        missing = "no VERIFY stamp in CONTEXT"
        if "catch-up" in ln.lower():
            missing = "no focused test; generator only"
        partial.append(f"  {text[:90]} — missing: {missing} {sha}")
        if len(partial) >= 5:
            break

    unproven: list[str] = []
    for ln in (commits_since or "").splitlines():
        low = ln.lower()
        if not ln.strip():
            continue
        sha = ln.strip().split()[0]
        subj = ln.strip()[len(sha) :].strip()
        if re.search(r"\b(truncate|wipe|drop legacy|destructive)\b", low):
            unproven.append(f"  destructive path committed; no e2e artifact in [6] — {subj} {sha}")
        if len(unproven) >= 4:
            break
    for rev in beyond[:3]:
        unproven.append(f"  alembic {rev} on disk beyond cip current; not applied this run {head_sha[:12]}")

    review: list[str] = [
        f"  apps/web/src/app/(app)/admin/cst-steward/CstArticleAliasesSection.tsx — CST aliases face 49ccec4",
        f"  apps/api/app/api/v1/endpoints/cst_steward.py — alias JSON / sales_model join 49ccec4",
        f"  apps/web/src/features/settings/SemanticCatalogOverlayPanel.tsx — overlay editor 24d2cf3",
        f"  apps/api/alembic/versions/20260814_0016_customer_term_cover_weeks.py — disk alembic head 62607c2",
        f"  scripts/claude_catchup.py — Claude-in-browser snapshot generator 3d5c01a",
    ]
    # Drop review lines whose sha is not in the window if floor is after that sha.
    kept_review = []
    for ln in review:
        sm = re.search(r"([0-9a-f]{7,40})$", ln.strip())
        if sm and in_floor_window(sm.group(1)):
            kept_review.append(ln)
        elif sm:
            kept_review.append(ln)  # still the files a reviewer should open; sha is the landing commit
    review = kept_review[:5]

    out = ["SHIPPED-COMPLETE:"]
    out.extend(complete or [])
    out.append("SHIPPED-PARTIAL:")
    out.extend(partial or [])
    out.append("UNPROVEN:")
    out.extend(unproven or [])
    out.append("REVIEW-FIRST:")
    out.extend(review)
    return out[:25]


def build_divergence(
    *,
    current_md: str,
    branch: str,
    head_sha: str,
    head_list: list[str],
    alembic_current: str | None,
    beyond: list[str],
    unpushed: bool,
    dirty: list[str],
) -> list[str]:
    lines: list[str] = []
    m_code = re.search(r"\*\*Alembic \(code\):\*\* `([^`]+)`", current_md)
    m_cip = re.search(r"\*\*Alembic on cip:\*\* `([^`]+)`", current_md)
    claim_code = m_code.group(1) if m_code else None
    claim_cip = m_cip.group(1) if m_cip else None
    disk_head = head_list[0] if len(head_list) == 1 else None
    if disk_head and alembic_current and claim_code and claim_cip and len({disk_head, str(alembic_current), claim_code, claim_cip}) == 1:
        lines.append(
            f"OK  alembic 3-way: disk_head={disk_head} cip={alembic_current} "
            f"CURRENT_code={claim_code} CURRENT_cip={claim_cip}"
        )
    else:
        lines.append(
            f"FLAG alembic 3-way: disk_heads={head_list} cip={alembic_current} "
            f"CURRENT_code={claim_code} CURRENT_cip={claim_cip}"
        )

    m_branch = re.search(r"\*\*Branch:\*\* `([^`]+)`", current_md)
    claim_branch = m_branch.group(1) if m_branch else None
    if claim_branch == branch:
        lines.append(f"OK  branch: CURRENT.md={claim_branch} git={branch}")
    else:
        lines.append(f"FLAG branch: CURRENT.md={claim_branch!r} git={branch!r}")

    m_upd = re.search(r"\*\*Last updated:\*\* (\d{4}-\d{2}-\d{2})", current_md)
    last_upd = m_upd.group(1) if m_upd else None
    head_date = git(["log", "-1", "--format=%cs"], check=False).strip()
    if last_upd and head_date and last_upd >= head_date:
        lines.append(f"OK  CURRENT.md Last updated {last_upd} vs newest commit date {head_date}")
    else:
        lines.append(
            f"FLAG CURRENT.md Last updated {last_upd} vs newest commit date {head_date}"
        )

    if beyond:
        lines.append(f"FLAG migration files on disk beyond alembic current: {', '.join(beyond)}")
    else:
        lines.append("OK  migration files on disk beyond alembic current: none")

    if unpushed:
        lines.append("FLAG HEAD not present on remote for this branch")
    else:
        lines.append("OK  HEAD present on remote")

    if dirty:
        lines.append(f"FLAG working tree dirty/untracked: {len(dirty)} line(s)")
    else:
        lines.append("OK  working tree dirty/untracked: clean")

    pins = []
    m_pin = re.search(r"\*\*Last content pin:\*\* `([0-9a-f]{7,40})`", current_md)
    if m_pin:
        pins.append(("Last content pin", m_pin.group(1)))
    seen = {p[1] for p in pins}
    for sha in re.findall(r"`([0-9a-f]{7,40})`", current_md):
        if sha in seen:
            continue
        if git(["cat-file", "-t", sha], check=False).strip() != "commit":
            continue
        pins.append(("CURRENT.md sha", sha))
        seen.add(sha)
    bad = []
    ok_pins = []
    for label, sha in pins:
        if is_ancestor(sha, head_sha):
            ok_pins.append(sha)
        else:
            bad.append(f"{label} {sha}")
    if bad:
        for b in bad:
            lines.append(f"FLAG pin hash is not an ancestor of HEAD: {b}")
    elif ok_pins:
        lines.append("OK  pin hashes in CURRENT.md are ancestors of HEAD: " + ", ".join(ok_pins[:12]))
    else:
        lines.append("OK  pin hashes in CURRENT.md: none found")
    return lines


def redact(text: str) -> str:
    return BANNED.sub("[redacted-cursor-term]", text)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Claude-in-browser catch-up snapshot")
    ap.add_argument(
        "--since",
        help="Override delta floor: ISO date, git sha, or JSONL log-index (0-based)",
    )
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    log = read_log()
    bootstrap = not log
    if bootstrap and not args.since:
        die("NO PRIOR MARKER — full snapshot, deltas unavailable. Re-run with explicit --since.")
    if bootstrap:
        print("NO PRIOR MARKER — full snapshot, deltas unavailable")

    if args.since:
        floor = parse_since(args.since, log)
    else:
        rec = log[-1]
        floor = {
            "kind": "last-log",
            "label": f"last log utc_ts={rec.get('utc_ts')} sha={rec.get('head_sha')}",
            "sha": rec.get("head_sha"),
            "fingerprint": rec.get("schema_fingerprint"),
            "row_counts": rec.get("row_counts") or {},
            "worklist_counts": rec.get("worklist_counts") or {},
            "alembic_current": rec.get("alembic_current"),
            "schema_sets": rec.get("schema_sets"),
        }

    floor_commit_iso: str | None = None
    floor_ts: int | None = None
    if floor.get("sha"):
        floor_commit_iso = git(["log", "-1", "--format=%cI", str(floor["sha"])], check=False).strip() or None
        raw_ct = git(["log", "-1", "--format=%ct", str(floor["sha"])], check=False).strip()
        if raw_ct.isdigit():
            floor_ts = int(raw_ct)

    try:
        import psycopg
    except ImportError:
        die("psycopg not installed. Use apps/api/.venv python to run this script.")

    url = resolve_sync_url()
    masked = mask_url(url)
    print(f"resolved DATABASE_URL_SYNC (password masked): {masked}")

    conn = psycopg.connect(url, autocommit=True)
    conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
    cur = conn.cursor()
    dbname = fetch_one(cur, "SELECT current_database()")
    print(f"current_database(): {dbname}")
    if dbname != "cip":
        conn.close()
        die(f"STOP: current_database() is {dbname!r}, expected 'cip'. No further queries.")

    host = fetch_one(cur, "SELECT inet_server_addr()::text")
    user = fetch_one(cur, "SELECT current_user")

    alembic_current = fetch_one(cur, "SELECT version_num FROM alembic_version LIMIT 1")
    graph, all_revs = parse_alembic_files()
    head_list = heads(graph)
    beyond = sorted(children_of(graph, alembic_current)) if alembic_current else []

    fp, now_sets = schema_fingerprint(cur)

    fact_dim = fetch_all(
        cur,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "AND (starts_with(table_name, 'fact_') OR starts_with(table_name, 'dim_')) "
        "ORDER BY table_name",
    )
    row_counts: dict[str, int] = {}
    for (tname,) in fact_dim:
        if not re.fullmatch(r"(fact|dim)_[a-z0-9_]+", tname):
            continue
        row_counts[tname] = int(fetch_one(cur, f'SELECT count(*)::bigint FROM "{tname}"'))

    jobs_all = fetch_all(
        cur,
        "SELECT id, status, stage, template_slug, file_name, "
        "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
        "FROM import_job ORDER BY id DESC LIMIT 10",
    )
    jobs_real = fetch_all(
        cur,
        "SELECT id, status, stage, template_slug, file_name, "
        "to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') "
        "FROM import_job WHERE NOT " + IMPORT_JOB_FIXTURE_SQL + " "
        "ORDER BY id DESC LIMIT 10",
    )
    fixture_in_window: int | None = None
    if floor_commit_iso:
        fixture_in_window = int(
            fetch_one(
                cur,
                "SELECT count(*)::bigint FROM import_job "
                "WHERE created_at >= %s::timestamptz AND " + IMPORT_JOB_FIXTURE_SQL,
                (floor_commit_iso,),
            )
            or 0
        )

    worklist_counts: dict[str, int] = {}
    worklist_errors: dict[str, str] = {}
    for spec in WORKLIST_SPECS:
        try:
            worklist_counts[spec["key"]] = int(fetch_one(cur, spec["sql"]))
        except Exception as exc:  # noqa: BLE001 — missing relation is a reported count, not a crash
            worklist_errors[spec["key"]] = str(exc).split("\n")[0][:200]
            worklist_counts[spec["key"]] = -1
            cur = conn.cursor()

    conn.close()

    # Git
    subprocess.run(["git", "fetch", "origin"], cwd=REPO_ROOT, capture_output=True)
    branch = git(["branch", "--show-current"])
    head_sha = git(["rev-parse", "HEAD"])
    head_short = git(["rev-parse", "--short", "HEAD"])
    head_subj = git(["log", "-1", "--pretty=format:%s"])
    upstream = git(["rev-parse", "--abbrev-ref", "@{u}"], check=False).strip()
    ahead, behind = 0, 0
    if upstream:
        lr = git(["rev-list", "--left-right", "--count", f"{upstream}...HEAD"], check=False)
        parts = lr.replace("\t", " ").split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])
    porcelain = git(["status", "--porcelain"], check=False)
    dirty = [ln for ln in porcelain.splitlines() if ln.strip()]
    remote_ref = f"origin/{branch}" if branch else ""
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", head_sha, remote_ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    unpushed = ancestor.returncode != 0

    floor_sha = floor.get("sha")
    if args.since and floor.get("kind") == "iso-date" and not floor_sha:
        commits_since = git(["log", "--since", args.since, "--pretty=format:%h %s"], check=False)
    elif floor_sha:
        commits_since = git(["log", f"{floor_sha}..HEAD", "--pretty=format:%h %s"], check=False)
    else:
        commits_since = git(["log", "-20", "--pretty=format:%h %s"], check=False)

    origin_url = git(["remote", "get-url", "origin"], check=False).strip()
    changed_files = ""
    if floor_sha:
        changed_files = git(["diff", "--name-only", f"{floor_sha}..HEAD"], check=False)
    elif args.since and floor.get("kind") == "iso-date":
        changed_files = git(["log", "--since", args.since, "--name-only", "--pretty=format:"], check=False)
        changed_files = "\n".join(sorted({ln for ln in changed_files.splitlines() if ln.strip()}))

    current_md = (REPO_ROOT / "docs" / "memory" / "CURRENT.md").read_text(encoding="utf-8-sig")
    context_md = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8-sig")
    backlog_text = (REPO_ROOT / "docs" / "BACKLOG.md").read_text(encoding="utf-8-sig")
    changelog = []
    for ln in context_md.splitlines():
        if ln.startswith("- 20"):
            changelog.append(ln)
        if len(changelog) >= 3:
            break
    backlog_open = open_backlog_items(backlog_text)
    test_lines = last_test_section(floor_ts)

    prior_fp = floor.get("fingerprint")
    prior_schema_sets = floor.get("schema_sets") or None
    schema_delta_lines = []
    if prior_schema_sets:
        kind_map = {
            "tables": now_sets["tables"],
            "columns": now_sets["columns"],
            "constraints": now_sets["constraints"],
            "indexes": now_sets["indexes"],
        }
        any_change = False
        for kind, now_kind in kind_map.items():
            then = set(prior_schema_sets.get(kind) or [])
            line = delta_sets(now_kind, then)
            schema_delta_lines.append(f"{kind}: {line}")
            if line != "(none)":
                any_change = True
        if not any_change:
            schema_delta_lines.insert(0, "fingerprint/sets unchanged vs floor" if prior_fp == fp else "sets equal; fingerprint field differed")
    elif prior_fp and prior_fp == fp:
        schema_delta_lines.append("fingerprint unchanged vs floor (no stored sets — name-level add/drop n/a)")
    elif not prior_fp:
        schema_delta_lines.append("NO PRIOR FINGERPRINT — schema delta unavailable")
    else:
        schema_delta_lines.append(f"floor fingerprint: {prior_fp}")
        schema_delta_lines.append(f"now fingerprint:   {fp}")
        schema_delta_lines.append("(set-level add/drop vs floor not stored; fingerprint mismatch)")

    # Prior log may not store table sets; only fingerprint. Data/worklist deltas use stored counts.
    prior_rows: dict[str, Any] = floor.get("row_counts") or {}
    prior_wl: dict[str, Any] = floor.get("worklist_counts") or {}

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def dlt(now: int, key: str, prior: dict[str, Any]) -> str:
        if key not in prior or now < 0:
            return "delta n/a"
        try:
            p = int(prior[key])
        except (TypeError, ValueError):
            return "delta n/a"
        return f"delta {now - p:+d}"

    narrative = build_narrative(
        context_md=context_md,
        current_md=current_md,
        floor_sha=str(floor_sha) if floor_sha else None,
        head_sha=head_sha,
        beyond=beyond,
        commits_since=commits_since,
    )
    flags = build_divergence(
        current_md=current_md,
        branch=branch,
        head_sha=head_sha,
        head_list=head_list,
        alembic_current=alembic_current,
        beyond=beyond,
        unpushed=unpushed,
        dirty=dirty,
    )

    now_backlog = {e["id"]: e for e in parse_backlog_entries(backlog_text)}
    floor_backlog: dict[str, dict[str, str]] = {}
    if floor_sha:
        old_bl = git_show_ok(f"{floor_sha}:docs/BACKLOG.md")
        if old_bl:
            floor_backlog = {e["id"]: e for e in parse_backlog_entries(old_bl)}
    status_changed: list[str] = []
    for bid in sorted(set(now_backlog) | set(floor_backlog)):
        old_st = (floor_backlog.get(bid) or {}).get("status", "(absent)")
        new_st = (now_backlog.get(bid) or {}).get("status", "(absent)")
        if old_st != new_st:
            title = (now_backlog.get(bid) or floor_backlog.get(bid) or {}).get("title", "")
            status_changed.append(f"  {bid} — {title} | {old_st} → {new_st}")

    cf = [ln for ln in (changed_files or "").splitlines() if ln.strip()]
    area_counts: dict[str, int] = {}
    for p in cf:
        area_counts[change_area(p)] = area_counts.get(change_area(p), 0) + 1
    alembic_added: list[str] = []
    if floor_sha:
        alembic_added = [
            ln
            for ln in git(
                ["diff", "--name-only", "--diff-filter=A", f"{floor_sha}..HEAD", "--", "apps/api/alembic/versions"],
                check=False,
            ).splitlines()
            if ln.strip()
        ]

    dirty_names: list[str] = []
    for ln in dirty:
        path = ln[3:].strip() if len(ln) > 3 else ln
        if " -> " in path:
            path = path.split(" -> ")[-1]
        dirty_names.append(path)

    out: list[str] = []
    out.append(AUDIENCE)
    if unpushed:
        out.append("BRANCH UNPUSHED — Claude cannot read this tree")
    if bootstrap:
        out.append("NO PRIOR MARKER — full snapshot, deltas unavailable")
    out.append(f"generated-at: {generated_at}")
    out.append(f"script-version: {SCRIPT_VERSION}")
    out.append(f"delta-floor: {floor['label']}")
    out.append("")
    out.append("[1] REPO")
    out.append(f"branch: {branch}")
    out.append(f"upstream: {upstream or '(none)'}")
    out.append(f"ahead: {ahead}  behind: {behind}")
    out.append(f"HEAD: {head_short} {head_subj}")
    out.append("dirty+untracked:")
    if dirty:
        out.extend(f"  {ln}" for ln in dirty)
    else:
        out.append("  (clean)")
    out.append("commits since floor:")
    if commits_since.strip():
        out.extend(f"  {ln}" for ln in commits_since.splitlines())
    else:
        out.append("  (none)")
    out.append("")
    out.append("[2] MIGRATIONS")
    out.append(f"db: {dbname}  host: {host}  user: {user}")
    out.append(f"alembic current: {alembic_current}")
    out.append(f"alembic heads: {', '.join(head_list) if head_list else '(none parsed)'}")
    out.append(f"multiple-heads: {str(len(head_list) > 1).lower()}")
    out.append("migration files on disk beyond current:")
    if beyond:
        out.extend(f"  {r}" for r in beyond)
    else:
        out.append("  (none)")
    out.append("")
    out.append("[3] SCHEMA DELTA")
    out.append(f"schema_fingerprint: {fp}")
    out.extend(schema_delta_lines)
    out.append("")
    out.append("[4] DATA")
    out.append("row counts (fact_* / dim_* enumerated from information_schema):")
    for tname in sorted(row_counts):
        extra = dlt(row_counts[tname], tname, prior_rows)
        out.append(f"  {tname}: {row_counts[tname]} ({extra})")
    out.append(f"import_job fixture predicate: {IMPORT_JOB_FIXTURE_PREDICATE}")
    if fixture_in_window is None:
        out.append("fixture-looking import_job in floor window: n/a (no floor commit timestamp)")
    else:
        out.append(f"fixture-looking import_job in floor window: {fixture_in_window}")
    out.append("last 10 import_job (all):")
    out.extend(format_jobs(jobs_all))
    out.append("last 10 import_job (excluding test fixtures):")
    out.extend(format_jobs(jobs_real))
    out.append("")
    out.append("[5] WORKLISTS")
    out.append("Queues enumerated from code (not assumed). Each count is SELECT-only.")
    for spec in WORKLIST_SPECS:
        k = spec["key"]
        n = worklist_counts.get(k, -1)
        err = worklist_errors.get(k)
        extra = dlt(n, k, prior_wl)
        if err:
            out.append(f"  {k}: ERROR {err}")
        else:
            out.append(f"  {k}: {n} ({extra})")
        out.append(f"    found: {spec['found']}")
    out.append("")
    out.append("[6] TESTS")
    if len(test_lines) == 1 and test_lines[0].startswith("NO TEST EVIDENCE"):
        out.append(test_lines[0])
    else:
        out.extend(test_lines)
    out.append("")
    out.append("[7] DOCS")
    current_rel = "docs/memory/CURRENT.md"
    context_rel = "CONTEXT.md"
    backlog_rel = "docs/BACKLOG.md"
    if file_identical_to_remote(current_rel, branch, current_md):
        out.append(f"{current_rel}: clean vs remote — fetch from repo")
    else:
        out.append(f"{current_rel}: DIRTY vs remote — working copy follows")
        out.append("--- CURRENT.md ---")
        out.extend(current_md.splitlines())
    if file_identical_to_remote(context_rel, branch, context_md):
        out.append(f"{context_rel}: clean vs remote — fetch from repo")
    else:
        out.append(f"{context_rel}: DIRTY vs remote — newest 3 changelog headers follow")
        out.append("--- newest 3 CONTEXT.md changelog headers ---")
        out.extend(changelog or ["(none)"])
    out.append(f"BACKLOG.md open-item count: {len(backlog_open)}")
    if file_identical_to_remote(backlog_rel, branch, backlog_text):
        out.append(f"{backlog_rel}: clean vs remote — fetch from repo")
    else:
        out.append(f"{backlog_rel}: DIRTY vs remote — open items follow")
        out.append("--- open BACKLOG.md (id + title; Status not Done/Closed/Shipped/Resolved/Proven live) ---")
        if backlog_open:
            out.extend(f"  {ln}" for ln in backlog_open)
        else:
            out.append("  (none)")
    out.append("BACKLOG status changed since floor:")
    if status_changed:
        out.extend(status_changed)
    else:
        out.append("  (none)")
    out.append("")
    out.append("[8] NARRATIVE")
    out.extend(narrative)
    out.append("")
    out.append("[9] DIVERGENCE FLAGS")
    out.extend(flags)
    out.append("")
    out.append("[10] REVIEW POINTER")
    out.append(f"repo: {origin_url}")
    out.append(f"branch: {branch}")
    out.append(f"HEAD: {head_sha}")
    out.append(f"floor sha: {floor_sha or '(none)'}")
    out.append(f"changed-file count since floor: {len(cf)}")
    out.append("changed-file breakdown:")
    for area in ("apps/api", "apps/web", "docs", "alembic versions", "other"):
        out.append(f"  {area}: {area_counts.get(area, 0)}")
    out.append("alembic version files added since floor:")
    if alembic_added:
        out.extend(f"  {ln}" for ln in alembic_added)
    else:
        out.append("  (none)")
    out.append("dirty/untracked working tree files:")
    if dirty_names:
        out.extend(f"  {ln}" for ln in dirty_names)
    else:
        out.append("  (none)")
    out.append("")

    body = redact("\n".join(out) + "\n")
    if BANNED.search(body):
        die("generated output still contained banned token; aborting write")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {OUT_PATH.relative_to(REPO_ROOT)}")

    marker = {
        "utc_ts": generated_at,
        "head_sha": head_sha,
        "branch": branch,
        "alembic_current": alembic_current,
        "schema_fingerprint": fp,
        "schema_sets": {k: sorted(v) for k, v in now_sets.items()},
        "row_counts": row_counts,
        "worklist_counts": {k: v for k, v in worklist_counts.items() if v >= 0},
    }
    with LOG_PATH.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(marker, sort_keys=True) + "\n")
    print(f"appended {LOG_PATH.relative_to(REPO_ROOT)}")

    # Print full snapshot to stdout so the operator can paste it.
    print("--- BEGIN CLAUDE_CATCHUP.md ---")
    print(body, end="" if body.endswith("\n") else "\n")
    print("--- END CLAUDE_CATCHUP.md ---")

    if unpushed:
        print("BRANCH UNPUSHED — Claude cannot read this tree", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
