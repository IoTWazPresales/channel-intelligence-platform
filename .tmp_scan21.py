from pathlib import Path
dlg = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200\BulkLineupBackfillDialog.tsx").read_text(encoding="utf-8")
lines = dlg.splitlines()
for i, ln in enumerate(lines, 1):
    if "applyFinished" in ln or "applySummary" in ln or "applySession" in ln or "Link POs" in ln or "next step" in ln.lower() or "po-management" in ln or "Completion" in ln or "cases created" in ln:
        print(f"{i}:{ln[:180]}")
print("--- UI around 700-829 ---")
for i in range(700, min(829, len(lines))):
    print(f"{i+1}:{lines[i][:160]}")
