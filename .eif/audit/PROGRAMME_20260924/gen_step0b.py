"""Step 0b payloads: proposed decisions for Warren-gated nodes, their blockers, and evidence for built items."""
import json
import pathlib

out = pathlib.Path(__file__).parent / "step0b"
out.mkdir(exist_ok=True)


def w(name, obj):
    (out / f"{name}.json").write_text(json.dumps(obj, indent=1), encoding="utf-8")


gated = {
    # node: (decision id, blocker type, statement)
    "N-0060": ("D-0020", "human", "Historical lineup backfill: Warren supplies the pre-2025 lineup archive and decides whether to load it into cip (a cip write). Options: (a) load all history via the existing bulk-backfill path after N-0058 rules land; (b) load only the years D-h needs; (c) do not load. Blocks D-h depth."),
    "N-0063": ("D-0021", "human", "Uplift from settled claims needs claim-evidence rows (cpor_claim_evidence_line 0 vs 211 settled cases). Unlocked by Warren's customer/distributor data drive, not by code."),
    "N-0065": ("D-0022", "decision", "BU entitlements semantics: default for a user with no mapping (all lines vs none); read-only vs read+write scoping; which surfaces filter (lineup, settlement, stock, reports); admin bypass. Warren decides."),
    "N-0068": ("D-0023", "decision", "BACKLOG-198 catalog_product grain: does catalog_product stay the catalogue, get retired, or is it unrelated to per-line column sets? Warren decides."),
    "N-0071": ("D-0024", "decision", "Stage 4.6 (BACKLOG-062) open->shipped fact double-count remediation policy. Not decided (D-e)."),
    "N-0072": ("D-0025", "decision", "Stage 4.7 (BACKLOG-046) ACZA workbook non-operational sheets (BOM Not Ready) allowlist business rule. Not decided (D-e)."),
}
for nid, (did, btype, st) in gated.items():
    w(f"dec_{nid}", {"id": did, "scope": nid, "statement": st, "origin": "agent", "status": "proposed"})
    w(f"blk_{nid}", {"node": nid, "expected_revision": 0, "type": btype, "ref": did, "note": st})

built = {
    "EV-BUILT-45-MINT": ("66003db9", "Plan 4.5 CIP-minted customer codes is BUILT: 66003db9 (2026-07-10, BACKLOG-061-U2b mint on bulk promote) and 66ae66d9 (distributor mint); customer_code_mint_setting model. Pre-programme work; D-f holds any mint pass."),
    "EV-BUILT-48-ALIAS": ("467bc89e", "Plan 4.8 customer merge alias seal is BUILT: 467bc89e (2026-07-11, seal merge aliases + follow redirects) and fc14962c (2026-08-19, follow merged_into on customer and distributor resolvers). Pre-programme work."),
    "EV-BUILT-S9-DISTMERGE": ("361d138a", "Plan Stage 9 distributor merge is BUILT: 361d138a (2026-06-30, full distributor merge engine with PO consolidation and soft-redirect). Pre-programme work."),
    "EV-BUILT-INBOUND-LQ": ("4d7231f0", "Outside-plan candidate inbound-shipments-by-lineup-quarter filter is BUILT: 4d7231f0 (2026-07-08, lineup plan-quarter filter and derived attribution on the inbound grid); InboundShipmentsWorkspace plan_quarter state + shipping.py lineup-quarter-summary."),
    "EV-BUILT-EXTAPI-SPEC": ("49e08364", "Outside-plan candidate external API layer (spec only until Warren names a consumer) is DONE as spec: docs/EXTERNAL_API_OUTBOUND.md and docs/EXTERNAL_API_INBOUND.md (49e08364, 2026-09-18). No implementation until a first consumer is named."),
}
for eid, (commit, note) in built.items():
    w(f"ev_{eid}", {"id": eid, "provenance": "implementation-observation", "path": f"git:{commit}", "tree_hash": commit, "note": note})

print("ok")
