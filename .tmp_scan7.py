from pathlib import Path
import re
bl = Path(r"C:\Users\warren_eliason\cip-run-logs\verify-b200\BACKLOG-tip.md").read_text(encoding="utf-8")
print("len", len(bl))
# sample headers containing BACKLOG-199 etc
for m in re.finditer(r'(?m)^.*BACKLOG-20[0-9].*$', bl):
    print(repr(m.group(0)[:120]))
print("---")
for m in re.finditer(r'(?m)^.*BACKLOG-18[0-9].*$', bl):
    if m.start() < 50: continue
    print(repr(m.group(0)[:140]))
print("---headers sample---")
for m in re.finditer(r'(?m)^#{1,4} .*$', bl):
    h = m.group(0)
    if "BACKLOG" in h or "Stage" in h or "SAFE" in h:
        print(h[:140])
