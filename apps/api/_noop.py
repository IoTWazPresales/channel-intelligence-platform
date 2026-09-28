from pathlib import Path
p = Path("_session_f_cip_test_evidence.py")
t = p.read_text(encoding="utf-8")
t = t.replace("ORDER BY line_id LIMIT 1", "ORDER BY id LIMIT 1")
t = t.replace(
    f"SELECT line_id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
    f"WHERE case_id = {{int(new_case_id)}} ORDER BY line_id",
    "SELECT id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
    "WHERE case_id = :case_id ORDER BY id",
)
# fix f-string in file - read actual content
