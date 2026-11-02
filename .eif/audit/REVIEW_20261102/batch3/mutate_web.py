"""Mutation harness for the web fixes (batch 2 and 3): break ONE fix at a time, run the tests written for it, restore the file.

Run from the repo root:  python .eif/audit/REVIEW_20261102/batch3/mutate_web.py [label fragment ...]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WEB = "apps/web/"
B3 = "src/features/dashboards/builder/chartsBatch3.test.tsx"

MUTATIONS = [
    ("sort menu: saved Z-A shows A-Z", "src/features/workbench-ui/ChartControls.tsx",
     "return s.dir === 'desc' ? 'name-desc' : 'name-asc';", "return 'name-asc';", [B3]),
    ("top N: a saved 50 has no pressed button", "src/features/workbench-ui/ChartControls.tsx",
     "if (typeof current !== 'number' || !Number.isFinite(current) || current <= 0 || TOP_N_OPTIONS.includes(current)) return [...TOP_N_OPTIONS];",
     "return [...TOP_N_OPTIONS];", [B3]),
    ("legend lists series the top N left out", "src/features/workbench-ui/charts.tsx",
     "const series = categoryAxis\n    ? allSeries.filter(", "const series = false\n    ? allSeries.filter(", [B3]),
    ("comparison ranks by the first category's series", "src/features/workbench-ui/charts.tsx",
     "value: (r) => toNumber(rankKey ? r[rankKey] : allSeries[0]", "value: (r) => toNumber(false ? r[rankKey!] : allSeries[0]", [B3]),
    ("table widget ignores the saved sort", "src/features/dashboards/builder/V2WidgetBody.tsx",
     "useChartControls(categoryPresentation(sort, topN, measureIds, breakdownIds, 10), true)",
     "useChartControls(categoryPresentation(undefined, topN, ['m'], [], 10), true)", [B3]),
    ("dual axis has no category controls", "src/features/dashboards/builder/V2WidgetBody.tsx",
     "categoryAxis={dualCategory} initialControls", "categoryAxis={false} initialControls", [B3]),
    ("editor and chart disagree on the default top N", "src/features/dashboards/builder/TopNSelect.tsx",
     "return visual === 'hbar' ? 15 : 10;", "return 15;", [B3]),
    ("tiles follow a vessel click", "src/app/(app)/shipping/buildShippingLinesUrl.ts",
     "return unchanged ? previous : own;", "return own;",
     ["src/app/(app)/shipping/buildShippingLinesUrl.test.ts", "src/app/(app)/shipping/ShippingCommercialSummary.test.tsx"]),
    ("a label is reserved a fixed 160 px", "src/features/supply-inbound/onTheWater/layout.ts",
     "return Math.ceil(Math.max(title.length * 7.2, sub.length * 5.6) + 24);", "return 160;",
     ["src/features/supply-inbound/onTheWater/onTheWater.rules.test.ts"]),
    ("placeLabels ignores an anchor's own size", "src/features/supply-inbound/onTheWater/layout.ts",
     "const own = a.size ?? size;", "const own = size;", ["src/features/supply-inbound/onTheWater/onTheWater.rules.test.ts"]),
    ("a label that fits no corner is dropped", "src/features/supply-inbound/onTheWater/layout.ts",
     "[a.x + gap.x, a.y - 2 * gap.y - 2 * own.h], // right, one box higher", "[a.x + gap.x, a.y - gap.y - own.h], // right, one box higher",
     ["src/features/supply-inbound/onTheWater/onTheWater.rules.test.ts"]),
    ("category axis draws keys, not names", "src/features/workbench-ui/charts.tsx",
     "fill: c.axis, fontSize: 10.5, format: xTickFormat })}", "fill: c.axis, fontSize: 10.5 })}", [B3]),
    ("a port name is wider than its avoid box", "src/features/supply-inbound/onTheWater/layout.ts",
     "export const PORT_NAME_PX_PER_LETTER = 8.4;", "export const PORT_NAME_PX_PER_LETTER = 7.6;",
     ["src/features/supply-inbound/onTheWater/OnTheWater.test.tsx"]),
    ("the map caption sits on the map again", "src/features/supply-inbound/onTheWater/OnTheWater.tsx",
     "{!narrow ? <DurbanNote /> : null}", "{!narrow ? <><DurbanNote /><MapCaption /></> : null}",
     ["src/features/supply-inbound/onTheWater/OnTheWater.test.tsx"]),
    ("a new caller may skip the axis titles", "src/features/dashboards/builder/V2WidgetBody.tsx",
     "unit={measureUnit(left)}", "", ["src/features/workbench-ui/chartCallers.test.ts"]),
]


def main() -> int:
    only = sys.argv[1:]
    for label, rel, old, new, tests in MUTATIONS:
        if only and not any(o in label for o in only):
            continue
        path = ROOT / WEB / rel
        original = path.read_bytes()
        text = original.decode("utf-8")
        if "\r\n" in text:
            old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
        if old not in text:
            print(f"{label:55s} -> MUTATION TEXT NOT FOUND")
            continue
        try:
            path.write_bytes(text.replace(old, new, 1).encode("utf-8"))
            proc = subprocess.run(
                ["npm", "--prefix", "apps/web", "run", "test", "--", "--run", *tests], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True,
            )
            lines = [ln for ln in (proc.stdout + proc.stderr).splitlines() if "Tests " in ln]
            import re
            summary = re.sub(r"\x1b\[[0-9;]*m", "", (lines[-1] if lines else "")).strip().encode("ascii", "replace").decode()
            print(f"{label:55s} -> exit {proc.returncode}: {summary}")
        finally:
            path.write_bytes(original)
            assert path.read_bytes() == original, f"RESTORE FAILED for {rel}"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
