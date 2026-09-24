"""N-0038 one-shot edit helper: swap get_current_user for the role dependency on named CPOR write views.

Kept as evidence of exactly which views were changed. Idempotent guard: asserts one match per view.
"""

import pathlib
import re

base = pathlib.Path(__file__).resolve().parents[4] / "apps/api/app/api/v1/endpoints"
plan = {
    "cpor_cases.py": {
        "_require_cpor_planner": [
            "create_case", "patch_case", "set_intelligence_exclude", "preview_supersede_case",
            "supersede_case_endpoint", "restore_supersede_case", "create_line", "patch_line", "void_line",
            "split_layers", "recompute", "transition_case", "cpor_promo_plan_recompute",
            "cpor_promo_plan_create_case", "import_claim_evidence", "post_settlement_rollup",
        ]
    },
    "cpor_exports.py": {"_require_cpor_planner": ["generate_export"]},
    "cpor_fx.py": {"_require_cpor_planner": ["fx_rate_fetch", "fx_backfill_confirm", "fx_declare_mode"]},
    "cpor_historical_import.py": {
        "_require_cpor_historical_writer": [
            "historical_map_token", "historical_bulk_map_token", "historical_validate", "historical_apply",
            "historical_resolution_plan_generate", "historical_resolution_plan_compute_async",
            "historical_resolution_plan_apply_async",
        ]
    },
    "cpor_payment_evidence.py": {"_require_cpor_steward": ["map_token", "mark_shell", "re_resolve", "apply_job"]},
}

for fname, mapping in plan.items():
    p = base / fname
    src = p.read_text(encoding="utf-8")
    for dep, fns in mapping.items():
        for fn in fns:
            mt = re.search(r"\n(?:async )?def %s\(" % re.escape(fn), src)
            assert mt, (fname, fn)
            start = mt.end()
            sig = re.search(r"\)(\s*->[^\n]*)?:\n", src[start:])
            assert sig, (fname, fn)
            sig_end = start + sig.end()
            seg = src[start:sig_end]
            assert seg.count("Depends(get_current_user)") == 1, (fname, fn, seg)
            src = src[:start] + seg.replace("Depends(get_current_user)", f"Depends({dep})") + src[sig_end:]
            print(fname, fn, "->", dep)
    p.write_text(src, encoding="utf-8")
