import { NextRequest } from 'next/server';
import { describe, expect, it } from 'vitest';

import { config, middleware } from './middleware';

function request(path: string) {
  return new NextRequest(new URL(path, 'http://localhost:3000'));
}

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
