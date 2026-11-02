"""Read-only probe (GOV-008 review 2026-11-02): list every JSX use of the shared chart components
under apps/web/src and report which axis-title / unit / click / controls props each passes.
Heuristic brace-depth-aware JSX scan, not a TS parser. Test files are skipped."""
import pathlib
import re
import sys

ROOT = pathlib.Path(sys.argv[1])
NAMES = ["CategoryBars", "PairedBars", "TrendChart", "RankedBars", "ShareChart", "ScatterPlot", "Sparkline"]
PROPS = ["xAxisTitle", "yAxisTitle", "unit", "format", "summary", "onRowClick", "onPointClick", "datumActions",
         "controls", "initial", "initialControls", "categoryAxis", "timeAxis", "xUnit", "layout", "horizontal"]
pat = re.compile(r"<(" + "|".join(NAMES) + r")\b")
for f in sorted(ROOT.rglob("*.tsx")):
    if f.name.endswith(".test.tsx"):
        continue
    s = f.read_text(encoding="utf-8")
    for m in pat.finditer(s):
        i = m.end()
        depth = 0
        while i < len(s):
            ch = s[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            elif ch == ">" and depth == 0:
                break
            i += 1
        tag = s[m.start():i + 1]
        line = s.count("\n", 0, m.start()) + 1
        present = [p for p in PROPS if re.search(r"\b" + p + r"\s*=", tag)]
        rel = f.relative_to(ROOT).as_posix()
        print(f"{rel}:{line} {m.group(1)} [{','.join(present)}]")
