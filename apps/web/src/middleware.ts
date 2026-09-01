import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const RETIRED_TO_BRIEF = ['/dashboard', '/exceptions', '/getting-started'];

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
  return NextResponse.next();
}

export const config = {
  matcher: ['/', '/dashboard', '/exceptions', '/getting-started'],
};
