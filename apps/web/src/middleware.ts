import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const RETIRED_TO_BRIEF = ['/dashboard', '/exceptions', '/getting-started'];

const STOCK_LEGACY_REDIRECTS: Record<string, string> = {
  '/sell-out': '/stock?lens=movement',
  '/plan-vs-executed': '/stock?lens=execution',
  '/shipping': '/stock?lens=inbound',
  '/inventory': '/stock?lens=cover',
};

const LINEUP_LEGACY_REDIRECTS: Record<string, string> = {
  '/buy-plans': '/lineup',
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
  return NextResponse.next();
}

export const config = {
  matcher: ['/', '/dashboard', '/exceptions', '/getting-started', '/sell-out', '/plan-vs-executed', '/shipping', '/inventory', '/buy-plans'],
};
