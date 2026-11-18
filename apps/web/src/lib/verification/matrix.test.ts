import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  AUTH_TOKEN_STORAGE_KEY,
  ERROR_MARKER,
  ID_QUERY_NAME,
  STATES,
  STATE_SELECTORS,
  STATIC_PATH,
  STATIC_QUERY,
  VIEWPORTS,
  WAVE1_ROUTES,
  buildMatrix,
  caseId,
  emptyShape,
  evaluateErrorIndication,
  fillId,
  firstCaseId,
  idsFromEnv,
  interceptionProblem,
  isInterceptableApiGet,
  isLoginRequest,
  isWriteRequest,
  newInterceptionCounts,
  parseFigure,
  parseMode,
  resolveAuth,
  resolveRoutePath,
  routeKey,
  skippedDynamicRoutes,
  viewKey,
  viewTemplate,
  type RouteEntry,
} from './matrix';

const SRC = path.resolve(__dirname, '../..');
const APP_GROUP = path.join(SRC, 'app', '(app)');
const SPEC_FILE = path.resolve(__dirname, '../../../e2e/wave2-matrix.spec.ts');

const staticRoutes = WAVE1_ROUTES.filter((r) => !r.dynamic);
const dynamicRoutes = WAVE1_ROUTES.filter((r) => r.dynamic);
const templates = WAVE1_ROUTES.map(viewTemplate);

function sourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) sourceFiles(full, out);
    else if (/\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) out.push(full);
  }
  return out;
}

describe('viewports and states', () => {
  it('has the two Wave 2 viewports', () => {
    expect(VIEWPORTS.map((v) => `${v.name}:${v.width}x${v.height}`)).toEqual(['desktop:1280x800', 'mobile:390x844']);
  });

  it('has the four states; only loaded uses real responses', () => {
    expect(STATES.map((s) => s.name)).toEqual(['loaded', 'empty', 'error', 'loading']);
    expect(STATES.filter((s) => s.produced === 'real').map((s) => s.name)).toEqual(['loaded']);
    for (const s of STATES) expect(s.description.length).toBeGreaterThan(20);
  });
});

describe('buildMatrix', () => {
  it('is static views x viewports x states with stable ids', () => {
    const cases = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES });
    expect(cases).toHaveLength(staticRoutes.length * VIEWPORTS.length * STATES.length);
    expect(new Set(cases.map((c) => c.id)).size).toBe(cases.length);
    const ids = cases.map((c) => c.id);
    expect(ids).toContain('brief@desktop#loaded');
    expect(ids).toContain('brief@mobile#loading');
    expect(ids).toContain('stock.replenishment@mobile#empty');
    expect(ids).toContain('admin.customers.duplicates@desktop#error');
    for (const c of cases) expect(c.id).toBe(caseId(c.route, c.viewport.name, c.state));
  });

  it('every state runs for every view: states are GET interception, so none needs a data change', () => {
    // Readonly runs used to keep only `loaded`; the other three are now produced by interception.
    const cases = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES });
    expect(new Set(cases.map((c) => c.state))).toEqual(new Set(['loaded', 'empty', 'error', 'loading']));
    for (const t of templates.filter((x) => !x.includes('[id]'))) {
      for (const state of ['loaded', 'empty', 'error', 'loading'] as const) {
        expect(cases.some((c) => c.route === t && c.state === state && c.viewport.name === 'mobile'), `${t} ${state}`).toBe(true);
      }
    }
  });

  it('ids do not depend on order or on a concrete dynamic id', () => {
    const a = buildMatrix({
      routes: WAVE1_ROUTES,
      viewports: VIEWPORTS,
      states: STATES,
      ids: { CIP_VERIFY_ID_CPOR_CASE: '17', CIP_VERIFY_ID_PLAN: '5' },
    });
    const b = buildMatrix({
      routes: [...WAVE1_ROUTES].reverse(),
      viewports: VIEWPORTS,
      states: STATES,
      ids: { CIP_VERIFY_ID_CPOR_CASE: '42', CIP_VERIFY_ID_PLAN: '6' },
    });
    expect(new Set(a.map((c) => c.id))).toEqual(new Set(b.map((c) => c.id)));
    expect(a.map((c) => c.id)).toContain('commercial-planner.cpor-cases.id@desktop#loaded');
    expect(a.map((c) => c.id)).toContain('promotions~plan-id@mobile#error');
  });

  it('accepts state names as well as state specs', () => {
    const cases = buildMatrix({ routes: staticRoutes.slice(0, 1), viewports: VIEWPORTS, states: ['loaded', 'error'] });
    expect(cases.map((c) => c.state)).toEqual(['loaded', 'error', 'loaded', 'error']);
  });

  it('leaves out dynamic views without an id, and keeps them for read-only discovery when asked', () => {
    expect(dynamicRoutes.length).toBeGreaterThan(0);
    const without = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES });
    expect(without.some((c) => c.route.includes('[id]'))).toBe(false);
    expect(skippedDynamicRoutes(WAVE1_ROUTES)).toEqual(dynamicRoutes);

    const ids = Object.fromEntries(dynamicRoutes.map((r) => [r.idEnv!, '123']));
    const withIds = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, ids });
    expect(withIds).toHaveLength(WAVE1_ROUTES.length * VIEWPORTS.length * STATES.length);
    const dyn = withIds.filter((c) => c.route.includes('[id]'));
    expect(dyn.length).toBe(dynamicRoutes.length * VIEWPORTS.length * STATES.length);
    for (const c of dyn) {
      expect(c.url).not.toContain('[id]');
      expect(c.needsDiscovery).toBe(false);
    }
    expect(skippedDynamicRoutes(WAVE1_ROUTES, ids)).toEqual([]);

    const discovering = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, discover: true });
    const pending = discovering.filter((c) => c.needsDiscovery);
    expect(pending.length).toBe(dynamicRoutes.length * VIEWPORTS.length * STATES.length);
    for (const c of pending) {
      expect(c.url).toContain('[id]');
      expect(c.discover).toBe('cpor-case');
    }
    expect(skippedDynamicRoutes(WAVE1_ROUTES, {}, { discover: true })).toEqual([]);
  });

  it('a blank id counts as missing; a malformed id is refused', () => {
    const r = dynamicRoutes.find((x) => x.path.includes('[id]'))!;
    expect(resolveRoutePath(r, { [r.idEnv!]: '   ' })).toBeNull();
    expect(resolveRoutePath(r, { [r.idEnv!]: 'abc-12_3' })).toBe(r.path.replace('[id]', 'abc-12_3'));
    expect(() => resolveRoutePath(r, { [r.idEnv!]: '../admin' })).toThrow(/plain id/);
    expect(() => resolveRoutePath(r, { [r.idEnv!]: '1?x=2' })).toThrow(/plain id/);
    expect(() => fillId('/promotions?plan=[id]', '1&tab=x')).toThrow(/plain id/);
  });

  it('idsFromEnv reads only the env vars the manifest names', () => {
    const env = { CIP_VERIFY_ID_CPOR_CASE: '9', CIP_VERIFY_ID_PLAN: '4', UNRELATED: 'x' };
    expect(idsFromEnv(env)).toEqual({ CIP_VERIFY_ID_CPOR_CASE: '9', CIP_VERIFY_ID_PLAN: '4' });
  });

  it('parseMode refuses anything but readonly or full', () => {
    expect(parseMode('readonly')).toBe('readonly');
    expect(parseMode('full')).toBe('full');
    expect(() => parseMode(undefined)).toThrow(/CIP_VERIFY_MODE/);
    expect(() => parseMode('live')).toThrow(/CIP_VERIFY_MODE/);
  });
});

describe('view templates, keys and ids', () => {
  it('builds the template and the concrete URL with the query', () => {
    const sites = WAVE1_ROUTES.find((r) => r.query === 'tab=sites')!;
    expect(viewTemplate(sites)).toBe('/listing-capture?tab=sites');
    expect(resolveRoutePath(sites)).toBe('/listing-capture?tab=sites');
    const plan = WAVE1_ROUTES.find((r) => r.idQuery === 'plan')!;
    expect(viewTemplate(plan)).toBe('/promotions?plan=[id]');
    expect(resolveRoutePath(plan)).toBeNull();
    expect(resolveRoutePath(plan, { CIP_VERIFY_ID_PLAN: '31' })).toBe('/promotions?plan=31');
    const both: RouteEntry = { path: '/brief', query: 'tab=x', idQuery: 'plan', source: 'W1-A', dynamic: true, idEnv: 'CIP_VERIFY_ID_X' };
    expect(viewTemplate(both)).toBe('/brief?tab=x&plan=[id]');
  });

  it('keys are file-safe and unique per view', () => {
    expect(viewKey('/brief')).toBe('brief');
    expect(viewKey('/listing-capture?tab=sites')).toBe('listing-capture~tab-sites');
    expect(viewKey('/promotions?plan=[id]')).toBe('promotions~plan-id');
    expect(viewKey('/commercial-planner/cpor-cases/[id]')).toBe('commercial-planner.cpor-cases.id');
    expect(caseId('/admin/cst-steward?tab=stock-gap', 'mobile', 'error')).toBe('admin.cst-steward~tab-stock-gap@mobile#error');
    for (const k of templates.map(viewKey)) expect(k).toMatch(/^[a-z0-9.~-]+$/);
    expect(new Set(templates).size).toBe(templates.length);
  });

  it('refuses a template with a non-static query', () => {
    expect(() => viewKey('/brief?a=1?b=2')).toThrow();
    expect(() => viewKey('/brief?tab=A B')).toThrow(/non-static/);
    expect(() => viewKey('/brief?tab=../x')).toThrow(/non-static/);
    const bad: RouteEntry = { path: '/brief', query: 'tab=sites&x=1', source: 'W1-A', dynamic: false };
    expect(() => viewTemplate(bad)).toThrow(/one static/);
  });

  it('fillId fills every placeholder with an encoded plain id', () => {
    expect(fillId('/promotions?plan=[id]', ' 12 ')).toBe('/promotions?plan=12');
    expect(fillId('/commercial-planner/cpor-cases/[id]', 'ab_c-1')).toBe('/commercial-planner/cpor-cases/ab_c-1');
  });

  it('firstCaseId reads the first plain id from a cases page', () => {
    expect(firstCaseId({ items: [{ id: 7 }, { id: 8 }] })).toBe('7');
    expect(firstCaseId({ items: [{ id: 'ab-1' }] })).toBe('ab-1');
    expect(firstCaseId({ items: [{ id: '../x' }, { id: 3 }] })).toBe('3');
    expect(firstCaseId({ items: [] })).toBeNull();
    expect(firstCaseId({ items: [{ name: 'no id' }] })).toBeNull();
    expect(firstCaseId({ items: [{ id: 0 }, { id: -2 }, { id: 1.5 }] })).toBeNull();
    expect(firstCaseId(null)).toBeNull();
    expect(firstCaseId('x')).toBeNull();
    expect(firstCaseId({})).toBeNull();
  });
});

describe('WAVE1_ROUTES manifest', () => {
  it('every path exists as a page under src/app/(app)', () => {
    for (const r of WAVE1_ROUTES) {
      const file = path.join(APP_GROUP, ...r.path.slice(1).split('/'), 'page.tsx');
      expect(fs.existsSync(file), `${r.path} -> ${file}`).toBe(true);
    }
  });

  it('views are unique and every entry names its source', () => {
    expect(new Set(templates).size).toBe(WAVE1_ROUTES.length);
    for (const r of WAVE1_ROUTES) expect(r.source).toMatch(/W1-[A-E]|#\d+/);
  });

  it('dynamic flag matches [id] or idQuery and dynamic views name an id env var', () => {
    for (const r of WAVE1_ROUTES) {
      expect(r.dynamic).toBe(r.path.includes('[id]') || Boolean(r.idQuery));
      if (r.dynamic) expect(r.idEnv).toMatch(/^CIP_VERIFY_ID_[A-Z0-9_]+$/);
      else expect(r.idEnv).toBeUndefined();
      if (r.discover) expect(r.dynamic).toBe(true);
    }
  });

  it('routes are static path segments only: nothing entity-specific', () => {
    for (const r of WAVE1_ROUTES) {
      expect(r.path).toMatch(STATIC_PATH);
      expect(r.path).not.toMatch(/[?#=&.:@%]/);
      for (const seg of r.path.slice(1).split('/')) {
        // No numeric ids, codes or uuids in a segment; `[id]` is the only placeholder.
        expect(seg).not.toMatch(/\d/);
        expect(seg.length).toBeLessThan(40);
      }
      if (r.query) {
        expect(r.query).toMatch(STATIC_QUERY);
        expect(r.query).not.toMatch(/\d/);
      }
      if (r.idQuery) expect(r.idQuery).toMatch(ID_QUERY_NAME);
    }
  });

  it('routeKey refuses a non-static path', () => {
    expect(routeKey('/stock/replenishment')).toBe('stock.replenishment');
    expect(() => routeKey('/supply/shipments/42?x=1')).toThrow();
    expect(() => routeKey('stock')).toThrow();
    const bad: RouteEntry = { path: '/Stock', source: 'W1-A', dynamic: false };
    expect(() => buildMatrix({ routes: [bad], viewports: VIEWPORTS, states: STATES })).toThrow();
  });
});

/**
 * Wave 1 views that mount only for a query parameter. A bare page never shows them, so a matrix
 * that only visits bare paths silently skips the work (Codex review of PR #113, finding 2).
 */
describe('Wave 1 views behind a query parameter are in the matrix', () => {
  const REQUIRED = [
    '/promotions?plan=[id]',
    '/listing-capture?tab=sites',
    '/listing-capture?tab=links',
    '/listing-capture?tab=coverage',
    '/admin/cst-steward?tab=stock-gap',
  ];

  it('lists the required views, and the bare pages stay too', () => {
    for (const t of REQUIRED) expect(templates, t).toContain(t);
    expect(templates).toContain('/promotions');
    expect(templates).toContain('/listing-capture');
  });

  it('the plan workspace view can find its id: env var, or read-only discovery', () => {
    const plan = WAVE1_ROUTES.find((r) => viewTemplate(r) === '/promotions?plan=[id]')!;
    expect(plan.idEnv).toBe('CIP_VERIFY_ID_PLAN');
    expect(plan.discover).toBe('cpor-case');
    expect(plan.mount).toBe('plan-workspace');
  });

  it('each view is selected by a value the app actually reads', () => {
    const read = (rel: string) => fs.readFileSync(path.join(SRC, rel), 'utf8');
    const chrome = read('features/market-listings/MarketChrome.tsx');
    const surface = read('features/market-listings/MarketSurface.tsx');
    for (const r of WAVE1_ROUTES.filter((x) => x.path === '/listing-capture' && x.query)) {
      const tab = r.query!.split('=')[1];
      expect(chrome, `MarketChrome tab ${tab}`).toContain(`tab === '${tab}'`);
    }
    expect(surface).toContain("lens === 'sites'");
    expect(surface).toContain("lens === 'links'");
    expect(surface).toContain("lens === 'coverage'");
    expect(read('app/(app)/admin/cst-steward/page.tsx')).toContain("requested === 'stock-gap'");
    expect(read('features/promotions-funding/PromotionPlannerSurface.tsx')).toContain("search.get('plan')");
  });

  it('every view that names a mount test id points at a test id in the app', () => {
    const files = [...sourceFiles(path.join(SRC, 'features')), ...sourceFiles(path.join(SRC, 'app'))];
    const text = files.map((f) => fs.readFileSync(f, 'utf8')).join('\n');
    const withMount = WAVE1_ROUTES.filter((r) => r.mount);
    expect(withMount.length).toBeGreaterThanOrEqual(WAVE1_ROUTES.filter((r) => r.query || r.idQuery).length);
    for (const r of withMount) expect(text, `${viewTemplate(r)} -> ${r.mount}`).toContain(`data-testid="${r.mount}"`);
  });
});

describe('isWriteRequest and the login write', () => {
  it('safe methods are never writes', () => {
    for (const m of ['GET', 'HEAD', 'OPTIONS', 'get', 'head', 'options']) {
      expect(isWriteRequest(m, 'http://h/api/v1/anything')).toBe(false);
    }
  });

  it('every other method is a write', () => {
    for (const m of ['POST', 'PUT', 'PATCH', 'DELETE', 'CONNECT', 'TRACE', 'PROPFIND']) {
      expect(isWriteRequest(m, 'http://h/api/v1/cpor/cases/1')).toBe(true);
    }
    expect(isWriteRequest('POST', '/api/v1/query/v2/execute')).toBe(true);
    expect(isWriteRequest('POST', 'http://h/_next/data')).toBe(true);
  });

  it('login is a write by default: it commits an AuthSession row', () => {
    expect(isLoginRequest('POST', 'http://h/api/v1/auth/login?next=/brief')).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/login')).toBe(true);
    expect(isWriteRequest('post', '/api/v1/auth/login/')).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/login', { allowLogin: false })).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/login', {})).toBe(true);
  });

  it('only an explicit allowLogin exempts POST /api/v1/auth/login, and nothing else', () => {
    const allow = { allowLogin: true };
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/login', allow)).toBe(false);
    expect(isWriteRequest('post', '/api/v1/auth/login/', allow)).toBe(false);
    expect(isWriteRequest('PUT', 'http://h/api/v1/auth/login', allow)).toBe(true);
    expect(isWriteRequest('DELETE', 'http://h/api/v1/auth/login', allow)).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/logout', allow)).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/login/extra', allow)).toBe(true);
    expect(isWriteRequest('POST', 'http://h/x/api/v1/auth/login', allow)).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/cpor/cases', allow)).toBe(true);
  });

  it('the spec lets login through only behind allowLogin (full mode), never unconditionally', () => {
    const spec = fs.readFileSync(SPEC_FILE, 'utf8');
    expect(spec).toMatch(/allowLogin\s*=\s*options\.allowLogin === true && mode === 'full'/);
    expect(spec).toContain('allowLogin && isLoginRequest(method, url)');
    expect(spec).not.toMatch(/if \(isLoginRequest\(/);
    // The page cases never ask for it; only the full-mode sign-in step does.
    expect(spec.match(/allowLogin: true/g)).toHaveLength(1);
    expect(spec).toContain("Refusing to submit the login form outside full mode.");
  });

  it('state intercepts touch GET /api/** but never auth endpoints', () => {
    expect(isInterceptableApiGet('GET', 'http://h/api/v1/brief')).toBe(true);
    expect(isInterceptableApiGet('GET', 'http://h/api/v1/auth/me')).toBe(false);
    expect(isInterceptableApiGet('POST', 'http://h/api/v1/brief')).toBe(false);
    expect(isInterceptableApiGet('GET', 'http://h/_next/static/chunk.js')).toBe(false);
  });
});

describe('resolveAuth: readonly never signs in', () => {
  const login = { CIP_VERIFY_EMAIL: 'verifier@example.invalid', CIP_VERIFY_PASSWORD: 'x' };

  it('readonly with no existing session refuses with a clear message, even when credentials are set', () => {
    expect(() => resolveAuth('readonly', {})).toThrow(/never signs in/);
    expect(() => resolveAuth('readonly', {})).toThrow(/CIP_VERIFY_STORAGE_STATE/);
    expect(() => resolveAuth('readonly', {})).toThrow(/CIP_VERIFY_SESSION_TOKEN/);
    expect(() => resolveAuth('readonly', login)).toThrow(/never signs in/);
    expect(() => resolveAuth('readonly', { CIP_VERIFY_STORAGE_STATE: '   ', CIP_VERIFY_SESSION_TOKEN: '' })).toThrow(/never signs in/);
  });

  it('readonly consumes a storageState file or a token, and ignores credentials', () => {
    expect(resolveAuth('readonly', { CIP_VERIFY_STORAGE_STATE: ' auth.json ', ...login })).toEqual({ kind: 'storage-state', file: 'auth.json' });
    expect(resolveAuth('readonly', { CIP_VERIFY_SESSION_TOKEN: ' tok ', ...login })).toEqual({ kind: 'token', token: 'tok' });
  });

  it('refuses two sessions at once', () => {
    expect(() => resolveAuth('readonly', { CIP_VERIFY_STORAGE_STATE: 'a.json', CIP_VERIFY_SESSION_TOKEN: 't' })).toThrow(/only one/);
  });

  it('full mode prefers an existing session, else logs in as the verification user', () => {
    expect(resolveAuth('full', { CIP_VERIFY_SESSION_TOKEN: 't', ...login })).toEqual({ kind: 'token', token: 't' });
    expect(resolveAuth('full', login)).toEqual({ kind: 'login', email: login.CIP_VERIFY_EMAIL, password: 'x' });
    expect(() => resolveAuth('full', {})).toThrow(/verification user/);
    expect(() => resolveAuth('full', { CIP_VERIFY_EMAIL: 'a@example.invalid' })).toThrow(/CIP_VERIFY_PASSWORD/);
  });

  it('the stored token key is the one the app reads', () => {
    const app = fs.readFileSync(path.join(SRC, 'lib', 'authSession.ts'), 'utf8');
    expect(app).toContain(`const TOKEN_KEY = '${AUTH_TOKEN_STORAGE_KEY}'`);
  });
});

describe('evaluateErrorIndication: error-specific only', () => {
  const info = { text: 'This page imports historical cases. Upload a file to begin.', className: 'MuiAlert-root MuiAlert-standardInfo' };

  it('an informational alert does not satisfy the error state (the historical-import false pass)', () => {
    const r = evaluateErrorIndication('Historical import\nThis page imports historical cases.', [info]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toMatch(/informational/);
  });

  it('an informational alert does not count even when its copy has failure wording', () => {
    const noisy = { text: 'If the import failed, request failed (500) rows are listed below.', className: 'MuiAlert-root MuiAlert-outlinedWarning' };
    expect(evaluateErrorIndication('', [noisy, info]).ok).toBe(false);
  });

  it('no alert and no error text fails', () => {
    const r = evaluateErrorIndication('Plans\nNo plans yet', []);
    expect(r).toEqual({ ok: false, reason: 'no error-specific indication is visible' });
  });

  it('plain page copy with the word "error" is not an indication', () => {
    expect(evaluateErrorIndication('Error budget and error rate trends', []).ok).toBe(false);
  });

  it('the injected detail shown on the page counts', () => {
    const r = evaluateErrorIndication(`Could not load\n${ERROR_MARKER}`, []);
    expect(r).toMatchObject({ ok: true, via: 'injected-detail' });
    expect(evaluateErrorIndication(ERROR_MARKER.toUpperCase(), []).ok).toBe(true);
  });

  it('an error-severity alert counts', () => {
    for (const cls of ['MuiAlert-standardError', 'MuiAlert-filledError', 'MuiAlert-outlinedError']) {
      const r = evaluateErrorIndication('', [info, { text: 'Something', className: `MuiAlert-root ${cls}` }]);
      expect(r, cls).toMatchObject({ ok: true, via: 'error-alert' });
    }
  });

  it('a role=alert element without a severity class counts only with failure wording', () => {
    expect(evaluateErrorIndication('', [{ text: 'Request failed (500)', className: '' }])).toMatchObject({ ok: true, via: 'alert-text' });
    expect(evaluateErrorIndication('', [{ text: 'Could not load plans', className: 'banner' }])).toMatchObject({ ok: true, via: 'alert-text' });
    expect(evaluateErrorIndication('', [{ text: 'Welcome back', className: 'banner' }]).ok).toBe(false);
  });

  it('the API error status in the page text counts', () => {
    expect(evaluateErrorIndication('Request failed (500)', [])).toMatchObject({ ok: true, via: 'status-text' });
    expect(evaluateErrorIndication('Server error (500)', [])).toMatchObject({ ok: true, via: 'status-text' });
  });

  it('severity classes are recognised', () => {
    expect(STATE_SELECTORS.errorAlertClass.test('MuiAlert-root MuiAlert-standardError')).toBe(true);
    expect(STATE_SELECTORS.nonErrorAlertClass.test('MuiAlert-root MuiAlert-standardInfo')).toBe(true);
    expect(STATE_SELECTORS.nonErrorAlertClass.test('MuiAlert-root MuiAlert-standardError')).toBe(false);
  });
});

describe('interceptionProblem: a state case needs its interception to have fired', () => {
  it('loaded needs no interception', () => {
    expect(interceptionProblem('loaded', newInterceptionCounts())).toBeNull();
  });

  it('error, empty and loading fail when nothing was intercepted', () => {
    const none = newInterceptionCounts();
    expect(interceptionProblem('error', none)).toMatch(/error: no GET .* injected 500/);
    expect(interceptionProblem('empty', none)).toMatch(/empty: no GET .* emptied/);
    expect(interceptionProblem('loading', none)).toMatch(/loading: no GET .* held/);
  });

  it('only the matching counter counts', () => {
    expect(interceptionProblem('error', { error: 0, empty: 5, loading: 5 })).not.toBeNull();
    expect(interceptionProblem('error', { error: 1, empty: 0, loading: 0 })).toBeNull();
    expect(interceptionProblem('empty', { error: 3, empty: 2, loading: 0 })).toBeNull();
    expect(interceptionProblem('loading', { error: 0, empty: 0, loading: 1 })).toBeNull();
  });
});

describe('emptyShape and parseFigure', () => {
  it('empties arrays at any depth and zeroes counts', () => {
    expect(emptyShape([1, 2])).toEqual([]);
    expect(emptyShape({ items: [{ a: 1 }], total: 5, page: 2, meta: { rows: [1], count: 3 } })).toEqual({
      items: [],
      total: 0,
      page: 2,
      meta: { rows: [], count: 0 },
    });
    expect(emptyShape(null)).toBeNull();
    expect(emptyShape('x')).toBe('x');
  });

  it('parses figures shown on a page', () => {
    expect(parseFigure('1,234.5')).toBe(1234.5);
    expect(parseFigure('R 1 234 567')).toBe(1234567);
    expect(parseFigure('US$ 574.59')).toBe(574.59);
    expect(parseFigure('-12')).toBe(-12);
    expect(parseFigure('(3.5)')).toBe(-3.5);
    expect(parseFigure('42%')).toBe(42);
    expect(parseFigure('—')).toBeNull();
    expect(parseFigure('')).toBeNull();
  });
});
