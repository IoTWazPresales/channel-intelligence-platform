/**
 * Wave 2 verification matrix: every Wave 1 route x viewport x state on an already-running app.
 *
 * Run only through playwright.wave2.config.ts (docs/audits/WAVE2_VERIFICATION_HARNESS.md).
 * Under any other config, or without CIP_VERIFY_BASE_URL and CIP_VERIFY_MODE, every case is skipped.
 *
 * Safety: a page.route('**\/*') guard is installed before every navigation, in both modes. It
 * aborts every request `isWriteRequest` marks as a write: anything but GET/HEAD/OPTIONS, and that
 * includes POST /api/v1/auth/login (login commits an AuthSession row). Only in full mode with
 * CIP_VERIFY_ALLOW_WRITES=1 do writes pass, and they are still recorded. The spec never submits a
 * form except the full-mode sign-in form on the test instance.
 *
 * Sessions: readonly mode never signs in. It consumes an existing session (CIP_VERIFY_STORAGE_STATE
 * or CIP_VERIFY_SESSION_TOKEN) and refuses to run without one. Full mode may log in as the
 * verification user, the only place the login request is let through (`allowLogin`).
 *
 * States: `empty`, `error` and `loading` are produced by GET interception only, in both modes, so
 * they never write; each state case also checks that the interception really hit a request.
 */
import fs from 'node:fs';
import path from 'node:path';
import { test as base, expect, type Page } from '@playwright/test';

import {
  AUTH_TOKEN_STORAGE_KEY,
  ERROR_MARKER,
  STATES,
  STATE_SELECTORS,
  VIEWPORTS,
  WAVE1_ROUTES,
  buildMatrix,
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
  skippedDynamicRoutes,
  type AlertSnapshot,
  type AuthPlan,
  type InterceptionCounts,
  type MatrixCase,
  type MatrixMode,
  type StateName,
} from '../src/lib/verification/matrix';

const WEB_ROOT = path.resolve(__dirname, '..');
const OUT_DIR = path.join(WEB_ROOT, '.tmp', 'wave2');
const SCREENS_DIR = path.join(OUT_DIR, 'screens');
const AUTH_DIR = path.join(OUT_DIR, 'auth');
const RESULTS_FILE = path.join(OUT_DIR, 'results.ndjson');
const FIGURES_FILE = path.join(OUT_DIR, 'figures.ndjson');

const EMPTY_ELEMENTS =
  '.ag-overlay-no-rows-wrapper, .ag-overlay-no-rows-center, .MuiDataGrid-overlay, .MuiTableBody-root .MuiTableRow-root:only-child .MuiTableCell-root[colspan]';

function envInt(name: string, fallback: number): number {
  const raw = process.env[name]?.trim();
  if (!raw) return fallback;
  const n = Number(raw);
  if (!Number.isInteger(n) || n <= 0) throw new Error(`${name} must be a positive integer (milliseconds); got ${raw}`);
  return n;
}

const configured = Boolean(process.env.CIP_VERIFY_BASE_URL?.trim() && process.env.CIP_VERIFY_MODE?.trim());
const mode: MatrixMode | null = configured ? parseMode(process.env.CIP_VERIFY_MODE?.trim()) : null;
const allowWrites = mode === 'full' && process.env.CIP_VERIFY_ALLOW_WRITES === '1';
const IDLE_TIMEOUT_MS = envInt('CIP_VERIFY_IDLE_TIMEOUT_MS', 20_000);
const LOADING_DELAY_MS = envInt('CIP_VERIFY_LOADING_DELAY_MS', 4_000);
const RUN_ID = process.env.CIP_VERIFY_RUN_ID?.trim() || 'unset';

// Throws with a clear message when readonly mode has no existing session: it never falls back to login.
const authPlan: AuthPlan | null = mode ? resolveAuth(mode, process.env) : null;
if (authPlan?.kind === 'storage-state' && !fs.existsSync(path.resolve(authPlan.file))) {
  throw new Error(`CIP_VERIFY_STORAGE_STATE points at a file that does not exist: ${authPlan.file}`);
}

const ids = idsFromEnv(process.env);
const cases: MatrixCase[] = mode ? buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, ids, discover: true }) : [];
const skipped = mode ? skippedDynamicRoutes(WAVE1_ROUTES, ids, { discover: true }) : [];

interface FigureCheck {
  name: string;
  route: string;
  selector?: string;
}

/** Optional page-figure capture (CIP_VERIFY_FIGURES=<checks JSON>): only checks that name a selector. */
function loadFigureChecks(): FigureCheck[] {
  const file = process.env.CIP_VERIFY_FIGURES?.trim();
  if (!file) return [];
  const parsed: unknown = JSON.parse(fs.readFileSync(path.resolve(file), 'utf8'));
  if (!Array.isArray(parsed)) throw new Error('CIP_VERIFY_FIGURES must point at a JSON array of checks.');
  return parsed.filter(
    (c): c is FigureCheck =>
      !!c && typeof c === 'object' && typeof c.name === 'string' && typeof c.route === 'string' && typeof c.selector === 'string',
  );
}
const figureChecks = mode ? loadFigureChecks() : [];

interface GuardLog {
  blockedWrites: string[];
  allowedWrites: string[];
  signIn: string[];
}

function newGuardLog(): GuardLog {
  return { blockedWrites: [], allowedWrites: [], signIn: [] };
}

function describeRequest(method: string, url: string): string {
  try {
    const u = new URL(url);
    return `${method} ${u.origin}${u.pathname}`;
  } catch {
    return `${method} ${url.slice(0, 200)}`;
  }
}

function relative(file: string): string {
  return path.relative(WEB_ROOT, file).split(path.sep).join('/');
}

interface GuardOptions {
  /** Let POST /api/v1/auth/login through. Only the full-mode sign-in step sets this. */
  allowLogin?: boolean;
  /** Counts of requests the state's interception really changed. */
  counts?: InterceptionCounts;
}

/** One handler for every request: the write guard first, then the state's GET /api/** rewrite. */
async function installGuard(page: Page, state: StateName, log: GuardLog, options: GuardOptions = {}): Promise<void> {
  const allowLogin = options.allowLogin === true && mode === 'full';
  const counts = options.counts ?? newInterceptionCounts();
  await page.route('**/*', async (route) => {
    const request = route.request();
    const method = request.method();
    const url = request.url();
    try {
      if (allowLogin && isLoginRequest(method, url)) {
        log.signIn.push(describeRequest(method, url));
        await route.continue();
        return;
      }
      if (isWriteRequest(method, url)) {
        if (allowWrites) {
          log.allowedWrites.push(describeRequest(method, url));
          await route.continue();
          return;
        }
        log.blockedWrites.push(describeRequest(method, url));
        await route.abort('blockedbyclient');
        return;
      }
      if (state !== 'loaded' && isInterceptableApiGet(method, url)) {
        if (state === 'error') {
          counts.error += 1;
          await route.fulfill({
            status: 500,
            contentType: 'application/json',
            body: JSON.stringify({ detail: ERROR_MARKER }),
          });
          return;
        }
        if (state === 'empty') {
          const response = await route.fetch();
          const type = response.headers()['content-type'] ?? '';
          if (response.ok() && type.includes('json')) {
            let body: unknown;
            try {
              body = JSON.parse(await response.text());
            } catch {
              await route.fulfill({ response });
              return;
            }
            counts.empty += 1;
            await route.fulfill({ response, json: emptyShape(body) });
            return;
          }
          await route.fulfill({ response });
          return;
        }
        if (state === 'loading') {
          counts.loading += 1;
          await new Promise((resolve) => setTimeout(resolve, LOADING_DELAY_MS));
          await route.continue();
          return;
        }
      }
      await route.continue();
    } catch (error) {
      // The page navigated away or closed while the request was held; nothing left to answer.
      if (!/closed|already handled|Target page/i.test(String(error))) throw error;
    }
  });
}

async function visibleTexts(page: Page, selector: string, limit = 3): Promise<string[]> {
  const loc = page.locator(selector);
  const out: string[] = [];
  const count = Math.min(await loc.count(), 20);
  for (let i = 0; i < count && out.length < limit; i += 1) {
    const item = loc.nth(i);
    if (await item.isVisible()) out.push((await item.innerText()).replace(/\s+/g, ' ').trim().slice(0, 200));
  }
  return out;
}

async function becomesVisible(page: Page, locator: ReturnType<Page['locator']>, timeout: number): Promise<boolean> {
  return locator
    .first()
    .waitFor({ state: 'visible', timeout })
    .then(
      () => true,
      () => false,
    );
}

const test = base.extend<{}, { workerStorageState: string }>({
  storageState: ({ workerStorageState }, provide) => provide(workerStorageState),
  workerStorageState: [
    async ({ browser }, provide, workerInfo) => {
      if (!authPlan) throw new Error('wave2 matrix is not configured');
      // Existing session: no browser, no request, no login. This is the only path readonly mode has.
      if (authPlan.kind === 'storage-state') {
        await provide(path.resolve(authPlan.file));
        return;
      }
      fs.mkdirSync(AUTH_DIR, { recursive: true });
      const file = path.join(AUTH_DIR, `worker-${workerInfo.parallelIndex}.json`);
      if (authPlan.kind === 'token') {
        const origin = new URL(String(workerInfo.project.use.baseURL)).origin;
        const state = { cookies: [], origins: [{ origin, localStorage: [{ name: AUTH_TOKEN_STORAGE_KEY, value: authPlan.token }] }] };
        fs.writeFileSync(file, JSON.stringify(state), 'utf8');
        await provide(file);
        return;
      }
      // authPlan.kind === 'login' is only ever produced for full mode (see resolveAuth).
      if (mode !== 'full') throw new Error('Refusing to submit the login form outside full mode.');
      const { email, password } = authPlan;
      const context = await browser.newContext({
        baseURL: workerInfo.project.use.baseURL,
        storageState: undefined,
        serviceWorkers: 'block',
      });
      const page = await context.newPage();
      const log = newGuardLog();
      await installGuard(page, 'loaded', log, { allowLogin: true });
      await page.goto('/login');
      await page.getByLabel(/email/i).fill(email);
      await page.getByLabel(/password/i).fill(password);
      await page.getByRole('button', { name: /sign in/i }).click();
      const signedIn = await page
        .waitForURL((u) => !u.pathname.startsWith('/login'), { timeout: 30_000 })
        .then(
          () => true,
          () => false,
        );
      if (!signedIn) {
        const shown = await visibleTexts(page, STATE_SELECTORS.anyAlert);
        await context.close();
        throw new Error(`Sign-in did not leave /login. ${shown.length ? `Page says: ${shown.join(' | ')}` : ''}`.trim());
      }
      if (log.blockedWrites.length) {
        console.warn(`[wave2] sign-in: the write guard blocked ${log.blockedWrites.join(', ')}`);
      }
      await context.storageState({ path: file });
      await context.close();
      await provide(file);
    },
    { scope: 'worker' },
  ],
});

async function captureFigures(page: Page, c: MatrixCase): Promise<void> {
  for (const check of figureChecks.filter((f) => f.route === c.route && f.selector)) {
    const loc = page.locator(check.selector!).first();
    const text = (await loc.isVisible()) ? (await loc.innerText()).trim() : null;
    const line = {
      runId: RUN_ID,
      name: check.name,
      route: c.route,
      caseId: c.id,
      viewport: c.viewport.name,
      selector: check.selector,
      text,
      value: text === null ? null : parseFigure(text),
    };
    fs.appendFileSync(FIGURES_FILE, `${JSON.stringify(line)}\n`, 'utf8');
  }
}

const discovered = new Map<string, Promise<string | null>>();

/**
 * Read-only lookup of a case id: open the planner list in a separate page of the same session (write
 * guard on, real responses) and take the first id from the list the app itself fetches. One lookup
 * per worker. Returns null when the list is empty or unreachable.
 */
function discoverCaseId(page: Page): Promise<string | null> {
  const key = 'cpor-case';
  const cached = discovered.get(key);
  if (cached) return cached;
  const lookup = (async () => {
    const probe = await page.context().newPage();
    try {
      await installGuard(probe, 'loaded', newGuardLog());
      const response = probe.waitForResponse(
        (r) => r.request().method() === 'GET' && new URL(r.url()).pathname.replace(/\/+$/, '') === '/api/v1/cpor/cases' && r.ok(),
        { timeout: IDLE_TIMEOUT_MS },
      );
      await probe.goto('/promotions', { waitUntil: 'domcontentloaded' });
      return firstCaseId(await (await response).json());
    } catch {
      return null;
    } finally {
      await probe.close();
    }
  })();
  discovered.set(key, lookup);
  return lookup;
}

/** Visible alert elements with their class (the MUI severity class tells an error from an introduction). */
async function visibleAlerts(page: Page): Promise<AlertSnapshot[]> {
  return page.locator(STATE_SELECTORS.anyAlert).evaluateAll((els) =>
    els
      .filter((e) => e.getClientRects().length > 0)
      .map((e) => ({ text: (e as HTMLElement).innerText ?? '', className: e.getAttribute('class') ?? '' })),
  );
}

async function waitForErrorIndication(page: Page, timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  let last = evaluateErrorIndication('', []);
  for (;;) {
    const body = await page.locator('body').innerText().catch(() => '');
    last = evaluateErrorIndication(body, await visibleAlerts(page).catch(() => []));
    if (last.ok || Date.now() >= deadline) return last;
    await page.waitForTimeout(500);
  }
}

async function runCase(page: Page, c: MatrixCase): Promise<Record<string, unknown>> {
  const log = newGuardLog();
  const counts = newInterceptionCounts();
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const problems: string[] = [];

  let url = c.url;
  if (c.needsDiscovery) {
    const id = await discoverCaseId(page);
    if (!id) {
      return {
        runId: RUN_ID,
        mode,
        id: c.id,
        route: c.route,
        url: c.url,
        viewport: c.viewport.name,
        state: c.state,
        status: 'skipped',
        problems: [],
        skipReason: `no id: set ${c.idEnv ?? 'the id env var'}, or the read-only lookup of GET /api/v1/cpor/cases found no case`,
        finishedAt: new Date().toISOString(),
      };
    }
    url = fillId(c.url, id);
  }

  page.on('console', (m) => {
    if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 500));
  });
  page.on('pageerror', (e) => pageErrors.push(e.message.slice(0, 500)));
  await installGuard(page, c.state, log, { counts });

  await page.goto(url, { waitUntil: 'domcontentloaded' });
  if (c.state === 'loading') {
    const seen = await becomesVisible(page, page.locator(STATE_SELECTORS.progress), Math.max(1_000, LOADING_DELAY_MS - 500));
    if (!seen) problems.push('loading: no progress bar, spinner or skeleton was visible before the delayed API responses');
  }
  let errorIndication: string | null = null;
  const networkIdle = await page.waitForLoadState('networkidle', { timeout: IDLE_TIMEOUT_MS }).then(
    () => true,
    () => false,
  );

  const finalPath = new URL(page.url()).pathname;
  if (finalPath.startsWith('/login')) problems.push('redirected to /login: the stored session is missing or expired');
  const bodyText = await page.locator('body').innerText().catch(() => '');
  if (STATE_SELECTORS.crashText.test(bodyText)) problems.push('the framework crash or not-found screen is shown');
  if (pageErrors.length) problems.push(`uncaught page error(s): ${pageErrors.slice(0, 3).join(' | ')}`);

  if (c.state === 'loaded' || c.state === 'loading') {
    const alerts = await visibleTexts(page, STATE_SELECTORS.errorAlert);
    if (alerts.length) problems.push(`error alert visible: ${alerts.join(' | ')}`);
  } else if (c.state === 'empty') {
    const empty = page.getByText(STATE_SELECTORS.emptyText).or(page.locator(EMPTY_ELEMENTS));
    if (!(await becomesVisible(page, empty, 10_000))) problems.push('empty: no empty-state text or element is visible');
  } else if (c.state === 'error') {
    // Error-specific only: an informational alert (role=alert) or the word "error" in page copy does not count.
    const indication = await waitForErrorIndication(page, 10_000);
    if (!indication.ok) problems.push(`error: ${indication.reason}`);
    else errorIndication = `${indication.via}: ${indication.evidence}`;
  }

  // The state only counts if its interception really hit a request (a pass on an untouched page proves nothing).
  const notIntercepted = interceptionProblem(c.state, counts);
  if (notIntercepted) problems.push(notIntercepted);

  // The view must really be the one the case names (a lens or workspace that mounts only for its query).
  if ((c.state === 'loaded' || c.state === 'loading') && c.mount) {
    const mounted = page.locator(`[data-testid="${c.mount}"]`);
    if (!(await becomesVisible(page, mounted, 10_000))) problems.push(`mount: [data-testid="${c.mount}"] is not visible, so this view did not render`);
  }

  // Anything the guard blocked was sent while the page rendered (the spec does not interact).
  if (log.blockedWrites.length && mode === 'full') {
    problems.push(`the write guard blocked ${log.blockedWrites.length} request(s) the page sent while rendering`);
  }

  if (c.state === 'loaded' && figureChecks.length) await captureFigures(page, c);

  fs.mkdirSync(SCREENS_DIR, { recursive: true });
  const screenshot = path.join(SCREENS_DIR, `${c.id}.png`);
  await page.screenshot({ path: screenshot, fullPage: true });

  return {
    runId: RUN_ID,
    mode,
    id: c.id,
    route: c.route,
    url,
    viewport: c.viewport.name,
    state: c.state,
    status: problems.length ? 'fail' : 'pass',
    problems,
    consoleErrors,
    pageErrors,
    blockedWrites: log.blockedWrites,
    allowedWrites: log.allowedWrites,
    intercepted: counts,
    errorIndication,
    networkIdle,
    screenshot: relative(screenshot),
    finishedAt: new Date().toISOString(),
  };
}

if (!mode) {
  test('wave2 matrix (not configured)', () => {
    test.skip(true, 'Run with playwright.wave2.config.ts, CIP_VERIFY_BASE_URL and CIP_VERIFY_MODE.');
  });
} else {
  // Not 'serial' in readonly: one failing case must not skip the rest. The config pins one worker there.
  test.describe.configure({ mode: mode === 'readonly' ? 'default' : 'parallel', retries: 0 });

  test.beforeAll(() => {
    fs.mkdirSync(OUT_DIR, { recursive: true });
    if (skipped.length) {
      console.warn(`[wave2] skipped dynamic views (no id env var, no read-only lookup): ${skipped.map((r) => `${r.path} <- ${r.idEnv}`).join(', ')}`);
    }
  });

  for (const viewport of VIEWPORTS) {
    test.describe(`${viewport.name} ${viewport.width}x${viewport.height}`, () => {
      test.use({ viewport: { width: viewport.width, height: viewport.height } });
      for (const c of cases.filter((x) => x.viewport.name === viewport.name)) {
        test(c.id, async ({ page }, testInfo) => {
          const result = await runCase(page, c);
          fs.mkdirSync(OUT_DIR, { recursive: true });
          fs.appendFileSync(RESULTS_FILE, `${JSON.stringify(result)}\n`, 'utf8');
          if (result.status === 'skipped') {
            // Recorded as `skipped` with its reason, never as a pass: the view is a gap in the evidence.
            testInfo.skip(true, String(result.skipReason));
            return;
          }
          await testInfo.attach('wave2-case.json', { body: JSON.stringify(result, null, 2), contentType: 'application/json' });
          await testInfo.attach('screenshot', { path: path.join(WEB_ROOT, String(result.screenshot)), contentType: 'image/png' });
          expect(result.problems, `${c.id}: ${(result.problems as string[]).join('; ')}`).toEqual([]);
        });
      }
    });
  }
}
