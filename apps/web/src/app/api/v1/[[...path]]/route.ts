import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';

/**
 * Same-origin reverse proxy: browser calls `/api/v1/...` on the Next host, this route forwards to FastAPI.
 *
 * - Local `next dev` / tests (`NODE_ENV` not `production`): enabled by default.
 * - `next start` / production: disabled unless `CIP_ENABLE_NEXT_API_PROXY=true` (e.g. Docker web → api).
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

function upstreamOrigin(): string {
  return (
    process.env.CIP_API_INTERNAL_URL ||
    process.env.CIP_API_PROXY_TARGET ||
    process.env.NEXT_PUBLIC_API_URL ||
    'http://127.0.0.1:8000'
  ).replace(/\/$/, '');
}

function allowSameOriginApiProxy(): boolean {
  const off = process.env.CIP_DISABLE_NEXT_API_PROXY;
  if (off === '1' || off === 'true') return false;
  const on = process.env.CIP_ENABLE_NEXT_API_PROXY;
  if (on === '1' || on === 'true') return true;
  return process.env.NODE_ENV !== 'production';
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

  const init: RequestInit & { duplex?: 'half' } = {
    method: request.method,
    headers,
    redirect: 'manual',
  };

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
export const POST = handle;
export const PATCH = handle;
export const PUT = handle;
export const DELETE = handle;
export const OPTIONS = handle;
