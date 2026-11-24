// @vitest-environment node

import { NextRequest } from 'next/server';
import { afterAll, afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import nextConfig from '../next.config';

import { config, middleware } from './middleware';

vi.hoisted(() => {
  // Next's server bootstrap exposes this before loading its request/adapter modules.
  vi.stubGlobal('AsyncLocalStorage', require('node:async_hooks').AsyncLocalStorage);
});
afterAll(() => vi.unstubAllGlobals());

function request(path: string) {
  return new NextRequest(new URL(path, 'http://localhost:3000'), { headers: { host: 'localhost:3000' } });
}

beforeEach(() => {
  // Next compiles this setting into the middleware runtime; mirror the configured value.
  vi.stubEnv('__NEXT_NO_MIDDLEWARE_URL_NORMALIZE', nextConfig.skipMiddlewareUrlNormalize ? '1' : undefined);
});
afterEach(() => vi.unstubAllEnvs());

describe('canonical navigation redirects', () => {
  it.each([
    ['/stock', '/inventory'],
    ['/stock?lens=cover', '/inventory'],
    ['/stock?lens=cover&product=42&status=low', '/inventory?product=42&status=low'],
    ['/stock?customer=7', '/inventory?customer=7'],
    ['/stock?tab=cover&product=42', '/inventory?product=42'],
    ['/stock?lens=COVER&distributor=7', '/inventory?distributor=7'],
    ['/stock/cover', '/inventory'],
    ['/stock/cover?product=42&distributor=7', '/inventory?product=42&distributor=7'],
    ['/stock/cover?lens=cover&tab=cover&status=breach', '/inventory?status=breach'],
    ['/stock/cover/?family=Notebook', '/inventory?family=Notebook'],
    ['/stock/cover/legacy?product=42', '/inventory?product=42'],
    ['/stock?lens=inbound&product=42', '/supply/shipments?product=42'],
    ['/sell-out?product=42', '/stock?product=42&lens=movement'],
    ['/plan-vs-executed', '/stock?lens=execution'],
    ['/shipping?product=42', '/supply/shipments?product=42'],
    ['/buy-plans?product=42', '/lineup/cases?product=42'],
    ['/dashboard?zone=attention', '/brief?zone=attention'],
    ['/exceptions', '/brief'],
    ['/getting-started', '/brief'],
    ['/', '/brief'],
  ])('redirects %s to %s', (source, target) => {
    const response = middleware(request(source));
    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe(new URL(target, 'http://localhost:3000').toString());
  });

  it.each([
    '/inventory',
    '/inventory?product=42',
    '/inventory/hand-entered',
    '/brief',
    '/dashboards?start=my_accounts',
    '/costs',
    '/pricing',
    '/stock?lens=movement',
    '/stock?lens=execution',
    '/stock/replenishment',
  ])('leaves canonical or unrelated route %s in place', (path) => {
    const response = middleware(request(path));
    expect(response.headers.get('location')).toBeNull();
    expect(response.headers.get('x-middleware-next')).toBe('1');
  });

  it('runs middleware for legacy cover paths in Next', () => {
    expect(config.matcher).toContain('/stock/cover/:path*');
  });
});

describe('legacy Inventory redirects through the installed Next adapter', () => {
  const origins = ['http://127.0.0.1:3107', 'http://localhost:3107', 'https://inventory.example.test:8443'];
  const paths = [
    '/stock?lens=cover&family=Notebook',
    '/stock/cover/?family=Notebook',
    '/stock?tab=cover&family=Notebook',
  ];

  it.each(origins.flatMap(origin => paths.map(path => [origin, path])))('keeps %s origin for %s', async (origin, path) => {
    const { adapter } = await import('next/dist/server/web/adapter');
    const input = new URL(path, origin);
    const { response, waitUntil } = await adapter({
      page: '/middleware',
      request: { url: input.toString(), method: 'GET', headers: { host: input.host }, signal: new AbortController().signal },
      handler: async req => middleware(req),
    });
    await waitUntil;
    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe(`${origin}/inventory?family=Notebook`);
  });

  it('keeps redirect-like filter values as query data', () => {
    const origin = 'http://127.0.0.1:3107';
    const input = new NextRequest(`${origin}/stock?lens=cover&next=https%3A%2F%2Fother.example%2F&product=42`, {
      headers: { host: '127.0.0.1:3107' },
    });
    const destination = new URL(middleware(input).headers.get('location')!);
    expect(destination.origin).toBe(origin);
    expect(destination.pathname).toBe('/inventory');
    expect(destination.searchParams.get('next')).toBe('https://other.example/');
    expect(destination.searchParams.get('product')).toBe('42');
    expect(destination.searchParams.has('lens')).toBe(false);
  });

  it.each(['http://localhost:3107', 'https://inventory.example.test:8443'])(
    'keeps incoming Host when Next binds its internal URL to loopback for %s',
    async origin => {
      const { adapter } = await import('next/dist/server/web/adapter');
      const incoming = new URL(origin);
      const { response, waitUntil } = await adapter({
        page: '/middleware',
        request: {
          url: `${incoming.protocol}//127.0.0.1:3107/stock?lens=cover&family=Notebook`,
          method: 'GET',
          headers: { host: incoming.host, 'x-forwarded-host': 'other.example' },
          signal: new AbortController().signal,
        },
        handler: async req => middleware(req),
      });
      await waitUntil;
      expect(response.headers.get('location')).toBe(`${origin}/inventory?family=Notebook`);
    },
  );

  it.each(
    ['http://localhost:3107', 'https://inventory.example.test:8443'].flatMap(origin => [
      ['/', '/brief'],
      ['/dashboard?zone=attention', '/brief?zone=attention'],
      ['/exceptions', '/brief'],
      ['/getting-started', '/brief'],
      ['/sell-out?product=42', '/stock?product=42&lens=movement'],
      ['/plan-vs-executed', '/stock?lens=execution'],
      ['/shipping?product=42', '/supply/shipments?product=42'],
      ['/buy-plans?product=42', '/lineup/cases?product=42'],
      ['/stock?lens=inbound&product=42', '/supply/shipments?product=42'],
    ].map(([path, target]) => [origin, path, target])),
  )('BACKLOG-266: keeps incoming Host on loopback-bound %s for %s', async (origin, path, target) => {
    const { adapter } = await import('next/dist/server/web/adapter');
    const incoming = new URL(origin);
    const { response, waitUntil } = await adapter({
      page: '/middleware',
      request: {
        url: `${incoming.protocol}//127.0.0.1:3107${path}`,
        method: 'GET',
        headers: { host: incoming.host, 'x-forwarded-host': 'other.example' },
        signal: new AbortController().signal,
      },
      handler: async req => middleware(req),
    });
    await waitUntil;
    expect(response.status).toBe(307);
    expect(response.headers.get('location')).toBe(origin + target);
  });

  it.each([
    ['/stock?lens=movement&family=Notebook', null],
    ['/stock?lens=execution', null],
    ['/inventory?family=Notebook', null],
    ['/stock?lens=inbound&product=42', '/supply/shipments?product=42'],
    ['/sell-out?product=42', '/stock?product=42&lens=movement'],
    ['/plan-vs-executed', '/stock?lens=execution'],
    ['/shipping?product=42', '/supply/shipments?product=42'],
    ['/buy-plans?product=42', '/lineup/cases?product=42'],
    ['/dashboard?zone=attention', '/brief?zone=attention'],
  ])('preserves the adapter behavior of %s', async (path, target) => {
    const { adapter } = await import('next/dist/server/web/adapter');
    const origin = 'http://localhost:3107';
    const { response, waitUntil } = await adapter({
      page: '/middleware',
      request: { url: origin + path, method: 'GET', headers: { host: 'localhost:3107' }, signal: new AbortController().signal },
      handler: async req => middleware(req),
    });
    await waitUntil;
    expect(response.headers.get('location')).toBe(target ? origin + target : null);
    expect(response.status).toBe(target ? 307 : 200);
    if (!target) expect(response.headers.get('x-middleware-next')).toBe('1');
  });
});
