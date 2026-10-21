"""One-off patch for import_load_report.py (N-0111 repair 2): repeated distributor lines are summed or counted once."""

import pathlib

p = pathlib.Path("apps/api/app/services/imports/import_load_report.py")
s = p.read_text(encoding="utf-8")


def sub(old: str, new: str) -> None:
    global s
    assert s.count(old) == 1, old[:90]
    s = s.replace(old, new)


sub(
    """  whose sale or stock part did not load is partly loaded; a line a later line of the same load
  replaced (same invoice, product, date and customer) did not load; otherwise not matched, no date,
  no figures, or waiting to apply.""",
    """  whose sale or stock part did not load is partly loaded; a line that repeats an earlier line of
  the same load (same invoice, product, date and customer) is loaded: summed into it when it
  differs, counted once when identical in every source column (D-0091); otherwise not matched, no
  date, no figures, or waiting to apply.""",
)
sub(
    """    "repeated_line": "Same invoice, product, date and customer again in this load; the later line replaced it (kept as superseded)",
""",
    "",
)
start = s.index('_DSI_REPEATED = """')
end = s.index("_DSI_SQL = ")
s = s[:start] + s[end:]
sub(
    """SELECT s.import_job_id, CASE
    WHEN {repeated} THEN 'repeated_line'
    WHEN s.apply_status <> 'pending'""",
    """SELECT s.import_job_id, CASE
    WHEN s.apply_status LIKE 'duplicate%' THEN 'duplicate'
    WHEN s.apply_status <> 'pending'""",
)
sub(
    """FROM import_distributor_si_staging_line s
{join}
WHERE""",
    """FROM import_distributor_si_staging_line s
WHERE""",
)
start = s.index("def _dsi_sql(has_superseded: bool) -> str:")
end = s.index("def display_status(")
s = s[:start] + s[end:]
sub("text(_dsi_sql(bool(db.scalar(text(_HAS_SUPERSEDED)))))", "text(_DSI_SQL)")
sub(
    """        has = bool((await db.execute(text(_HAS_SUPERSEDED))).scalar())
        grouped = _group((await db.execute(text(_dsi_sql(has)), {"ids": by_kind[DSI]})).all())""",
    """        grouped = _group((await db.execute(text(_DSI_SQL), {"ids": by_kind[DSI]})).all())""",
)
p.write_text(s, encoding="utf-8")
print("patched")
