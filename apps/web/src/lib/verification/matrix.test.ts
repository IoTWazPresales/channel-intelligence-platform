import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  STATES,
  STATIC_PATH,
  VIEWPORTS,
  WAVE1_ROUTES,
  buildMatrix,
  caseId,
  emptyShape,
  idsFromEnv,
  isInterceptableApiGet,
  isLoginRequest,
  isWriteRequest,
  parseFigure,
  parseMode,
  resolveRoutePath,
  routeKey,
  skippedDynamicRoutes,
  type RouteEntry,
} from './matrix';

const APP_GROUP = path.resolve(__dirname, '../../app/(app)');

const staticRoutes = WAVE1_ROUTES.filter((r) => !r.dynamic);
const dynamicRoutes = WAVE1_ROUTES.filter((r) => r.dynamic);

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
  it('full mode is static routes x viewports x states with stable ids', () => {
    const cases = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, mode: 'full' });
    expect(cases).toHaveLength(staticRoutes.length * VIEWPORTS.length * STATES.length);
    expect(new Set(cases.map((c) => c.id)).size).toBe(cases.length);
    const ids = cases.map((c) => c.id);
    expect(ids).toContain('brief@desktop#loaded');
    expect(ids).toContain('brief@mobile#loading');
    expect(ids).toContain('stock.replenishment@mobile#empty');
    expect(ids).toContain('admin.customers.duplicates@desktop#error');
    for (const c of cases) expect(c.id).toBe(caseId(c.route, c.viewport.name, c.state));
  });

  it('ids do not depend on order or on a concrete dynamic id', () => {
    const a = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, mode: 'full', ids: { CIP_VERIFY_ID_CPOR_CASE: '17' } });
    const b = buildMatrix({ routes: [...WAVE1_ROUTES].reverse(), viewports: VIEWPORTS, states: STATES, mode: 'full', ids: { CIP_VERIFY_ID_CPOR_CASE: '42' } });
    expect(new Set(a.map((c) => c.id))).toEqual(new Set(b.map((c) => c.id)));
    expect(a.map((c) => c.id)).toContain('commercial-planner.cpor-cases.id@desktop#loaded');
  });

  it('readonly mode only has loaded', () => {
    const cases = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, mode: 'readonly' });
    expect(cases.length).toBe(staticRoutes.length * VIEWPORTS.length);
    expect(new Set(cases.map((c) => c.state))).toEqual(new Set(['loaded']));
  });

  it('accepts state names as well as state specs', () => {
    const cases = buildMatrix({ routes: staticRoutes.slice(0, 1), viewports: VIEWPORTS, states: ['loaded', 'error'], mode: 'full' });
    expect(cases.map((c) => c.state)).toEqual(['loaded', 'error', 'loaded', 'error']);
  });

  it('skips dynamic routes without an id and includes them with one', () => {
    expect(dynamicRoutes.length).toBeGreaterThan(0);
    const without = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, mode: 'full' });
    expect(without.some((c) => c.route.includes('[id]'))).toBe(false);
    expect(skippedDynamicRoutes(WAVE1_ROUTES)).toEqual(dynamicRoutes);

    const ids = Object.fromEntries(dynamicRoutes.map((r) => [r.idEnv!, '123']));
    const withIds = buildMatrix({ routes: WAVE1_ROUTES, viewports: VIEWPORTS, states: STATES, mode: 'full', ids });
    expect(withIds).toHaveLength(WAVE1_ROUTES.length * VIEWPORTS.length * STATES.length);
    const dyn = withIds.filter((c) => c.route.includes('[id]'));
    expect(dyn.length).toBe(dynamicRoutes.length * VIEWPORTS.length * STATES.length);
    for (const c of dyn) expect(c.url).not.toContain('[id]');
    expect(skippedDynamicRoutes(WAVE1_ROUTES, ids)).toEqual([]);
  });

  it('a blank id counts as missing; a malformed id is refused', () => {
    const r = dynamicRoutes[0];
    expect(resolveRoutePath(r, { [r.idEnv!]: '   ' })).toBeNull();
    expect(resolveRoutePath(r, { [r.idEnv!]: 'abc-12_3' })).toBe(r.path.replace('[id]', 'abc-12_3'));
    expect(() => resolveRoutePath(r, { [r.idEnv!]: '../admin' })).toThrow(/plain id/);
    expect(() => resolveRoutePath(r, { [r.idEnv!]: '1?x=2' })).toThrow(/plain id/);
  });

  it('idsFromEnv reads only the env vars the manifest names', () => {
    const env = { CIP_VERIFY_ID_CPOR_CASE: '9', UNRELATED: 'x' };
    expect(idsFromEnv(env)).toEqual({ CIP_VERIFY_ID_CPOR_CASE: '9' });
  });

  it('parseMode refuses anything but readonly or full', () => {
    expect(parseMode('readonly')).toBe('readonly');
    expect(parseMode('full')).toBe('full');
    expect(() => parseMode(undefined)).toThrow(/CIP_VERIFY_MODE/);
    expect(() => parseMode('live')).toThrow(/CIP_VERIFY_MODE/);
  });
});

describe('WAVE1_ROUTES manifest', () => {
  it('every path exists as a page under src/app/(app)', () => {
    for (const r of WAVE1_ROUTES) {
      const file = path.join(APP_GROUP, ...r.path.slice(1).split('/'), 'page.tsx');
      expect(fs.existsSync(file), `${r.path} -> ${file}`).toBe(true);
    }
  });

  it('paths are unique and every entry names its source', () => {
    expect(new Set(WAVE1_ROUTES.map((r) => r.path)).size).toBe(WAVE1_ROUTES.length);
    for (const r of WAVE1_ROUTES) expect(r.source).toMatch(/W1-[A-E]|#\d+/);
  });

  it('dynamic flag matches [id] and dynamic routes name an id env var', () => {
    for (const r of WAVE1_ROUTES) {
      expect(r.dynamic).toBe(r.path.includes('[id]'));
      if (r.dynamic) expect(r.idEnv).toMatch(/^CIP_VERIFY_ID_[A-Z0-9_]+$/);
      else expect(r.idEnv).toBeUndefined();
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
    }
  });

  it('routeKey refuses a non-static path', () => {
    expect(routeKey('/stock/replenishment')).toBe('stock.replenishment');
    expect(() => routeKey('/supply/shipments/42?x=1')).toThrow();
    expect(() => routeKey('stock')).toThrow();
    const bad: RouteEntry = { path: '/Stock', source: 'W1-A', dynamic: false };
    expect(() => buildMatrix({ routes: [bad], viewports: VIEWPORTS, states: STATES, mode: 'full' })).toThrow();
  });
});

describe('isWriteRequest', () => {
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

  it('only POST /api/v1/auth/login is excepted', () => {
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/login')).toBe(false);
    expect(isWriteRequest('post', '/api/v1/auth/login/')).toBe(false);
    expect(isLoginRequest('POST', 'http://h/api/v1/auth/login?next=/brief')).toBe(true);
    expect(isWriteRequest('PUT', 'http://h/api/v1/auth/login')).toBe(true);
    expect(isWriteRequest('DELETE', 'http://h/api/v1/auth/login')).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/logout')).toBe(true);
    expect(isWriteRequest('POST', 'http://h/api/v1/auth/login/extra')).toBe(true);
    expect(isWriteRequest('POST', 'http://h/x/api/v1/auth/login')).toBe(true);
  });

  it('state intercepts touch GET /api/** but never auth endpoints', () => {
    expect(isInterceptableApiGet('GET', 'http://h/api/v1/brief')).toBe(true);
    expect(isInterceptableApiGet('GET', 'http://h/api/v1/auth/me')).toBe(false);
    expect(isInterceptableApiGet('POST', 'http://h/api/v1/brief')).toBe(false);
    expect(isInterceptableApiGet('GET', 'http://h/_next/static/chunk.js')).toBe(false);
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
    expect(parseFigure('US$ 574.59')).toBe(574.59);
    expect(parseFigure('-12')).toBe(-12);
    expect(parseFigure('(3.5)')).toBe(-3.5);
    expect(parseFigure('42%')).toBe(42);
    expect(parseFigure('—')).toBeNull();
    expect(parseFigure('')).toBeNull();
  });
});
