from pathlib import Path
raw = Path(r"C:\Users\warren_eliason\agent-tools\6365fc0c-0b7e-4c4f-9467-43f0afcd313f.txt").read_bytes()
text = raw.replace(b"\x00", b"").decode("utf-8", "replace")
# Keep only section headers and first lines of each
lines = text.splitlines()
keep = []
for i, ln in enumerate(lines):
    if ln.startswith("====") or ln.startswith("SE ") or (ln and not ln.startswith("origin/") and i < 200):
        keep.append(ln)
    elif ln.startswith("origin/") and ("change" in ln.lower() or "not_activated" in ln or "Attention" in ln or "ship" in ln.lower()):
        keep.append(ln[:180])
Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200\scan14-slim.txt").write_text("\n".join(keep[:250]), encoding="utf-8")
print("\n".join(keep[:250]))
