"""Generate step-0 ledger payloads (decisions + queue nodes). Writes JSON files under step0/."""
import json
import pathlib

out = pathlib.Path(__file__).parent / "step0"
out.mkdir(exist_ok=True)

decisions = {
    "Da": ("N-0030", "D-a (Warren, 2026-09-23): approve N-0030 once STAGED_WORK_PLAN.md is refreshed (21 Sep section 3 answers, D-g, the 23 Sep stale-item fixes)."),
    "Db": ("N-0034", "D-b (Warren, 2026-09-23): grid search, saved views and export become three separate nodes, each a shared workbench-ui component, dependent on N-0034. The field-list source is the architecture lens's engineering call; it must reuse the inbound-shipments optional-columns pattern if present, with no migration."),
    "Dc": ("N-0032", "D-c (Warren, 2026-09-23): CporCaseWorkspace retires once the desk absorbs the BACKLOG-202 pieces. SettlementPortfolioRead and CporPortfolioIntelligencePanel: if they show intelligence nothing else shows, mount under Promotions & Funding per the lab; if they duplicate existing surfaces, delete them; report which and why."),
    "Dd": (None, "D-d (Warren, 2026-09-23): untracked files move to an archive folder OUTSIDE the repo, never deleted; commit only what is clearly real source, and list it."),
    "De": (None, "D-e (Warren, 2026-09-23): Stage 4.6 (open->shipped double-count policy, BACKLOG-062) and 4.7 (ACZA non-operational sheets allowlist, BACKLOG-046) are NOT decided. Present each in plain language with the lens positions; build nothing for them."),
    "Df": (None, "D-f (Warren, 2026-09-23): no customer code mint pass and no remap of the 7 verified rows for now."),
    "Dg": (None, "D-g (Warren, 2026-09-23): the sellable BU grain is ALL product lines as they appear in dim_product.product_line (Warren counted 16; NX included), not the brief's five. Every hardcoded or assumed five-line set is a defect and becomes config/data-driven. Null product_line rows are a finding. Any lineup supersession behaviour change is proven on a clone first with before/after numbers; a cip repair goes to Warren."),
    "Dh": (None, "D-h (Warren, 2026-09-23): proposed-vs-executed intelligence (plan accuracy, deal-stock landing rates, PM planning bias across years): agent recommends start position and outline via a feature-definition moment (product/commercial, UX/design, architecture lenses); charter as an unstarted node at that position; do not build."),
}
for k, (scope, st) in decisions.items():
    p = {"statement": st, "origin": "operator", "status": "accepted"}
    if scope:
        p["scope"] = scope
    (out / f"dec_{k}.json").write_text(json.dumps(p, indent=1), encoding="utf-8")

COMMON_TAIL = [
    "Nothing writes to cip; read-only SQL prints current_database() first",
    "Tests green on touched areas, tsc exit 0, eslint clean on changed files",
]


def node(i, title, deps, facets, risk, crit, acc="auto"):
    return {
        "id": i, "title": title, "class": "feature", "origin": "operator", "status": "proposed",
        "depends_on": deps, "facets": facets, "risk": risk, "touches_existing": True,
        "acceptance": acc, "acceptance_criteria": crit + COMMON_TAIL,
    }


nodes = [
    node("N-0036", "BACKLOG-206: API binds loopback, not 0.0.0.0:8001", ["N-0030"], ["infra"], "R2", [
        "pnpm dev:api (scripts/dev-api.js) and any documented start path bind the API to loopback only; netstat shows no 0.0.0.0:8001 or [::]:8001 listener",
        "localhost/::1 trap handled: every in-repo caller (web proxy fallback, scripts, runbooks) that targets localhost:8001 is repointed to 127.0.0.1 or the API also answers on ::1; resolution measured on this host",
        "Web same-origin proxy still reaches the API (/api/v1/health 200 via :3000)",
        "BACKLOG-206 stamped; PILOT_TUNNEL_RUNBOOK updated if it names the bind"]),
    node("N-0037", "Stage 3.4: login rate limit and lockout", ["N-0036", "N-0033"], ["auth", "api"], "R2", [
        "Repeated wrong-password attempts on /api/v1/auth/login are throttled per account and per client address; limit and window are config, not literals",
        "Throttled response is 429 with Retry-After; during lockout even a correct password is refused until the window passes; a successful login resets the counter",
        "No enumeration: unknown-user and wrong-password responses are indistinguishable in status and body",
        "Tests cover throttle, reset and non-enumeration; stub mode unaffected"]),
    node("N-0038", "Stage 3.2: CPOR role checks on the existing roles (BACKLOG-136/141)", ["N-0037"], ["auth", "api"], "R2", [
        "Every CPOR write endpoint (incl. export generate, settle, transitions, payment-evidence apply) requires a role from the existing admin/steward/planner/viewer set; viewer is read-only",
        "Shipment steward panels accept STEWARD and ADMIN (BACKLOG-141)",
        "The role matrix used is written into the node evidence; no new roles (Warren 21 Sep: enforce on existing roles)",
        "Tests: one allowed and one denied role per guarded write"]),
    node("N-0039", "Listing links open the real product page (Market & Listings bug)", ["N-0038"], ["api", "ui"], "R2", [
        "Root cause of stored listing URLs that open a marketplace 'doesn't exist' page (at least Takealot) is found in code: PLID normaliser b17e950, URL auto-finder bfd0c44, feed-derived listing seeds; no assumed cause",
        "How the listing data was obtained when the stored URL does not resolve is explained",
        "A SMALL sample per marketplace is checked by GET, rate-limited; no bulk crawling",
        "URL construction fixed at the source, with tests",
        "Links that do not resolve get status dead_link per the registry lifecycle (observed, never deleted); the UI never presents an unverified or dead link as valid",
        "Any repair of stored rows on cip is proven on a clone and listed for Warren, not applied"]),
    node("N-0040", "D-g: sellable BU grain is every dim_product.product_line (five-line assumption sweep)", ["N-0039"], ["api", "ui"], "R2", [
        "Every place that hardcodes or assumes the five-line set (lineup BU derivation, supersession, filters, labels) is enumerated with file:line and made config/data-driven from dim_product.product_line, never a constant",
        "NULL product_line rows in dim_product are reported as a finding with count",
        "Any change to lineup supersession behaviour is proven on a clone first with before/after numbers; a cip repair is listed for Warren, not applied"]),
    node("N-0041", "D-b: shared grid search (workbench-ui) on Tier A grids", ["N-0034"], ["ui"], "R2", [
        "One shared toolbar-search component in features/workbench-ui used by the Tier A grids from N-0034 discovery; no bespoke per-page copies",
        "Field-list source reuses the inbound-shipments optional-columns pattern if present; no migration"]),
    node("N-0042", "D-b: shared saved grid views (workbench-ui)", ["N-0034"], ["ui"], "R2", [
        "One shared saved-views component in features/workbench-ui: name, save, apply, delete a grid layout (columns, sort, filters) per layout key",
        "Reuses the N-0034 layout key; storage decision recorded; no migration unless this node charters one"]),
    node("N-0043", "D-b: shared grid export (workbench-ui, community AG Grid)", ["N-0034"], ["ui"], "R2", [
        "One shared export action in features/workbench-ui: CSV of visible columns and filtered rows, community module only (BACKLOG-193 stays dropped)",
        "Export follows the name-only identity rule; code columns only when picked"]),
    node("N-0044", "D-c + rest of 2.7: desk absorbs BACKLOG-202 pieces, CporCaseWorkspace retires, two orphan panels ruled", ["N-0040", "N-0032"], ["ui"], "R2", [
        "FX anchor, settle readiness row, comparable cases and transition buttons are on the settlement desk (BACKLOG-202), then CporCaseWorkspace is deleted",
        "SettlementPortfolioRead and CporPortfolioIntelligencePanel: overlap with existing surfaces measured; mounted under Promotions & Funding per the lab if they show intelligence nothing else shows, deleted if they duplicate; ruling and reason reported",
        "Browser smoke on case 46 and 311"]),
    node("N-0045", "D-d: archive untracked files outside the repo; commit only real source", ["N-0044"], [], "R1", [
        "Every untracked path is classified; non-source files move to an archive folder outside the repo (never deleted); real source is committed and listed",
        "Control-plane paths are not moved by the agent; any that need moving go to Warren"]),
    node("N-0046", "BACKLOG-143: worktrees and leftover-state hygiene", ["N-0045"], [], "R1", [
        "Stale git worktrees and disposable leftover state in BACKLOG-143 are inventoried; removals are local and reversible or archived; nothing on cip"]),
    node("N-0047", "Stage 4.1: dim_product inverted launch/retire windows (BACKLOG-034), proven on a clone", ["N-0046"], ["data_migration"], "R2", [
        "Inverted windows counted on cip read-only; repair rule stated; repair run on a clone with printed before/after numbers",
        "cip apply prepared but not run; listed ready-for-cip for Warren"]),
    node("N-0048", "Stage 4.2: cpor_case status vs workflow_status drift (BACKLOG-139), proven on a clone", ["N-0047"], ["data_migration"], "R2", [
        "Owner column chosen with reasoning; drift rows measured on cip read-only; repair proven on a clone with before/after; cip apply listed for Warren"]),
    node("N-0049", "Stage 4.3: MAC check reads customer sell-through, not the empty inventory fact (BACKLOG-135)", ["N-0048"], ["api"], "R2", [
        "MAC check sources customer SOH from fact_customer_sellthrough and stops claiming fact_inventory_customer; proven on cip_test or a clone with printed numbers"]),
    node("N-0050", "Stage 4.4: cpor_case_line week-aligned window columns (BACKLOG-137), migration proven on cip_test only", ["N-0049"], ["schema", "data_migration"], "R2", [
        "Alembic migration written; upgrade and downgrade proven on cip_test with printed numbers; NOT applied to cip; listed ready-for-cip for Warren"]),
    node("N-0051", "Stage 3.7: import completion asserts no merged-id leftovers (BACKLOG-133/134)", ["N-0050"], ["api"], "R2", [
        "customer_leftover_repair's merged-id check runs on the import-complete rail; a leftover FLAGs (FLAG is not BLOCK unless Warren rules); proven on cip_test"]),
    node("N-0052", "Stage 3.6: ops safety net (restore proven on a clone, alerting, resolver fails loudly)", ["N-0051"], ["infra"], "R2", [
        "pg_dump backup restored into a clone with row-count parity printed; RTO/RPO measured and written to docs/BACKUP_AND_DR.md",
        "A Celery task failure raises an alert through a configured channel, proven by a forced local failure",
        "AI resolver fails loudly when AI_ASSIST_ENABLED is on and the client is missing"]),
    node("N-0053", "Stage 2.5: line identifier 'both' as two columns", ["N-0052", "N-0034"], ["ui"], "R2", [
        "LineIdentifierPreference gains 'both', rendered as two sortable and filterable columns through the N-0034 picker mechanism, not a second mechanism"]),
    node("N-0054", "Stage 2.9: design-lab as fixture skin over production primitives (BACKLOG-161/158)", ["N-0052"], ["ui"], "R2", [
        "design-lab/primitives and design-lab/shell import production components; duplicates removed; lab renders unchanged at 1280x800 (Warren 21 Sep: keep lab as fixture skin)"]),
    node("N-0055", "Stage 3.3: tenant scoping sweep", ["N-0054"], ["api"], "R2", [
        "Every endpoint module that reads tenant-owned rows filters by tenant_id; module list before and after; tests prove a second tenant cannot read the first"]),
    node("N-0056", "Stage 5: analytics delivery (export, event-triggered refresh, calendar delivery, vintage on face)", ["N-0055", "N-0052"], ["api", "ui"], "R2", [
        "Excel/PDF export; load completes then dependents refresh then subscribers are notified; calendar delivery; every report shows its vintage; delivery failures alert via N-0052"]),
    node("N-0057", "Stage 6.1/6.2: lineup authoring workbench and the B2 end-to-end PM run (BACKLOG-190)", ["N-0056", "N-0040"], ["ui", "api"], "R2", [
        "A PM authors next quarter's lineup in CIP beside unified import and exports tenant format; the journey is browser-proven on cip_test, not cip"]),
    node("N-0058", "Stage 6.3/6.5: unified lineup import 1H fan-out and lineup data rules (BACKLOG-103/105/055/065)", ["N-0057"], ["api"], "R2", [
        "Unified path fans 1H into Q1+Q2 like the bulk path; PF Qty vs Total Qty, BU resolver thresholds and monthly phasing each implemented per a recorded rule or sent to Warren as a decision"]),
    node("N-0059", "Stage 6.4: bulk-backfill completion UX (BACKLOG-060)", ["N-0058"], ["ui"], "R1", [
        "Bulk backfill Apply shows progress and a completion summary with next steps; no silent dialog close"]),
    node("N-0060", "Historical lineup backfill (years before 2025 Q1)", ["N-0058"], ["data_migration"], "R2", [
        "Warren supplies the historical lineup archive and authorises the cip load; load rehearsed on a clone with per-quarter case counts printed. cip holds 36 lineup cases, 2025 Q1 to 2026 Q3, today (measured 2026-09-24)"]),
    node("N-0061", "Stage 7.1-7.3: promotion intelligence v2 (listing/competitor evidence, observed cover, comparable scope)", ["N-0059"], ["ui", "api"], "R2", [
        "BACKLOG-183/184/186 with honest empties where data is absent (fact_competitor_price 0 rows)"]),
    node("N-0062", "Stage 7.5: supply Arrived state and plan-unit PO coverage (BACKLOG-178/179)", ["N-0061"], ["schema", "api"], "R2", [
        "Stored Arrived state and PO coverage by distributor; any migration proven on cip_test only"]),
    node("N-0063", "Stage 7.4: uplift from settled claims (BACKLOG-185), data-gated", ["N-0062"], ["api"], "R2", [
        "Buildable only once cpor_claim_evidence_line has rows (0 vs 211 settled cases, 2026-09-21); Warren's data drive unlocks it"]),
    node("N-0065", "BU entitlements: user-to-product-line mapping over the D-g lines", ["N-0055", "N-0040", "N-0038"], ["auth", "api"], "R2", [
        "A user may be mapped to any subset of dim_product.product_line values (D-g grain); enforcement semantics per Warren's decision (default for unmapped users, read vs write scope, which surfaces filter)"]),
    node("N-0066", "Naming and polish pass across containers, with outside buyers in mind", ["N-0062"], ["ui"], "R1", [
        "Every container's labels, empty states and microcopy reviewed against docs/design/NAMING.md hard rules and an outside-buyer read; changes listed"]),
    node("N-0067", "Light/dark theme completion", ["N-0066"], ["ui"], "R1", [
        "Every production surface renders correctly in both modes (cipTheme supports both; 16 hard-coded hex literals under features/ and app/ counted 2026-09-24); grids and charts included; browser-checked"]),
    node("N-0068", "Multi-catalogue column sets (BACKLOG-198)", ["N-0067"], ["api", "ui"], "R2", [
        "Blocked on Warren's catalog_product grain decision (BACKLOG-198)"]),
    node("N-0069", "Stage 8: steward and import engine follow-ons (trigger-gated umbrella)", ["N-0067"], ["api", "ui"], "R2", [
        "Each item in STAGED_WORK_PLAN Stage 8 is split into its own node when its trigger fires; this node records the list"]),
    node("N-0070", "Stage 10: multi-tenant productisation (P6)", ["N-0069", "N-0068", "N-0065"], ["api", "ui"], "R3", [
        "Tenant config surface, tenant-2 onboarding, branding, provisioning; catalog grain decided"], acc="operator"),
    node("N-0071", "Stage 4.6: open->shipped fact double-count policy (BACKLOG-062), undecided", ["N-0050"], ["data_migration"], "R2", [
        "Warren decides the remediation policy (D-e: not decided); nothing is built until then"]),
    node("N-0072", "Stage 4.7: ACZA workbook non-operational sheets allowlist (BACKLOG-046), undecided", ["N-0050"], ["api"], "R2", [
        "Warren decides the business rule (D-e: not decided); nothing is built until then"]),
]
for n in nodes:
    (out / f"{n['id']}.json").write_text(json.dumps(n, indent=1), encoding="utf-8")
print(len(decisions), "decisions,", len(nodes), "nodes")
