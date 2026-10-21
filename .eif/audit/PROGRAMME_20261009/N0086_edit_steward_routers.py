"""N-0086 one-off editor: steward-write role gates on cst_steward, mappings, product_master_gaps, exceptions.

Files are CRLF; read with universal newlines and write back CRLF so only the edited lines change.
"""

import os
import re

ROOT = os.getcwd()
EP = os.path.join(ROOT, "apps", "api", "app", "api", "v1", "endpoints")

GATE_COMMENT = (
    "# N-0086: steward writes need steward or admin (admin always passes require_roles); reads stay sign-in only.\n"
)


def edit(name, import_old, import_new, anchor, writes):
    p = os.path.join(EP, name)
    s = open(p, encoding="utf-8").read()
    if import_old is not None:
        assert s.count(import_old) == 1, (name, import_old)
        s = s.replace(import_old, import_new)
    assert s.count(anchor) == 1, (name, anchor)
    s = s.replace(
        anchor,
        anchor + "\n" + GATE_COMMENT + "_STEWARD_WRITE = [Depends(require_roles(Role.ADMIN, Role.STEWARD))]\n",
    )
    for method, path in writes:
        pat = re.compile(r'@router\.' + method + r'\("' + re.escape(path) + r'"(?P<rest>[^)\n]*)\)\n')
        m = list(pat.finditer(s))
        assert len(m) == 1, (name, method, path, len(m))
        rest = m[0].group("rest")
        assert "dependencies" not in rest, (name, path)
        s = s[: m[0].start()] + f'@router.{method}("{path}"{rest}, dependencies=_STEWARD_WRITE)\n' + s[m[0].end():]
    open(p, "w", encoding="utf-8", newline="\r\n").write(s)
    print(name, len(writes), "gated")


edit(
    "cst_steward.py",
    None,
    None,
    "router = APIRouter()\n",
    [
        ("patch", "/key-accounts/{customer_id}"),
        ("post", "/report-slots/advance"),
        ("post", "/article-aliases/import"),
        ("post", "/article-aliases/confirm-import"),
        ("patch", "/article-aliases/{alias_id}"),
        ("post", "/article-aliases/derive-eras-from-shipping"),
        ("post", "/article-aliases/confirm-shipping-derived"),
        ("post", "/article-aliases/reresolve-job-residuals"),
        ("post", "/article-aliases/{alias_id}/confirm"),
        ("post", "/article-aliases/{alias_id}/reject"),
    ],
)

edit(
    "mappings.py",
    None,
    None,
    "router = APIRouter()\n",
    [
        ("post", "/queue/{item_id}/approve"),
        ("post", "/queue/{item_id}/reject"),
        ("delete", "/queue/{item_id}"),
        ("post", "/queue/clear-all"),
        ("post", "/import-candidates/{candidate_id}/resolve-product"),
        ("post", "/import-candidates/{candidate_id}/map-customer"),
        ("post", "/import-candidates/{candidate_id}/duplicate-review/different-entity"),
        ("post", "/import-candidates/{candidate_id}/duplicate-review/same-entity"),
        ("post", "/import-jobs/{job_id}/duplicate-review/cluster-same-entity"),
        ("post", "/import-candidates/{candidate_id}/create-provisional-customer"),
        ("post", "/import-candidates/{candidate_id}/mark-open-channel"),
        ("post", "/import-candidates/{candidate_id}/ignore"),
        ("post", "/import-candidates/{candidate_id}/map-distributor"),
        ("post", "/import-candidates/{candidate_id}/create-provisional-distributor"),
        ("post", "/import-jobs/{job_id}/dsi-steward-bulk-preview"),
        ("post", "/import-jobs/{job_id}/dsi-steward-bulk-provisional-customers/apply-async"),
        ("post", "/import-jobs/{job_id}/dsi-steward-bulk-ignore/apply-async"),
        ("post", "/import-jobs/{job_id}/dsi-steward-bulk-apply"),
        ("post", "/import-jobs/{job_id}/dsi-resolution-plan/compute-async"),
        ("post", "/import-jobs/{job_id}/dsi-resolution-plan"),
        ("post", "/import-jobs/{job_id}/dsi-resolution-plan/effective"),
        ("post", "/import-jobs/{job_id}/dsi-resolution-plan/apply-async"),
        ("post", "/import-jobs/{job_id}/dsi-resolution-plan/apply"),
        ("post", "/import-jobs/{job_id}/revalidate-distributor-sales-inventory"),
        ("post", "/customer-source-token-aliases"),
    ],
)

_SEC_OLD = "from app.api.deps import get_db\n"
_SEC_NEW = "from app.api.deps import get_db\nfrom app.core.security import Role, require_roles\n"

edit(
    "product_master_gaps.py",
    _SEC_OLD,
    _SEC_NEW,
    "router = APIRouter()\n",
    [("post", "/scan"), ("post", "/preview"), ("post", "/apply")],
)

edit(
    "exceptions.py",
    _SEC_OLD,
    _SEC_NEW,
    "router = APIRouter()\n",
    [("delete", "/{item_id}"), ("post", "/clear-all")],
)
