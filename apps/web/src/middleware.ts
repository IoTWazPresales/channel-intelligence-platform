import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const RETIRED_TO_BRIEF = ['/dashboard', '/exceptions', '/getting-started'];

const STOCK_LEGACY_REDIRECTS: Record<string, string> = {
  '/sell-out': '/stock?lens=movement',
  '/plan-vs-executed': '/stock?lens=execution',
  '/shipping': '/supply/shipments',
};

const LINEUP_LEGACY_REDIRECTS: Record<string, string> = {
  '/buy-plans': '/lineup/cases',
};

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === '/') {
    const url = request.nextUrl.clone();
    url.pathname = '/brief';
    return NextResponse.redirect(url);
  }
  if (RETIRED_TO_BRIEF.includes(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = '/brief';
    return NextResponse.redirect(url);
  }
  const stockTarget = STOCK_LEGACY_REDIRECTS[pathname];
  if (stockTarget) {
    const url = request.nextUrl.clone();
    const [path, query] = stockTarget.split('?');
    url.pathname = path;
    if (query) {
      const params = new URLSearchParams(query);
      params.forEach((v, k) => url.searchParams.set(k, v));
    }
    return NextResponse.redirect(url);
  }
  const lineupTarget = LINEUP_LEGACY_REDIRECTS[pathname];
  if (lineupTarget) {
    const url = request.nextUrl.clone();
    url.pathname = lineupTarget;
    return NextResponse.redirect(url);
  }
  const legacyCoverPath = pathname === '/stock/cover' || pathname.startsWith('/stock/cover/');
  if (pathname === '/stock' || legacyCoverPath) {
    const lens = (
      request.nextUrl.searchParams.get('lens') ??
      request.nextUrl.searchParams.get('tab') ??
      ''
    ).trim().toLowerCase();
    if (legacyCoverPath || !lens || lens === 'cover') {
      const url = new URL(request.nextUrl.toString());
      url.pathname = '/inventory';
      url.searchParams.delete('lens');
      if (url.searchParams.get('tab')?.trim().toLowerCase() === 'cover') {
        url.searchParams.delete('tab');
      }
      return NextResponse.redirect(url);
    }
    if (lens === 'inbound') {
      const url = request.nextUrl.clone();
      url.pathname = '/supply/shipments';
      url.searchParams.delete('lens');
      return NextResponse.redirect(url);
    }
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    '/',
    '/dashboard',
    '/exceptions',
    '/getting-started',
    '/sell-out',
    '/plan-vs-executed',
    '/shipping',
    '/inventory',
    '/buy-plans',
    '/stock',
    '/stock/cover/:path*',
  ],
};
