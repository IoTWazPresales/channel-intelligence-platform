"""List endpoint modules that mention a tenant-owned model without a tenant filter token."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODELS = ROOT / "apps" / "api" / "app" / "models"
ENDPOINTS = ROOT / "apps" / "api" / "app" / "api" / "v1" / "endpoints"


def tenant_models() -> set[str]:
    names: set[str] = set()
    for path in MODELS.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            blob = ast.get_source_segment(source, node) or ""
            if "tenant_id" in blob:
                names.add(node.name)
    return names


def main() -> None:
    models = tenant_models()
    print("TENANT_MODELS", len(models))
    print(" ".join(sorted(models)))
    missing: list[str] = []
    scoped: list[str] = []
    untouched: list[str] = []
    for path in sorted(ENDPOINTS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        hits = sorted(name for name in models if name in text)
        if not hits:
            untouched.append(path.name)
            continue
        filtered = "where_tenant" in text or "tenant_id_from_user" in text or ".tenant_id" in text
        if filtered:
            scoped.append(f"{path.name} ({', '.join(hits)})")
        else:
            missing.append(f"{path.name} ({', '.join(hits)})")
    print("\nSCOPED", len(scoped))
    print("\n".join(scoped))
    print("\nUNSCOPED", len(missing))
    print("\n".join(missing))
    print("\nNO_TENANT_MODEL", len(untouched))


if __name__ == "__main__":
    main()
