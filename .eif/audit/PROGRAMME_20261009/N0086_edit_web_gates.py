"""N-0086 one-off editor: wrap steward pages in StewardWriteGate (exact-match replacements, keeps line endings).

Run from the repository root:  python .eif/audit/PROGRAMME_20261009/N0086_edit_web_gates.py
"""

import os

ROOT = os.getcwd()
APP = os.path.join(ROOT, "apps", "web", "src", "app", "(app)")
GATE_IMPORT = "import { StewardWriteGate } from '@/components/StewardWriteGate';\n"


def edit(rel, reps):
    p = os.path.join(APP, rel)
    raw = open(p, "rb").read().decode("utf-8")
    crlf = "\r\n" in raw
    s = raw.replace("\r\n", "\n")
    for old, new in reps:
        n = s.count(old)
        assert n == 1, (rel, old[:60], n)
        s = s.replace(old, new)
    if crlf:
        s = s.replace("\n", "\r\n")
    open(p, "wb").write(s.encode("utf-8"))
    print("edited", rel, "crlf" if crlf else "lf")


edit(
    "admin/cst-steward/page.tsx",
    [
        (
            "import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';\n",
            "import { EnterpriseDataGrid } from '@/components/EnterpriseDataGrid';\n" + GATE_IMPORT,
        ),
        (
            '  return (\n    <DataChrome>\n      <Alert severity="info" sx={{ mb: 2 }} data-testid="cst-steward-guide">',
            '  return (\n    <DataChrome>\n      <StewardWriteGate>\n      <Alert severity="info" sx={{ mb: 2 }} data-testid="cst-steward-guide">',
        ),
        (
            "      </Dialog>\n    </DataChrome>\n  );\n}",
            "      </Dialog>\n      </StewardWriteGate>\n    </DataChrome>\n  );\n}",
        ),
    ],
)

edit(
    "admin/mappings/page.tsx",
    [
        (
            "import { ModuleDataSection } from '@/components/ModuleDataSection';\n",
            "import { ModuleDataSection } from '@/components/ModuleDataSection';\n" + GATE_IMPORT,
        ),
        (
            "      >\n        <AdminMappingsPageContent />\n      </Suspense>",
            "      >\n        <StewardWriteGate>\n          <AdminMappingsPageContent />\n        </StewardWriteGate>\n      </Suspense>",
        ),
    ],
)

edit(
    "admin/product-master-gaps/page.tsx",
    [
        (
            "import { DataChrome } from '@/features/data-stewardship/DataChrome';\n",
            GATE_IMPORT + "import { DataChrome } from '@/features/data-stewardship/DataChrome';\n",
        ),
        (
            "    <DataChrome>\n      <ProductMasterGapWorklistView />\n    </DataChrome>",
            "    <DataChrome>\n      <StewardWriteGate>\n        <ProductMasterGapWorklistView />\n      </StewardWriteGate>\n    </DataChrome>",
        ),
    ],
)

edit(
    "admin/shipment-evidence/page.tsx",
    [
        (
            "import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';\n",
            "import { ModuleGridToolbar } from '@/components/ModuleGridToolbar';\n" + GATE_IMPORT,
        ),
        (
            "  return (\n    <SupplyChrome>\n    <Box>\n",
            "  return (\n    <SupplyChrome>\n    <StewardWriteGate>\n    <Box>\n",
        ),
        (
            "      </Dialog>\n    </Box>\n    </SupplyChrome>\n  );\n}",
            "      </Dialog>\n    </Box>\n    </StewardWriteGate>\n    </SupplyChrome>\n  );\n}",
        ),
    ],
)
