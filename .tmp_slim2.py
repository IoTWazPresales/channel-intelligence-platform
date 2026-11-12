from pathlib import Path
raw = Path(r"C:\Users\warren_eliason\agent-tools\6365fc0c-0b7e-4c4f-9467-43f0afcd313f.txt").read_bytes()
text = raw.replace(b"\x00", b"").decode("utf-8", "replace")
Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200\scan14-clean.txt").write_text(text, encoding="utf-8")
# Also extract key sections with ascii
out = []
for ln in text.splitlines():
    if ln.startswith("====") or ln.startswith("SE "):
        out.append(ln)
    elif "not_activated" in ln or "promo_not" in ln:
        out.append(ln[:200])
    elif "change-event" in ln.lower() or "change_event" in ln or "/change" in ln:
        out.append(ln[:200])
    elif ln.startswith("apps/web") and ("ship" in ln or "brief" or "overview" in ln):
        if "ship" in ln or "brief" in ln or "overview" in ln or "inbound" in ln:
            out.append(ln)
Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200\scan14-key.txt").write_text("\n".join(out[:300]), encoding="utf-8")
print("wrote", len(text), "keylines", len(out))
