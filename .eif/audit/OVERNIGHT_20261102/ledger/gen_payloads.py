"""Generates ledger payload files for the 2 Nov overnight session (writes only JSON payloads next to itself)."""
import json
import pathlib

root = pathlib.Path(__file__).resolve().parent
SRC = "Warren, 2 November 2026"


def w(name, obj):
    (root / name).write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


decisions = {
    "dec_priority_order": {
        "scope": None,
        "origin": "operator",
        "status": "accepted",
        "statement": (
            f"Priority order ({SRC}): (1) close N-0114, N-0115 and N-0116 through one independent review that also covers On the water and the shipment fixes; "
            "(2) N-0100 extended: a job per user (account manager, product manager, finance, country manager, admin) plus the customer accounts each user covers, with dashboards, Brief and Attention defaulting to My accounts and a My accounts starter dashboard; "
            "(3) load the staged-but-unloaded store-level data for whichever customers are found, from the data, to hold it; "
            "(4) new inception module Store and DC replenishment (store sales and stock, customer DC stock where a DC is evidenced, DC to store needs, which distributor supplies a site from distributor stock with learned lead times, slow and unsold stock with a suggested path, the store map), with N-0110 and N-0108 folded in; "
            "(5) competition and customer websites: N-0102, then N-0105, N-0106, N-0104, N-0103, N-0076, N-0077; "
            "(6) enablers: N-0074, N-0089, N-0111, N-0088; "
            "(7) later: N-0094, N-0097, N-0098, N-0084, N-0070 and the blocked or deferred nodes. "
            "Source: docs/memory/CLAUDE_CHAT_HANDOVER_20261102.md, section Priority order."
        ),
    },
    "dec_store_dc_core": {
        "scope": "N-0117",
        "origin": "operator",
        "status": "accepted",
        "statement": (
            f"Store and distribution-centre level sales, stock and replenishment are a core priority and are not deferred ({SRC}; settled decision 6, first stated 30 October). "
            "A store is never aliased to its parent customer."
        ),
    },
    "dec_channel_chain": {
        "scope": "N-0117",
        "origin": "operator",
        "status": "accepted",
        "statement": (
            f"Channel chain ({SRC}; settled decision 7): ASUS to distributor, then the customer's site levels. A distribution centre, where one is evidenced, belongs to the customer and not to the distributor. "
            "The chain is tenant configuration, not code."
        ),
    },
    "dec_direct_indirect": {
        "scope": "N-0117",
        "origin": "operator",
        "status": "accepted",
        "statement": (
            f"Direct and indirect customers ({SRC}; settled decision 8, stated generically): a customer is direct when ASUS ships to a receiving site of the customer, and indirect when it buys through a distributor. "
            "An indirect customer's DC, where one exists, appears only as a site in that customer's own reports. One customer DC can serve several accounts of one retail group. "
            "Which sites are DCs is decided by the DC level rule, never by account name."
        ),
    },
    "dec_dc_detection": {
        "scope": "N-0117",
        "origin": "operator",
        "status": "accepted",
        "statement": (
            f"DC detection ({SRC}; settled decision 9): name patterns (tenant configuration) and stock behaviour (high stock, no consumer sales) propose a DC candidate; "
            "a steward confirms each DC once and the confirmation is remembered. Nothing is created without that confirmation."
        ),
    },
    "dec_my_accounts": {
        "scope": "N-0100",
        "origin": "operator",
        "status": "accepted",
        "statement": (
            f"My accounts default ({SRC}; settled decision 10, delegated by Warren): account managers default to their own accounts through a My accounts filter that they can clear. "
            "There is no database restriction. A per-user restriction can come later if needed."
        ),
    },
    "dec_dc_level_rule": {
        "scope": "N-0117",
        "origin": "operator",
        "status": "accepted",
        "statement": (
            f"DC level rule ({SRC}): every site has a level (distributor stock, customer DC, store, other) and an owner (distributor or customer). "
            "A distributor's warehouse or business-unit account is distributor-level stock and is never a customer DC; a distributor-owned site cannot be set to customer DC. "
            "A customer DC exists only on evidence: a customer report or an ASUS shipment names the site as a distribution or fulfilment centre, or a steward confirms it once (remembered). "
            "Name patterns and stock behaviour only propose a candidate; a candidate is not a DC until confirmed; never auto-create. "
            "With no stated DC there is no DC level: stock sits at store or account level supplied through the distributor, and the module must not invent a DC. "
            "Open question (separate proposed decision, Task 4): whether ASUS shipping directly to a customer's receiving site is sufficient evidence of a DC on its own."
        ),
    },
}
for k, v in decisions.items():
    w(k + ".json", v)

evidence = {
    "ev_census": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/STORE_DC_CENSUS_20261030/REPORT.md",
        "note": "Evidence for N-0117 Store and DC replenishment: read-only census of store and DC level data on cip (30 October 2026).",
    },
    "ev_otw_step8": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/ON_THE_WATER_20261029/STEP8_REPORT.md",
        "note": "Evidence for N-0119 (retroactive): steps 6-8, migration 20261101_0049 and the backfill clone proof.",
    },
    "ev_otw_step9": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/ON_THE_WATER_20261029/STEP9_REPORT.md",
        "note": "Evidence for N-0119 (retroactive): step 9, the endpoint, filters, Attention row, map and port-conditions page.",
    },
    "ev_otw_step10": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/ON_THE_WATER_20261029/STEP10_STOP_REPORT.md",
        "note": "Evidence for N-0119 (retroactive): step 10, migration 0050, PO-less twin retire and job 1697 re-process.",
    },
    "ev_otw_step11": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/ON_THE_WATER_20261029/STEP11_REPORT.md",
        "note": "Evidence for N-0119 (retroactive): step 11, fixes from the 2 November review.",
    },
    "ev_otw_step12": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/ON_THE_WATER_20261029/STEP12_CIP_APPLY.md",
        "note": "Evidence for N-0119 (retroactive): step 12, the cip apply.",
    },
    "ev_otw_audit_events": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/REVIEW_20261102/FINDINGS.md",
        "note": "Evidence for N-0119 (retroactive): platform_audit_event 22 (voyage backfill, 0049) and 26 (orphan open retire, job 1697) matched read-only by the GOV-008 review; section Audit events.",
    },
    "ev_otw_deploy": {
        "provenance": "implementation-observation",
        "path": ".eif/audit/REVIEW_20261102/DEPLOY_20261102.md",
        "note": "Evidence for N-0119 (retroactive): deploy of 2 November 2026, migration 20261102_0051, web rebuild and restart, figures after.",
    },
}
for k, v in evidence.items():
    w(k + ".json", v)
print("ok", len(decisions), len(evidence))
