// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  CLIENT_ADDRESS_HEADERS,
  LOCAL_CLIENT_ADDRESS,
  buildUpstreamHeaders,
  parseIpLiteral,
  resolveClientAddress,
} from './proxyForwardedHeaders';

describe('parseIpLiteral', () => {
  it('accepts single IPv4 and IPv6 literals', () => {
    expect(parseIpLiteral('203.0.113.7')).toBe('203.0.113.7');
    expect(parseIpLiteral(' 2001:DB8::1 ')).toBe('2001:db8::1');
  });

  it.each([null, '', 'unknown', '1.2.3.4, 5.6.7.8', '1.2.3.4:80', '[2001:db8::1]', '999.1.1.1', 'a'.repeat(80)])(
    'rejects %s',
    (raw) => {
      expect(parseIpLiteral(raw as string | null)).toBeNull();
    },
  );
});

describe('resolveClientAddress', () => {
  it('uses CF-Connecting-IP (set by the Cloudflare edge) for tunnel traffic', () => {
    const h = new Headers({ 'cf-connecting-ip': '198.51.100.20', 'x-forwarded-for': '10.9.9.9' });
    expect(resolveClientAddress(h)).toBe('198.51.100.20');
  });

  it('keys a request without CF-Connecting-IP as local, whatever X-Forwarded-For says', () => {
    expect(resolveClientAddress(new Headers({ 'x-forwarded-for': '203.0.113.99' }))).toBe(LOCAL_CLIENT_ADDRESS);
    expect(resolveClientAddress(new Headers({ 'x-real-ip': '203.0.113.99' }))).toBe(LOCAL_CLIENT_ADDRESS);
    expect(resolveClientAddress(new Headers({ forwarded: 'for=203.0.113.99' }))).toBe(LOCAL_CLIENT_ADDRESS);
    expect(resolveClientAddress(new Headers())).toBe(LOCAL_CLIENT_ADDRESS);
  });

  it('ignores a malformed CF-Connecting-IP instead of forwarding it', () => {
    const h = new Headers({ 'cf-connecting-ip': '1.2.3.4, 5.6.7.8' });
    expect(resolveClientAddress(h)).toBe(LOCAL_CLIENT_ADDRESS);
  });
});

describe('buildUpstreamHeaders', () => {
  it('overwrites a spoofed X-Forwarded-For with the trusted address and drops other address headers', () => {
    const incoming = new Headers({
      'x-forwarded-for': '1.1.1.1, 2.2.2.2',
      'x-real-ip': '3.3.3.3',
      forwarded: 'for=4.4.4.4',
      'true-client-ip': '5.5.5.5',
      'x-client-ip': '6.6.6.6',
      'cf-connecting-ip': '198.51.100.20',
      authorization: 'Bearer test-token',
      'content-type': 'application/json',
      connection: 'keep-alive',
      host: 'example.trycloudflare.com',
    });
    const out = buildUpstreamHeaders(incoming);
    expect(out.get('x-forwarded-for')).toBe('198.51.100.20');
    expect(out.get('x-real-ip')).toBe('198.51.100.20');
    for (const name of CLIENT_ADDRESS_HEADERS) {
      if (name === 'x-forwarded-for' || name === 'x-real-ip') continue;
      expect(out.has(name)).toBe(false);
    }
    expect(out.get('authorization')).toBe('Bearer test-token');
    expect(out.get('content-type')).toBe('application/json');
    expect(out.has('connection')).toBe(false);
    expect(out.has('host')).toBe(false);
  });

  it('sends the local key when a local caller spoofs X-Forwarded-For', () => {
    const out = buildUpstreamHeaders(new Headers({ 'x-forwarded-for': '203.0.113.99' }));
    expect(out.get('x-forwarded-for')).toBe(LOCAL_CLIENT_ADDRESS);
    expect(out.get('x-real-ip')).toBe(LOCAL_CLIENT_ADDRESS);
  });
});

describe('proxy route handler', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('forwards the trusted address, not the visitor-supplied X-Forwarded-For', async () => {
    const seen: Headers[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init: RequestInit) => {
        seen.push(new Headers(init.headers));
        return new Response('{}', { status: 401, headers: { 'content-type': 'application/json' } });
      }),
    );
    const { NextRequest } = await import('next/server');
    const route = await import('@/app/api/v1/[[...path]]/route');
    const req = new NextRequest('http://127.0.0.1:3000/api/v1/auth/login', {
      method: 'POST',
      body: '{}',
      headers: {
        'content-type': 'application/json',
        'x-forwarded-for': '6.6.6.6',
        'x-real-ip': '6.6.6.6',
        'cf-connecting-ip': '198.51.100.20',
      },
    });
    const res = await route.POST(req, { params: Promise.resolve({ path: ['auth', 'login'] }) });
    expect(res.status).toBe(401);
    expect(seen).toHaveLength(1);
    expect(seen[0].get('x-forwarded-for')).toBe('198.51.100.20');
    expect(seen[0].get('x-real-ip')).toBe('198.51.100.20');
    expect(seen[0].has('cf-connecting-ip')).toBe(false);
  });
});
