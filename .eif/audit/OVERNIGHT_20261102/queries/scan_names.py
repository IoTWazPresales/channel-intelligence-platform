"""Read-only text scan for hardcoded names. Writes a TSV to the path given as argv[1]."""
import os, re, sys

ROOTS = ["apps/api/app", "apps/api/alembic", "apps/api/scripts", "scripts", "apps/web/src", "packages"]
EXT = {".py", ".ts", ".tsx", ".yaml", ".yml", ".js", ".cjs", ".ps1", ".sql", ".mjs"}
SKIP_DIRS = {"node_modules", "__pycache__", ".next", "dist", "build"}
TERMS = r"""pepkor|\bgame\b|makro|massmart|takealot|amazon|computer\s*mania|compumania|evetech|hifi|hi-fi|incredible\s*connection|jd\s*furniture|cash\s*crusaders|pinnacle|mustek|syntech|compuspeed|rectron|axiz|esquire|ingram|brackengate|gosforth|\bACZA\b|Wza2607|CUST-1001|DIST-01|-ZA-[A-Z]{2}-\d\d|\bdurban\b|\bcape\s*town\b|\bjohannesburg\b|\bwoolworths\b|\bcheckers\b|\bshoprite\b|\bbuild\s*it\b|\bwhere\s*to\b|\bdreamwave\b|\btarget\s*dc\b"""
RX = re.compile(TERMS, re.I)


def kind(p):
    pl = p.replace("\\", "/").lower()
    if "design-lab" in pl or "/__tests__/" in pl or "/tests/" in pl or "/test-utils/" in pl or "/fixtures" in pl or "/seed" in pl or "/e2e" in pl:
        return "TEST_FIXTURE"
    b = os.path.basename(pl)
    if ".test." in b or ".spec." in b or b.startswith("test_") or b.endswith("_test.py") or b == "conftest.py" or "seed" in b or "fixture" in b:
        return "TEST_FIXTURE"
    if pl.startswith("apps/api/alembic"):
        return "MIGRATION"
    return "PRODUCT"


dest = sys.argv[1] if len(sys.argv) > 1 else None
out = open(dest, "w", encoding="utf-8") if dest else sys.stdout
nfiles = 0
for root in ROOTS:
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            if os.path.splitext(fn)[1] not in EXT:
                continue
            p = os.path.join(dp, fn).replace("\\", "/")
            nfiles += 1
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        m = RX.search(line)
                        if m:
                            out.write(f"{kind(p)}\t{p}:{i}\t{m.group(0)}\t{line.strip()[:220]}\n")
            except Exception as e:
                out.write(f"ERR\t{p}\t\t{e}\n")
out.write(f"#FILES\t{nfiles}\n")
if dest:
    out.close()
