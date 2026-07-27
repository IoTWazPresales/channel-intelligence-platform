import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

/**
 * Same-origin reverse proxy: browser calls `/api/v1/...` on the Next host, this route forwards to FastAPI.
 *
 * - Local `next dev` / tests (`NODE_ENV` not `production`): enabled by default.
 * - `next start` sets `NODE_ENV=production`; proxy stays on when the resolved upstream host is loopback
 *   (typical local `pnpm --filter web start` + API on :8001). Disable with `CIP_DISABLE_NEXT_API_PROXY=true`.
 * - Non-loopback production (e.g. internal service URL): set `CIP_ENABLE_NEXT_API_PROXY=true` to opt in.
 * - Opt out anywhere: `CIP_DISABLE_NEXT_API_PROXY=true`.
 */
const HOP_BY_HOP = new Set([
  'connection',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailers',
  'transfer-encoding',
  'upgrade',
  'host',
]);

/** Resolved origin (no trailing slash) used for both allow-gate and upstream fetch. */
function resolvedApiUpstreamOrigin(): string {
  // Non-production: deterministic local default unless explicitly overridden.
  if (process.env.NODE_ENV !== 'production') {
    return (process.env.CIP_API_INTERNAL_URL || 'http://127.0.0.1:8001').replace(/\/$/, '');
  }
  return (
    process.env.CIP_API_INTERNAL_URL ||
    process.env.CIP_API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://127.0.0.1:8001'
  ).replace(/\/$/, '');
}

function isLocalLoopbackApiUpstream(origin: string): boolean {
  try {
    const { hostname } = new URL(origin);
    const h = hostname.toLowerCase();
    return h === 'localhost' || h === '127.0.0.1' || h === '[::1]' || h === '::1';
  } catch {
    return false;
  }
}

function allowSameOriginApiProxy(): boolean {
  const off = process.env.CIP_DISABLE_NEXT_API_PROXY;
  if (off === '1' || off === 'true') return false;
  const on = process.env.CIP_ENABLE_NEXT_API_PROXY;
  if (on === '1' || on === 'true') return true;
  if (process.env.NODE_ENV !== 'production') return true;
  // `next start` uses NODE_ENV=production; still proxy when upstream is loopback (local prod-style run).
  return isLocalLoopbackApiUpstream(resolvedApiUpstreamOrigin());
}

function upstreamOrigin(): string {
  return resolvedApiUpstreamOrigin();
}

/** Long-running import apply/validate/commit/batch can exceed undici defaults (~300s headers). */
const LONG_PROXY_TIMEOUT_MS = 600_000;

function proxyFetchInitNeedsLongTimeout(method: string, pathSuffix: string): boolean {
  if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return false;
  const p = pathSuffix.toLowerCase();
  return (
    p.includes('/validate') ||
    p.includes('/commit') ||
    p.endsWith('/apply') ||
    p.includes('/apply/') ||
    p.includes('/dsi/batch-propose') ||
    p.includes('/dsi/batch-jobs')
  );
}

/** Undici's headersTimeout is independent of AbortSignal — raise both for long routes. */
function longProxyDispatcher(): import('undici').Dispatcher | undefined {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { Agent } = require('undici') as typeof import('undici');
    return new Agent({
      headersTimeout: LONG_PROXY_TIMEOUT_MS,
      bodyTimeout: LONG_PROXY_TIMEOUT_MS,
      connectTimeout: 60_000,
    });
  } catch {
    return undefined;
  }
}

async function proxy(request: NextRequest, pathSegments: string[] | undefined) {
  if (!allowSameOriginApiProxy()) {
    return NextResponse.json({ detail: 'Not Found' }, { status: 404 });
  }

  const suffix = pathSegments?.length ? pathSegments.join('/') : '';
  const url = `${upstreamOrigin()}/api/v1/${suffix}${request.nextUrl.search}`;

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) {
      headers.set(key, value);
    }
  });

  const long = proxyFetchInitNeedsLongTimeout(request.method, suffix);
  const init: RequestInit & { duplex?: 'half'; dispatcher?: import('undici').Dispatcher } = {
    method: request.method,
    headers,
    redirect: 'manual',
  };

  if (long) {
    init.signal = AbortSignal.timeout(LONG_PROXY_TIMEOUT_MS);
    const dispatcher = longProxyDispatcher();
    if (dispatcher) init.dispatcher = dispatcher;
  }

  if (request.method !== 'GET' && request.method !== 'HEAD' && request.method !== 'OPTIONS') {
    init.body = request.body;
    init.duplex = 'half';
  }

  const res = await fetch(url, init);
  const out = new Headers(res.headers);
  HOP_BY_HOP.forEach((h) => out.delete(h));

  return new NextResponse(res.body, { status: res.status, statusText: res.statusText, headers: out });
}

type RouteCtx = { params: Promise<{ path?: string[] }> };

async function handle(request: NextRequest, ctx: RouteCtx) {
  const { path } = await ctx.params;
  return proxy(request, path);
}

export const GET = handle;
export const HEAD = handle;
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
export const OPTIONS = handle;

/** Allow long-running batch/import proxy on platforms that honor route segment config. */
export const maxDuration = 600;
