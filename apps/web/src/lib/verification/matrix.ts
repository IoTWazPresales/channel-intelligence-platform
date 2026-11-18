/**
 * Wave 2 verification matrix (CIP alignment Section D item 10).
 *
 * Pure data and helpers shared by the Playwright spec `e2e/wave2-matrix.spec.ts` and its vitest
 * suite. No Playwright import here: this module must load in vitest and in the browser-free
 * config. Nothing in this file names a customer, retailer, distributor, site or product: routes
 * are static path segments, concrete ids for `[id]` routes come only from env vars at run time.
 *
 * See docs/audits/WAVE2_VERIFICATION_HARNESS.md for how to run it.
 */

export type ViewportName = 'desktop' | 'mobile';

export interface Viewport {
  name: ViewportName;
  width: number;
  height: number;
}

/** Wave 2 step 3: "at 1280x800 and 390x844". */
export const VIEWPORTS: readonly Viewport[] = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 390, height: 844 },
];

export type StateName = 'loaded' | 'empty' | 'error' | 'loading';

export interface StateSpec {
  name: StateName;
  /** `real`: the page talks to the app's API as is. `intercept`: GET /api/** is rewritten in the browser. */
  produced: 'real' | 'intercept';
  /** How the state is produced and what the spec checks. None of them write to a database. */
  description: string;
}

export const STATES: readonly StateSpec[] = [
  {
    name: 'loaded',
    produced: 'real',
    description:
      'Real responses from the app under test. Check: no error alert is visible and the page raised no uncaught error.',
  },
  {
    name: 'empty',
    produced: 'intercept',
    description:
      'Every GET /api/** response is fetched, then every JSON array in it is replaced by [] (so [] and {"items":[]} shapes; ' +
      'count/total numbers become 0). Auth endpoints pass through. Check: an empty-state text or element is visible.',
  },
  {
    name: 'error',
    produced: 'intercept',
    description:
      'Every GET /api/** (auth endpoints excepted) is answered with HTTP 500 and a JSON {"detail": ...} carrying a fixed marker, ' +
      'without reaching the server. Check: at least one request was intercepted, and an error-specific indication is visible ' +
      '(the marker text, an error-severity alert, or error wording in a non-informational alert); an informational alert does not count. ' +
      'The page also must not crash (no uncaught error, no framework error screen).',
  },
  {
    name: 'loading',
    produced: 'intercept',
    description:
      'Every GET /api/** (auth endpoints excepted) is held for a delay before it continues to the real API. ' +
      'Check: a progress bar, spinner or skeleton is visible before the delayed responses arrive.',
  },
];

/** Where a run may look up an id read-only when its env var is not set. */
export type DiscoverKind = 'cpor-case';

export interface RouteEntry {
  /** In-app path under src/app/(app); `[id]` marks a dynamic segment. Static segments only. */
  path: string;
  /** Which wave item or doc line justifies including the route. */
  source: string;
  /** True when the view needs an id (`[id]` in the path, or `idQuery`); skipped unless an id is supplied or discovered. */
  dynamic: boolean;
  /** Env var that supplies the concrete id for a dynamic view. */
  idEnv?: string;
  /**
   * One static query parameter that selects the view inside the page, as `name=value` (for example a
   * lens tab). The page mounts a different component per value, so each value is its own view.
   */
  query?: string;
  /** Name of a query parameter that carries the id (for example `plan`); the view is `path?name=<id>`. */
  idQuery?: string;
  /** Read-only lookup of an id when `idEnv` is unset (see `firstCaseId`); the spec only does GETs. */
  discover?: DiscoverKind;
  /** `data-testid` of the component this view must mount; the `loaded` case fails if it is absent. */
  mount?: string;
}

const WAVES = 'docs/CIP_ORCHESTRATOR_WAVES.md';
const CURRENT = 'docs/memory/CURRENT.md';

/**
 * Routes Wave 1 touched, mapped to real pages under src/app/(app). Sources quote the wave item
 * (W1-A..W1-E in docs/CIP_ORCHESTRATOR_WAVES.md) or the CURRENT.md merge line. The mapping from a
 * wave item to a page follows the shell navigation (src/features/shell/navConfig.ts) and the page
 * component that renders the feature.
 */
export const WAVE1_ROUTES: readonly RouteEntry[] = [
  {
    path: '/stock/replenishment',
    source: `${WAVES} W1-A (N-0117 store and DC replenishment, store map, store location suggestions); ${CURRENT} #93 suggested store places as unconfirmed map pins`,
    dynamic: false,
  },
  {
    path: '/stock',
    source: `${WAVES} W1-A (N-0108 Cover speed folds in; slow and unsold stock)`,
    dynamic: false,
  },
  {
    path: '/promotions',
    source: `${WAVES} W1-A (slow/unsold stock suggested path, BACKLOG-227; aged-stock panel) and W1-C (N-0088 promotion planner suggested quantities); ${CURRENT} #92 line quantity suggestions, #96 stock-action price`,
    dynamic: false,
  },
  {
    // The quantity and export workspace mounts only for `?plan=<id>`; bare /promotions is the list.
    path: '/promotions',
    idQuery: 'plan',
    source: `${WAVES} W1-C (N-0088 plan quantity and export workspace, mounted only with ?plan=<id>); ${CURRENT} #92 line quantity suggestions, stored-layout export`,
    dynamic: true,
    idEnv: 'CIP_VERIFY_ID_PLAN',
    discover: 'cpor-case',
    mount: 'plan-workspace',
  },
  {
    path: '/commercial-planner/cpor-cases',
    source: `${WAVES} W1-A (BACKLOG-227 folds in); ${CURRENT} #86 Lane B CPOR aged-stock drafts and stock actions`,
    dynamic: false,
  },
  {
    path: '/commercial-planner/cpor-cases/[id]',
    source: `${WAVES} W1-E (N-0082 case link, N-0083 FX at approval); ${CURRENT} #86 stock actions on a case`,
    dynamic: true,
    idEnv: 'CIP_VERIFY_ID_CPOR_CASE',
    discover: 'cpor-case',
  },
  {
    path: '/commercial-planner/cpor-cases/historical-import',
    source: `${WAVES} W1-C (N-0088 plan export in the company's own template); ${CURRENT} #92 stored-layout export (Plan templates)`,
    dynamic: false,
  },
  {
    path: '/commercial-planner',
    source: `${WAVES} W1-E (N-0080 one profit definition; Plans & line economics)`,
    dynamic: false,
  },
  {
    path: '/listing-capture',
    source: `${WAVES} W1-B (N-0102 generic discovery and reader, N-0103 proposed listings, N-0076 promotion activation) and W1-D (Link discovery panel mounts only in Market & Listings); ${CURRENT} #91 site/domain for a reporting customer, #95 retail discovery`,
    dynamic: false,
  },
  // The bare page shows only the default lens; each lens below mounts only for its `?tab=` value
  // (marketLensFromLocation in features/market-listings/MarketChrome.tsx).
  {
    path: '/listing-capture',
    query: 'tab=sites',
    source: `${WAVES} W1-B (N-0102 sites and sellers: generic discovery and reader); ${CURRENT} #91 site/domain for a reporting customer`,
    dynamic: false,
    mount: 'listing-sites-lens',
  },
  {
    path: '/listing-capture',
    query: 'tab=links',
    source: `${WAVES} W1-D (Link discovery panel mounts only in Market & Listings); ${CURRENT} #95 retail discovery link queue`,
    dynamic: false,
    mount: 'listing-links-lens',
  },
  {
    path: '/listing-capture',
    query: 'tab=coverage',
    source: `${WAVES} W1-B (N-0102 listing coverage by customer); ${CURRENT} #95 retail discovery coverage`,
    dynamic: false,
    mount: 'listing-coverage-lens',
  },
  {
    path: '/listing-capture',
    query: 'tab=proposals',
    source: `${WAVES} W1-B (N-0103 proposed listings)`,
    dynamic: false,
    mount: 'market-proposals-lens',
  },
  {
    path: '/listing-capture',
    query: 'tab=intelligence',
    source: `${WAVES} W1-B (N-0076 promotion activation)`,
    dynamic: false,
    mount: 'market-activation-lens',
  },
  {
    path: '/competition',
    source: `${WAVES} W1-B (N-0077 competitor monitoring and price position)`,
    dynamic: false,
  },
  {
    path: '/brief',
    source: `${WAVES} W1-D (Link discovery panel must not render on other pages; Brief is the landing page) and W1-E (N-0114/N-0116 dashboards); ${CURRENT} #85 Lane D brief dashboards, My accounts`,
    dynamic: false,
  },
  {
    path: '/dashboards',
    source: `${WAVES} W1-E (N-0114, N-0115, N-0116 dashboards, with the BACKLOG-217 items)`,
    dynamic: false,
  },
  {
    path: '/channel-intelligence',
    source: `${WAVES} W1-E (N-0110 customer stock position; Sell-through)`,
    dynamic: false,
  },
  {
    path: '/admin/product-master-gaps',
    source: `${WAVES} W1-D (catalogue-gap scan rewritten as SQL, truth audit L1)`,
    dynamic: false,
  },
  {
    path: '/budgets',
    source: `${WAVES} W1-D (row security on budget_ledger_entry; Budget ledger)`,
    dynamic: false,
  },
  {
    // The Stock gap section mounts only for `?tab=stock-gap` (admin/cst-steward/page.tsx).
    path: '/admin/cst-steward',
    query: 'tab=stock-gap',
    source: `${WAVES} W1-E (N-0110 customer stock position: stock gap)`,
    dynamic: false,
    mount: 'cst-stock-gap',
  },
  {
    path: '/admin/imports',
    source: `${WAVES} W1-E (N-0111 sell-through upload by customer, N-0112 import job delete)`,
    dynamic: false,
  },
  {
    path: '/admin/customers/duplicates',
    source: `${WAVES} W1-E (N-0095 customer merge seals aliases)`,
    dynamic: false,
  },
  {
    path: '/admin/ops',
    source: `${WAVES} W1-E (N-0089 operations and data health, only what its charter scopes)`,
    dynamic: false,
  },
];

export type MatrixMode = 'readonly' | 'full';

export interface MatrixCase {
  /** Stable id, e.g. `brief@desktop#loaded`; dynamic views keep the template (`promotions~plan-id@...`). */
  id: string;
  /** View template from the manifest: path plus query, with `[id]` for an id (e.g. `/promotions?plan=[id]`). */
  route: string;
  /** Concrete URL to visit; still holds `[id]` while `needsDiscovery` is true. */
  url: string;
  viewport: Viewport;
  state: StateName;
  /** True when no id was supplied and the spec must look one up read-only before visiting. */
  needsDiscovery: boolean;
  discover?: DiscoverKind;
  /** Env var that would have supplied the id (named in the skip reason). */
  idEnv?: string;
  /** `data-testid` the view must mount in the `loaded` state. */
  mount?: string;
}

export interface BuildMatrixOptions {
  routes: readonly RouteEntry[];
  viewports: readonly Viewport[];
  states: readonly StateSpec[] | readonly StateName[];
  /** Concrete ids keyed by `RouteEntry.idEnv`, typically from `idsFromEnv(process.env)`. */
  ids?: Readonly<Record<string, string | undefined>>;
  /** Keep dynamic views that have a `discover` rule but no id; the spec resolves them at run time. */
  discover?: boolean;
}

/** A path made only of lower-case static segments, plus the literal `[id]` placeholder. */
export const STATIC_PATH = /^\/[a-z0-9-]+(?:\/(?:[a-z0-9-]+|\[id\]))*$/;
/** One static `name=value` query parameter (a lens or tab selector). */
export const STATIC_QUERY = /^[a-z][a-z0-9_]*=[a-z0-9-]+$/;
export const ID_QUERY_NAME = /^[a-z][a-z0-9_]*$/;
const CONCRETE_ID = /^[A-Za-z0-9_-]{1,64}$/;

export function parseMode(raw: string | undefined): MatrixMode {
  if (raw === 'readonly' || raw === 'full') return raw;
  throw new Error(
    `CIP_VERIFY_MODE must be "readonly" (live app) or "full" (test instance); got ${JSON.stringify(raw ?? null)}.`,
  );
}

/** `/stock/replenishment` -> `stock.replenishment`; `[id]` -> `id`. Safe as a file name. */
export function routeKey(path: string): string {
  if (!STATIC_PATH.test(path)) throw new Error(`Route is not a static in-app path: ${path}`);
  return path.slice(1).replace(/\[id\]/g, 'id').replace(/\//g, '.');
}

/** Query part of a view template: the static selector plus `idQuery=[id]`, in that order. */
function queryTemplate(entry: RouteEntry): string {
  const parts: string[] = [];
  if (entry.query) {
    if (!STATIC_QUERY.test(entry.query)) throw new Error(`Route query is not one static name=value: ${entry.query}`);
    parts.push(entry.query);
  }
  if (entry.idQuery) {
    if (!ID_QUERY_NAME.test(entry.idQuery)) throw new Error(`idQuery is not a plain parameter name: ${entry.idQuery}`);
    parts.push(`${entry.idQuery}=[id]`);
  }
  return parts.join('&');
}

/** Template of a view: `/listing-capture?tab=sites`, `/promotions?plan=[id]`, `/brief`. */
export function viewTemplate(entry: RouteEntry): string {
  routeKey(entry.path);
  const qs = queryTemplate(entry);
  return qs ? `${entry.path}?${qs}` : entry.path;
}

/** File-safe key of a view template: `/listing-capture?tab=sites` -> `listing-capture~tab-sites`. */
export function viewKey(template: string): string {
  const [path, qs, ...rest] = template.split('?');
  if (rest.length) throw new Error(`View template has more than one "?": ${template}`);
  const base = routeKey(path);
  if (qs === undefined) return base;
  if (!/^[a-z][a-z0-9_]*=(?:[a-z0-9-]+|\[id\])(?:&[a-z][a-z0-9_]*=(?:[a-z0-9-]+|\[id\]))*$/.test(qs)) {
    throw new Error(`View template has a non-static query: ${template}`);
  }
  return `${base}~${qs.replace(/\[id\]/g, 'id').replace(/[=&]/g, '-')}`;
}

export function caseId(template: string, viewport: ViewportName, state: StateName): string {
  return `${viewKey(template)}@${viewport}#${state}`;
}

function checkedId(entry: RouteEntry, raw: string): string {
  if (!CONCRETE_ID.test(raw)) {
    throw new Error(`${entry.idEnv ?? 'the id'} must be a plain id (letters, digits, "_" or "-"), got ${JSON.stringify(raw)}.`);
  }
  return encodeURIComponent(raw);
}

/** Put a concrete id into a view template (every `[id]`). Throws on a malformed id. */
export function fillId(template: string, id: string): string {
  return template.replace(/\[id\]/g, checkedId({ path: '', source: '', dynamic: true }, id.trim()));
}

/** Concrete URL for a view, or null for a dynamic view without an id. Throws on a malformed id. */
export function resolveRoutePath(
  entry: RouteEntry,
  ids: Readonly<Record<string, string | undefined>> = {},
): string | null {
  const template = viewTemplate(entry);
  if (!entry.dynamic) return template;
  const raw = entry.idEnv ? ids[entry.idEnv]?.trim() : undefined;
  if (!raw) return null;
  return template.replace(/\[id\]/g, checkedId(entry, raw));
}

/** Dynamic views the matrix leaves out because no id was supplied (and none is looked up at run time). */
export function skippedDynamicRoutes(
  routes: readonly RouteEntry[],
  ids: Readonly<Record<string, string | undefined>> = {},
  options: { discover?: boolean } = {},
): RouteEntry[] {
  return routes.filter((r) => r.dynamic && resolveRoutePath(r, ids) === null && !(options.discover && r.discover));
}

/**
 * First case id in a `GET /api/v1/cpor/cases` page (`{items: [{id}]}`), or null. Used to discover a
 * plan or case id read-only; ids that are not plain are ignored.
 */
export function firstCaseId(body: unknown): string | null {
  const items = body && typeof body === 'object' ? (body as { items?: unknown }).items : undefined;
  if (!Array.isArray(items)) return null;
  for (const item of items) {
    const id = item && typeof item === 'object' ? (item as { id?: unknown }).id : undefined;
    if (typeof id === 'number' && Number.isInteger(id) && id > 0) return String(id);
    if (typeof id === 'string' && CONCRETE_ID.test(id.trim())) return id.trim();
  }
  return null;
}

/** Collect the id env vars the manifest names from an env object (never hard-coded ids). */
export function idsFromEnv(
  env: Readonly<Record<string, string | undefined>>,
  routes: readonly RouteEntry[] = WAVE1_ROUTES,
): Record<string, string | undefined> {
  const out: Record<string, string | undefined> = {};
  for (const r of routes) if (r.idEnv) out[r.idEnv] = env[r.idEnv];
  return out;
}

/**
 * View x viewport x state, the same in both modes. The `empty`, `error` and `loading` states are
 * produced by request interception on GET only (no server write, no data change), so they run on the
 * live app as well as on the test instance.
 */
export function buildMatrix(options: BuildMatrixOptions): MatrixCase[] {
  const { routes, viewports, ids = {}, discover = false } = options;
  const states = (options.states as readonly (StateSpec | StateName)[]).map((s) =>
    typeof s === 'string' ? s : s.name,
  );
  const cases: MatrixCase[] = [];
  for (const route of routes) {
    const template = viewTemplate(route);
    let url = resolveRoutePath(route, ids);
    let needsDiscovery = false;
    if (url === null) {
      if (!(discover && route.discover)) continue;
      url = template;
      needsDiscovery = true;
    }
    for (const viewport of viewports) {
      for (const state of states) {
        cases.push({
          id: caseId(template, viewport.name, state),
          route: template,
          url,
          viewport,
          state,
          needsDiscovery,
          discover: route.discover,
          idEnv: route.idEnv,
          mount: route.mount,
        });
      }
    }
  }
  const seen = new Set<string>();
  for (const c of cases) {
    if (seen.has(c.id)) throw new Error(`Duplicate matrix case id: ${c.id}`);
    seen.add(c.id);
  }
  return cases;
}

export const LOGIN_API_PATH = '/api/v1/auth/login';
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

function pathnameOf(url: string): string {
  try {
    const p = new URL(url, 'http://verification.invalid').pathname;
    return p.length > 1 ? p.replace(/\/+$/, '') : p;
  } catch {
    return '';
  }
}

/** POST to the sign-in endpoint. It commits a session row, so it is a write like any other. */
export function isLoginRequest(method: string, url: string): boolean {
  return method.toUpperCase() === 'POST' && pathnameOf(url) === LOGIN_API_PATH;
}

/**
 * True for every method other than GET, HEAD and OPTIONS. POST /api/v1/auth/login is a write too
 * (it adds an AuthSession row); `allowLogin` exempts it and only the full-mode sign-in step sets it.
 */
export function isWriteRequest(method: string, url: string, options: { allowLogin?: boolean } = {}): boolean {
  if (SAFE_METHODS.has(method.toUpperCase())) return false;
  return !(options.allowLogin === true && isLoginRequest(method, url));
}

/** localStorage key the web app keeps its Bearer session token under (src/lib/authSession.ts). */
export const AUTH_TOKEN_STORAGE_KEY = 'cip.auth.token.v1';

export type AuthPlan =
  | { kind: 'storage-state'; file: string }
  | { kind: 'token'; token: string }
  | { kind: 'login'; email: string; password: string };

/**
 * How the run gets a signed-in session.
 * - readonly (live app): an existing session only, a Playwright storageState file
 *   (`CIP_VERIFY_STORAGE_STATE`) or a session token (`CIP_VERIFY_SESSION_TOKEN`). The login form is
 *   never submitted because login commits an AuthSession row. Without one, the run refuses.
 * - full (test instance): the same two, else the verification user's login (a write on the test
 *   instance only).
 */
export function resolveAuth(mode: MatrixMode, env: Readonly<Record<string, string | undefined>>): AuthPlan {
  const file = env.CIP_VERIFY_STORAGE_STATE?.trim();
  const token = env.CIP_VERIFY_SESSION_TOKEN?.trim();
  if (file && token) {
    throw new Error('Set only one of CIP_VERIFY_STORAGE_STATE and CIP_VERIFY_SESSION_TOKEN.');
  }
  if (file) return { kind: 'storage-state', file };
  if (token) return { kind: 'token', token };
  if (mode === 'readonly') {
    throw new Error(
      'Readonly mode never signs in (login writes an AuthSession row to the live database). ' +
        'Supply an existing session: CIP_VERIFY_STORAGE_STATE=<Playwright storageState file> or ' +
        'CIP_VERIFY_SESSION_TOKEN=<session token from an operator-issued session>.',
    );
  }
  const email = env.CIP_VERIFY_EMAIL;
  const password = env.CIP_VERIFY_PASSWORD;
  if (!email || !password) {
    throw new Error(
      'Full mode needs a session (CIP_VERIFY_STORAGE_STATE or CIP_VERIFY_SESSION_TOKEN) or a verification ' +
        'user (CIP_VERIFY_EMAIL and CIP_VERIFY_PASSWORD) to sign in on the test instance.',
    );
  }
  return { kind: 'login', email, password };
}

/** GET on the app API (`/api/**`), excluding auth endpoints: the requests the state intercepts rewrite. */
export function isInterceptableApiGet(method: string, url: string): boolean {
  if (method.toUpperCase() !== 'GET') return false;
  const p = pathnameOf(url);
  return p.startsWith('/api/') && !p.startsWith('/api/v1/auth/');
}

const COUNT_KEYS = new Set(['total', 'count', 'total_count', 'totalcount', 'row_count', 'rowcount']);

/** The `empty` state body: every array becomes [], count-like numbers become 0, other values stay. */
export function emptyShape(value: unknown): unknown {
  if (Array.isArray(value)) return [];
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = typeof v === 'number' && COUNT_KEYS.has(k.toLowerCase()) ? 0 : emptyShape(v);
    }
    return out;
  }
  return value;
}

/**
 * Read one figure from page text. The rule is fixed and matches figure_check.py: spaces,
 * non-breaking spaces and commas are thousands separators, "." is the decimal point, a leading
 * "-" or wrapping "( )" is negative; currency symbols, units and "%" are ignored (the number shown
 * is returned). Returns null when no number is present.
 */
export function parseFigure(text: string): number | null {
  const t = text.replace(/[\s  ,]/g, '');
  const m = t.match(/^(.*?)(\d+(?:\.\d+)?|\.\d+)(.*)$/);
  if (!m) return null;
  const n = Number(m[2]);
  if (!Number.isFinite(n)) return null;
  const negative = m[1].includes('-') || (m[1].includes('(') && m[3].startsWith(')'));
  return negative ? -n : n;
}

/** Selectors and text patterns the spec uses; generic, no test ids in app code. */
export const STATE_SELECTORS = {
  errorAlert: '.MuiAlert-standardError, .MuiAlert-filledError, .MuiAlert-outlinedError',
  anyAlert: '[role="alert"], .MuiAlert-root',
  progress:
    '[role="progressbar"], .MuiSkeleton-root, .MuiCircularProgress-root, .MuiLinearProgress-root, [aria-busy="true"]',
  emptyText: /no .*(data|results|rows|records|items|matches)|nothing|empty|none (yet|found)/i,
  errorText: /error|failed|could not|couldn't|unable|try again|went wrong/i,
  /** Next.js crash and not-found screens. Not "Internal Server Error": the error state shows that legitimately. */
  crashText: /Application error: a (client|server)-side exception|Unhandled Runtime Error|This page could not be found/i,
  /** MUI alerts whose severity is not error: they never count as an error indication. */
  nonErrorAlertClass: /MuiAlert-(?:standard|filled|outlined)(?:Info|Success|Warning)\b/,
  errorAlertClass: /MuiAlert-(?:standard|filled|outlined)Error\b/,
} as const;

/** Detail the `error` state returns for every intercepted GET; the app shows it when it surfaces the API error. */
export const ERROR_MARKER = 'Wave 2 verification: simulated server error';

/** Wording the app's API error helper produces for a failed request (src/lib/api.ts `readFetchError`). */
const FAILURE_WORDING =
  /request failed|server error|\(500\)|http 500|(?:could not|couldn't|unable to|failed to) (?:load|fetch|retrieve|read)|went wrong/i;

export interface AlertSnapshot {
  /** Visible text of the element. */
  text: string;
  /** Its `class` attribute (the MUI severity class is how an error alert differs from an informational one). */
  className: string;
}

export type ErrorIndication =
  | { ok: true; via: 'injected-detail' | 'error-alert' | 'alert-text' | 'status-text'; evidence: string }
  | { ok: false; reason: string };

function clip(s: string): string {
  return s.replace(/\s+/g, ' ').trim().slice(0, 160);
}

/**
 * Decide whether a page shows an error-specific indication for the `error` state. `bodyText` is the
 * page text, `alerts` every `[role=alert]` / `.MuiAlert-root` element. Not enough: any visible alert
 * (an informational introduction is an alert), or the word "error" somewhere in page copy.
 */
export function evaluateErrorIndication(bodyText: string, alerts: readonly AlertSnapshot[]): ErrorIndication {
  if (bodyText.toLowerCase().includes(ERROR_MARKER.toLowerCase())) {
    return { ok: true, via: 'injected-detail', evidence: ERROR_MARKER };
  }
  const errorAlert = alerts.find((a) => STATE_SELECTORS.errorAlertClass.test(a.className));
  if (errorAlert) return { ok: true, via: 'error-alert', evidence: clip(errorAlert.text) };
  const failureAlert = alerts.find(
    (a) => !STATE_SELECTORS.nonErrorAlertClass.test(a.className) && FAILURE_WORDING.test(a.text),
  );
  if (failureAlert) return { ok: true, via: 'alert-text', evidence: clip(failureAlert.text) };
  const status = bodyText.match(/(?:request failed|server error) \(500\)|http 500/i);
  if (status) return { ok: true, via: 'status-text', evidence: status[0] };
  const informational = alerts.filter((a) => !STATE_SELECTORS.errorAlertClass.test(a.className)).length;
  return {
    ok: false,
    reason: informational
      ? `${informational} alert(s) are visible but none is error-specific (informational alerts do not count)`
      : 'no error-specific indication is visible',
  };
}

/** What a state's interception actually did while the page loaded. */
export interface InterceptionCounts {
  /** GET /api/** answered with the injected 500. */
  error: number;
  /** GET /api/** whose JSON body was emptied. */
  empty: number;
  /** GET /api/** held for the delay. */
  loading: number;
}

export function newInterceptionCounts(): InterceptionCounts {
  return { error: 0, empty: 0, loading: 0 };
}

/**
 * A state case only counts when its injected condition really hit a request: otherwise the page was
 * never put in that state and a pass proves nothing. Returns a problem or null.
 */
export function interceptionProblem(state: StateName, counts: InterceptionCounts): string | null {
  if (state === 'loaded') return null;
  if (counts[state] > 0) return null;
  const what =
    state === 'error' ? 'answered with the injected 500' : state === 'empty' ? 'had its JSON body emptied' : 'was held';
  return `${state}: no GET /api/** request ${what}, so the page was never put in this state`;
}
