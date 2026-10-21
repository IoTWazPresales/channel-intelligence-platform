from pathlib import Path

root = Path(".")
listed = Path(".eif/audit/PROGRAMME_20260924/n0045/archive_list.final.txt")
names = [line.strip() for line in listed.read_text(encoding="utf-8").splitlines() if line.strip()]
present = [name for name in names if (root / name).exists()]
print(f"listed {len(names)} present {len(present)}")
for name in present:
    print(name)
