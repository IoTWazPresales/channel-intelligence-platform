from pathlib import Path
dlg = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200\BulkLineupBackfillDialog.tsx").read_text(encoding="utf-8")
lines = dlg.splitlines()
print("total", len(lines))
for i in range(250, 420):
    print(f"{i+1}:{lines[i]}")
print("--- apply mutation / completion panel ---")
for i, ln in enumerate(lines, 1):
    if "onClose(" in ln or "completion" in ln.lower() or "Apply complete" in ln or "setApplySession" in ln or "applyMutation" in ln or "isApplying" in ln:
        print(f"{i}:{ln[:180]}")
