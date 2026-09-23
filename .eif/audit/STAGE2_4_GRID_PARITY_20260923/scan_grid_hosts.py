"""N-0034 discovery: per-host grid feature scan (read-only heuristics; every hit is spot-checked by hand).

Run from the repo root: python -B .eif/audit/STAGE2_4_GRID_PARITY_20260923/scan_grid_hosts.py
"""
import re
import sys
from pathlib import Path

ROOT = Path('apps/web/src')
MOUNT = re.compile(r'<EnterpriseDataGrid\b')
SHELL = re.compile(r'<MasterDataGridShell\b')

FEATURES = {
    'search': re.compile(r'[Ss]earch|quickFilter|placeholder=["\'][^"\']*(?:[Ff]ind|[Ff]ilter)'),
    'colfilter_off': re.compile(r'filter:\s*false'),
    'floating': re.compile(r'floatingFilter:\s*true'),
    'chips': re.compile(r'<ScopeBar\b|<Chip\b[^>]*onDelete|<ToggleButtonGroup\b|\bselect\b\s*(?:\n|\s)*label=|<Select\b|TextField[^>]*\bselect\b'),
    'views': re.compile(r'savedView|SavedView|smartView|SmartView'),
    'picker': re.compile(r'<ColumnPickerDialog\b|<ColumnSelectorModal\b|<MasterColumnPickerDialog\b'),
    'export': re.compile(r'exportDataAs|[Ee]xport CSV|Download CSV|toCsv|downloadCsv|\.csv[\'"`]'),
    'toolbar': re.compile(r'<ModuleGridToolbar\b'),
    'mds': re.compile(r'<ModuleDataSection\b'),
}


def main() -> int:
    files = sorted(p for p in ROOT.rglob('*.tsx')
                   if '.test.' not in p.name and (MOUNT.search(t := p.read_text(encoding='utf-8')) or SHELL.search(t)))
    total = 0
    print('file\tmounts\tshell\t' + '\t'.join(FEATURES))
    for p in files:
        text = p.read_text(encoding='utf-8')
        mounts = len(MOUNT.findall(text))
        shells = len(SHELL.findall(text))
        total += mounts
        cells = []
        for name, rx in FEATURES.items():
            lines = [str(i + 1) for i, ln in enumerate(text.splitlines()) if rx.search(ln)]
            cells.append(','.join(lines[:6]) + ('+' if len(lines) > 6 else '') if lines else '-')
        print(f'{p.relative_to(ROOT).as_posix()}\t{mounts}\t{shells}\t' + '\t'.join(cells))
    print(f'TOTAL_MOUNTS\t{total}\tFILES\t{len(files)}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
