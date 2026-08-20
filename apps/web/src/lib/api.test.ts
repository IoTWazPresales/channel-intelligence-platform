import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

describe('getApiBase', () => {
  const prev = process.env.NEXT_PUBLIC_API_URL;

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = prev;
  });

  it('defaults to same-origin when NEXT_PUBLIC_API_URL is unset', async () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    const { getApiBase } = await import('./api');
    expect(getApiBase()).toBe('');
  });

  it('respects explicit NEXT_PUBLIC_API_URL', async () => {
    process.env.NEXT_PUBLIC_API_URL = 'http://localhost:8010/';
    const { getApiBase } = await import('./api');
    expect(getApiBase()).toBe('http://localhost:8010');
  });
});

describe('readFetchError', () => {
  it('parses FastAPI detail JSON', async () => {
    const { readFetchError } = await import('./api');
    const res = new Response(JSON.stringify({ detail: 'Unknown source' }), { status: 400 });
    await expect(readFetchError(res)).resolves.toBe('Unknown source');
  });

  it('parses structured detail.message from JSON bodies', async () => {
    const { readFetchError } = await import('./api');
    const res = new Response(
      JSON.stringify({ detail: { message: 'Product Master validation failed.', code: 'pm_validate_internal' } }),
      { status: 500 }
    );
    await expect(readFetchError(res)).resolves.toBe('Product Master validation failed.');
  });

  it('joins FastAPI blocking_mapping_errors messages for DSI-style 422 bodies', async () => {
    const { readFetchError } = await import('./api');
    const res = new Response(
      JSON.stringify({
        detail: {
          blocking_mapping_errors: [
            { code: 'missing_column_mapping_distributor', message: 'Required column mapping missing: Distributor.' },
            { code: 'missing_column_mapping_product', message: 'Required column mapping missing: product identifier.' },
          ],
        },
      }),
      { status: 422 }
    );
    const msg = await readFetchError(res);
    expect(msg).toContain('Distributor');
    expect(msg).toContain('product identifier');
  });

  it('replaces HTML error bodies with a short message', async () => {
    const { readFetchError } = await import('./api');
    const res = new Response('<!DOCTYPE html><html><body>500</body></html>', { status: 500 });
    const msg = await readFetchError(res);
    expect(msg).toContain('Server error (500)');
  });
});

describe('401 session handling', () => {
  beforeEach(() => {
    vi.resetModules();
    localStorage.clear();
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('clears the stored token and routes to /login on 401', async () => {
    localStorage.setItem('cip.auth.token.v1', 'expired-token');
    const assign = vi.fn();
    const loc = { pathname: '/admin/shipment-evidence', assign };
    vi.stubGlobal('location', loc);
    Object.defineProperty(window, 'location', { configurable: true, value: loc });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'Authentication required' }), { status: 401 }))
    );
    const { apiGet } = await import('./api');
    await expect(apiGet('/api/v1/shipment-evidence')).rejects.toThrow();
    expect(localStorage.getItem('cip.auth.token.v1')).toBeNull();
    expect(assign).toHaveBeenCalledWith('/login');
  });

  it('does not redirect on 403', async () => {
    const assign = vi.fn();
    const loc = { pathname: '/admin/shipment-evidence', assign };
    vi.stubGlobal('location', loc);
    Object.defineProperty(window, 'location', { configurable: true, value: loc });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'Insufficient role' }), { status: 403 }))
    );
    const { apiGet } = await import('./api');
    await expect(apiGet('/api/v1/shipment-evidence')).rejects.toThrow(/Insufficient role/);
    expect(assign).not.toHaveBeenCalled();
  });

  it('does not redirect a failed /auth/login 401', async () => {
    const assign = vi.fn();
    const loc = { pathname: '/login', assign };
    vi.stubGlobal('location', loc);
    Object.defineProperty(window, 'location', { configurable: true, value: loc });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ detail: 'Invalid credentials' }), { status: 401 }))
    );
    const { apiPost } = await import('./api');
    await expect(apiPost('/api/v1/auth/login', { email: 'x@y.z', password: 'no' })).rejects.toThrow();
    expect(assign).not.toHaveBeenCalled();
  });
});

describe('safeDisplayError', () => {
  it('stringifies Error and strings', async () => {
    const { safeDisplayError } = await import('./api');
    expect(safeDisplayError(new Error('x'))).toBe('x');
    expect(safeDisplayError('y')).toBe('y');
    expect(safeDisplayError({})).toBe('Something went wrong.');
  });
});
