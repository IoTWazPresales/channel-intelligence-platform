from pathlib import Path
p = Path("_session_f_cip_test_evidence.py")
t = p.read_text(encoding="utf-8")
t = t.replace('"ORDER BY line_id LIMIT 1"', '"ORDER BY id LIMIT 1"')
old = '''        run_query(
            session,
            f"SELECT line_id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
            f"WHERE case_id = {int(new_case_id)} ORDER BY line_id",
            f"B4 lines for case_id={new_case_id}",
        )'''
new = '''        run_query(
            session,
            f"SELECT id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
            f"WHERE case_id = {int(new_case_id)} ORDER BY id",
            f"B4 lines for case_id={new_case_id} (id column; no line_id in schema)",
        )
        try:
            run_query(
                session,
                f"SELECT line_id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
                f"WHERE case_id = {int(new_case_id)} ORDER BY line_id",
                f"User-requested SQL line_id for case_id={new_case_id}",
            )
        except Exception as exc:
            print(f"--- User-requested SQL line_id for case_id={new_case_id} ---")
            print(
                f"SELECT line_id, cost_source, estimate_qty, cost_basis FROM cpor_case_line "
                f"WHERE case_id = {int(new_case_id)} ORDER BY line_id"
            )
            print(exc)
            print()'''
if old not in t:
    raise SystemExit('block not found')
p.write_text(t.replace(old, new), encoding='utf-8')
print('ok')
