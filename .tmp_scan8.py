from pathlib import Path
import re
p = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200\BACKLOG-tip.md")
raw = p.read_bytes()
print("bom", raw[:4], "nul", raw.count(b"\x00"), "cr", raw.count(b"\r"), "lf", raw.count(b"\n"))
bl = raw.replace(b"\x00", b"").decode("utf-8")
# find exact
idx = bl.find("BACKLOG-199")
print("idx199", idx)
print(repr(bl[idx-5:idx+80]) if idx>=0 else "none")
idx = bl.find("## BACKLOG-199")
print("idx hdr", idx, repr(bl[idx:idx+90]) if idx>=0 else None)
# try split
parts = re.split(r'(?m)^## BACKLOG-', bl)
print("split parts", len(parts))
print("first hdrs", [parts[i][:40].replace("\n"," ") for i in range(1,6)])
