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
      'Every GET /api/** (auth endpoints excepted) is answered with HTTP 500 and a JSON {"detail": ...}. ' +
      'Check: a visible error message, and the page did not crash (no uncaught error, no framework error screen).',
  },
  {
    name: 'loading',
    produced: 'intercept',
    description:
      'Every GET /api/** (auth endpoints excepted) is held for a delay before it continues to the real API. ' +
      'Check: a progress bar, spinner or skeleton is visible before the delayed responses arrive.',
  },
];

export interface RouteEntry {
  /** In-app path under src/app/(app); `[id]` marks a dynamic segment. Static segments only. */
  path: string;
  /** Which wave item or doc line justifies including the route. */
  source: string;
  /** True for `[id]` routes; skipped unless `idEnv` supplies a concrete id. */
  dynamic: boolean;
  /** Env var that supplies the concrete id for a dynamic route. */
  idEnv?: string;
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
    path: '/commercial-planner/cpor-cases',
    source: `${WAVES} W1-A (BACKLOG-227 folds in); ${CURRENT} #86 Lane B CPOR aged-stock drafts and stock actions`,
    dynamic: false,
  },
  {
    path: '/commercial-planner/cpor-cases/[id]',
    source: `${WAVES} W1-E (N-0082 case link, N-0083 FX at approval); ${CURRENT} #86 stock actions on a case`,
    dynamic: true,
    idEnv: 'CIP_VERIFY_ID_CPOR_CASE',
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
  /** Stable id, e.g. `brief@desktop#loaded`; dynamic routes keep the template (`...cpor-cases.id`). */
  id: string;
  /** Template path from the manifest. */
  route: string;
  /** Concrete path to visit (template with its id filled in). */
  url: string;
  viewport: Viewport;
  state: StateName;
}

export interface BuildMatrixOptions {
  routes: readonly RouteEntry[];
  viewports: readonly Viewport[];
  states: readonly StateSpec[] | readonly StateName[];
  mode: MatrixMode;
  /** Concrete ids keyed by `RouteEntry.idEnv`, typically from `idsFromEnv(process.env)`. */
  ids?: Readonly<Record<string, string | undefined>>;
}

/** A path made only of lower-case static segments, plus the literal `[id]` placeholder. */
export const STATIC_PATH = /^\/[a-z0-9-]+(?:\/(?:[a-z0-9-]+|\[id\]))*$/;
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

export function caseId(path: string, viewport: ViewportName, state: StateName): string {
  return `${routeKey(path)}@${viewport}#${state}`;
}

/** Concrete path for a route, or null for a dynamic route without an id. Throws on a malformed id. */
export function resolveRoutePath(
  entry: RouteEntry,
  ids: Readonly<Record<string, string | undefined>> = {},
): string | null {
  if (!entry.dynamic) return entry.path;
  const raw = entry.idEnv ? ids[entry.idEnv]?.trim() : undefined;
  if (!raw) return null;
  if (!CONCRETE_ID.test(raw)) {
    throw new Error(`${entry.idEnv} must be a plain id (letters, digits, "_" or "-"), got ${JSON.stringify(raw)}.`);
  }
  return entry.path.replace('[id]', encodeURIComponent(raw));
}

/** Dynamic routes the matrix leaves out because no id was supplied. */
export function skippedDynamicRoutes(
  routes: readonly RouteEntry[],
  ids: Readonly<Record<string, string | undefined>> = {},
): RouteEntry[] {
  return routes.filter((r) => r.dynamic && resolveRoutePath(r, ids) === null);
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

/** Route x viewport x state. Readonly mode keeps only `loaded`: mocking the live app proves nothing. */
export function buildMatrix(options: BuildMatrixOptions): MatrixCase[] {
  const { routes, viewports, mode, ids = {} } = options;
  const stateNames = (options.states as readonly (StateSpec | StateName)[]).map((s) =>
    typeof s === 'string' ? s : s.name,
  );
  const states = mode === 'readonly' ? stateNames.filter((s) => s === 'loaded') : stateNames;
  const cases: MatrixCase[] = [];
  for (const route of routes) {
    const url = resolveRoutePath(route, ids);
    if (url === null) continue;
    for (const viewport of viewports) {
      for (const state of states) {
        cases.push({ id: caseId(route.path, viewport.name, state), route: route.path, url, viewport, state });
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

/** POST to the sign-in endpoint: the only non-safe request the harness lets through by default. */
export function isLoginRequest(method: string, url: string): boolean {
  return method.toUpperCase() === 'POST' && pathnameOf(url) === LOGIN_API_PATH;
}

/** True for every method other than GET, HEAD and OPTIONS, except POST /api/v1/auth/login. */
export function isWriteRequest(method: string, url: string): boolean {
  if (SAFE_METHODS.has(method.toUpperCase())) return false;
  return !isLoginRequest(method, url);
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
} as const;
