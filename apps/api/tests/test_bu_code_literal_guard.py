"""N-0040 (D-g) guard: no hardcoded product-line / BU code sets in product source.

The sellable BU grain is every ``dim_product.product_line`` value, served by
``app.services.catalog.product_lines`` and ``GET /api/v1/catalog/product-lines``. A literal list
of three or more two-letter upper-case codes in non-test source is the defect shape this node
removed (e.g. ``{"NB", "NR", "NV"}``). Tests, design-lab fixtures and ops scripts are excluded.
"""

from __future__ import annotations

import re
from pathlib import Path

_APPS = Path(__file__).resolve().parents[2]
_ROOTS = (_APPS / "api" / "app", _APPS / "web" / "src")
_SUFFIXES = {".py", ".ts", ".tsx"}

# Three or more quoted two-letter upper-case codes separated by commas (spans newlines).
_CODE_SET = re.compile(
    r"""(["'])[A-Z]{2}\1\s*,\s*(["'])[A-Z]{2}\2\s*,\s*(["'])[A-Z]{2}\3"""
)


def _excluded(path: Path) -> bool:
    parts = set(path.parts)
    name = path.name
    return (
        "design-lab" in parts
        or "__tests__" in parts
        or "tests" in parts
        or ".test." in name
        or ".spec." in name
        or name.startswith("test_")
    )


def _source_files() -> list[Path]:
    out: list[Path] = []
    for root in _ROOTS:
        for path in root.rglob("*"):
            if path.suffix in _SUFFIXES and path.is_file() and not _excluded(path):
                out.append(path)
    return out


def test_guard_pattern_detects_a_code_set() -> None:
    assert _CODE_SET.search("CODES = frozenset({'NB', 'NR', 'NV'})")
    assert _CODE_SET.search('const X = [\n  "NB",\n  "PF",\n  "XB",\n];')
    assert not _CODE_SET.search("['NB', 'NR']")


def test_no_literal_bu_code_sets_in_source() -> None:
    files = _source_files()
    assert files, "guard scanned no files"
    hits: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in _CODE_SET.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{path.relative_to(_APPS)}:{line}: {m.group(0)!r}")
    assert not hits, (
        "Hardcoded BU/product-line code set(s) found; read the codes from "
        "app.services.catalog.product_lines (API) or useProductLines (web) instead:\n"
        + "\n".join(hits)
    )
