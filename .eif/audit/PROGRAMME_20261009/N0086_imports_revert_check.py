"""N-0086 check: are the 5 imports page test failures caused by the N-0086 hunks?

Writes TEMPORARY sibling copies (removed with --clean):
  apps/web/src/app/(app)/admin/imports/pageN0086Revert.tsx       page.tsx with the N-0086 hunks reversed
  apps/web/src/app/(app)/admin/imports/pageN0086Revert.test.tsx  page.test.tsx importing that copy
Run from the repository root:  python .eif/audit/PROGRAMME_20261009/N0086_imports_revert_check.py [--clean]
"""

import os
import sys

D = os.path.join(os.getcwd(), "apps", "web", "src", "app", "(app)", "admin", "imports")
PAGE = os.path.join(D, "page.tsx")
TEST = os.path.join(D, "page.test.tsx")
OUT_PAGE = os.path.join(D, "pageN0086Revert.tsx")
OUT_TEST = os.path.join(D, "pageN0086Revert.test.tsx")

if "--clean" in sys.argv:
    for p in (OUT_PAGE, OUT_TEST):
        if os.path.exists(p):
            os.remove(p)
            print("removed", os.path.basename(p))
    sys.exit(0)

s = open(PAGE, encoding="utf-8", newline="").read().replace("\r\n", "\n")
reps = [
    (
        "import { StewardWriteFieldset, StewardWriteNotice } from '@/components/StewardWriteGate';\n"
        "import { canRunImportTemplate, useStewardWriteAccess } from '@/features/shell/stewardAccess';\n",
        "",
    ),
    (
        "  // N-0086: steward imports need steward or admin; planners keep the CPOR templates and the lineup cards.\n"
        "  const stewardAccess = useStewardWriteAccess();\n"
        "  const wizardWriteAllowed = canRunImportTemplate(stewardAccess, selectedSlug);\n",
        "",
    ),
    (
        "      <StewardWriteNotice\n"
        "        access={stewardAccess}\n"
        '        id="import-center-steward-notice"\n'
        "        extra={\n"
        "          stewardAccess.role === 'planner'\n"
        "            ? 'The lineup import cards, CPOR historical cases and payment evidence still work for planners.'\n"
        "            : undefined\n"
        "        }\n"
        "      />\n",
        "",
    ),
    (
        "                    disabled={!canRunImportTemplate(stewardAccess, t.slug)}\n"
        "                    aria-describedby={\n"
        "                      canRunImportTemplate(stewardAccess, t.slug) ? undefined : 'import-center-steward-notice'\n"
        "                    }\n"
        "                    data-testid={`import-template-card-${t.slug}`}\n",
        "",
    ),
    ('        <StewardWriteFieldset disabled={!wizardWriteAllowed} describedBy="import-center-steward-notice">\n', ""),
    ("        </StewardWriteFieldset>\n", ""),
]
for old, new in reps:
    assert s.count(old) == 1, old[:80]
    s = s.replace(old, new)
open(OUT_PAGE, "w", encoding="utf-8", newline="\n").write(s)

t = open(TEST, encoding="utf-8", newline="").read().replace("\r\n", "\n")
old = "import AdminImportsPage from './page';\n"
assert t.count(old) == 1
t = t.replace(old, "import AdminImportsPage from './pageN0086Revert';\n")
open(OUT_TEST, "w", encoding="utf-8", newline="\n").write(t)
print("wrote", os.path.basename(OUT_PAGE), os.path.basename(OUT_TEST))
