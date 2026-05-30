/**
 * API origin for browser `fetch`.
 *
 * Default: **same-origin** (`''`) so requests go to `/api/v1/...` on the Next host and are forwarded by
 * `src/app/api/v1/[[...path]]/route.ts` to FastAPI (`CIP_ENABLE_NEXT_API_PROXY` + `CIP_API_INTERNAL_URL` in Docker).
 * That avoids cross-origin/CORS/preflight for uploads and custom headers.
 *
 * Set `NEXT_PUBLIC_API_URL` only when the browser must call the API host directly (e.g. API on another machine).
 */
export function getApiBase(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL;
  if (raw != null && String(raw).trim() !== '') {
    return String(raw).trim().replace(/\/$/, '');
  }
  return '';
}

export function apiUrl(path: string): string {
  const b = getApiBase();
  const p = path.startsWith('/') ? path : `/${path}`;
  return b ? `${b}${p}` : p;
}

/** Extract a short user-facing message from a failed JSON API body (FastAPI ``detail`` shapes). */
export function parseApiErrorDetailText(text: string): string {
  const t = text.trim();
  if (!t) return '';
  if (!t.startsWith('{')) return t.length > 600 ? `${t.slice(0, 600)}…` : t;
  try {
    const j = JSON.parse(t) as { detail?: unknown };
    const d = j.detail;
    if (typeof d === 'string') return d;
    if (typeof d === 'object' && d !== null && !Array.isArray(d)) {
      const rec = d as Record<string, unknown>;
      const bme = rec.blocking_mapping_errors;
      if (Array.isArray(bme) && bme.length) {
        const parts = bme
          .map((x) => {
            if (typeof x === 'object' && x !== null && 'message' in x) {
              const m = (x as { message?: unknown }).message;
              if (typeof m === 'string' && m.trim()) return m.trim();
            }
            return '';
          })
          .filter(Boolean);
        if (parts.length) return parts.join(' ');
      }
      const msg = rec.message;
      if (typeof msg === 'string' && msg.trim()) return msg.trim();
      const alt = rec.msg;
      if (typeof alt === 'string' && alt.trim()) return alt.trim();
    }
    if (Array.isArray(d)) {
      const parts = d
        .map((x) =>
          typeof x === 'object' && x !== null && 'msg' in x ? String((x as { msg: string }).msg) : String(x)
        )
        .filter(Boolean);
      if (parts.length) return parts.join('; ');
    }
  } catch {
    /* fall through */
  }
  const lower = t.toLowerCase();
  if (lower.includes('<!doctype') || lower.includes('<html')) {
    return 'Server error. Check API logs or try again.';
  }
  return t.length > 600 ? `${t.slice(0, 600)}…` : t;
}

/** Parse a failed `fetch` body into a short, UI-safe message (avoids embedding HTML error pages). */
export async function readFetchError(res: Response): Promise<string> {
  const text = (await res.text()).trim();
  if (!text) return `Request failed (${res.status})`;
  const parsed = parseApiErrorDetailText(text);
  if (parsed) return parsed;
  return `Request failed (${res.status})`;
}

/** Safe string for React alert children when displaying mutation errors. */
export function safeDisplayError(e: unknown): string {
  if (e instanceof Error) return e.message;
  if (typeof e === 'string') return e;
  return 'Something went wrong.';
}

const defaultHeaders = (init?: RequestInit, includeJsonContentType = true): HeadersInit => ({
  ...(includeJsonContentType ? { 'Content-Type': 'application/json' } : {}),
  'X-User-Role': 'admin',
  'X-User-Id': 'demo-user',
  ...init?.headers,
});

/**
 * Browser `fetch` for JSON GET. Pass `{ signal }` from TanStack Query `queryFn` so superseded
 * requests abort and cannot overwrite the cache with stale responses.
 */
export async function apiGet<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: defaultHeaders(init),
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(await readFetchError(res));
  }
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: 'POST',
    ...init,
    headers: defaultHeaders(init, body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
  });
  if (!res.ok) {
    const text = await res.text();
    throw parseConflictError(res.status, text);
  }
  return res.json() as Promise<T>;
}

/** POST multipart (e.g. CSV upload). Do not set JSON Content-Type — browser sets multipart boundary. */
export async function apiPostFormData<T>(path: string, formData: FormData, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: 'POST',
    ...init,
    headers: {
      'X-User-Role': 'admin',
      'X-User-Id': 'demo-user',
      ...init?.headers,
    },
    body: formData,
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(await readFetchError(res));
  }
  return res.json() as Promise<T>;
}

export async function apiPatch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: 'PATCH',
    ...init,
    headers: defaultHeaders(init, body !== undefined),
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(await readFetchError(res));
  }
  return res.json() as Promise<T>;
}

function errorMessageFromResponse(status: number, text: string): string {
  const parsed = parseApiErrorDetailText(text);
  if (parsed.trim()) return parsed;
  return `Request failed (${status})`;
}

/** 409 with structured `references` from APIs such as `DELETE /products/{id}`. */
export type ApiReferenceCount = { label: string; count: number };

export class HttpConflictError extends Error {
  constructor(
    message: string,
    public readonly references: ApiReferenceCount[]
  ) {
    super(message);
    this.name = 'HttpConflictError';
  }

  static is(e: unknown): e is HttpConflictError {
    if (e instanceof HttpConflictError) return true;
    if (e === null || typeof e !== 'object') return false;
    const o = e as { name?: unknown; references?: unknown };
    return o.name === 'HttpConflictError' && Array.isArray(o.references);
  }
}

function normalizeReferenceRows(raw: unknown[]): ApiReferenceCount[] {
  const out: ApiReferenceCount[] = [];
  for (const r of raw) {
    if (!r || typeof r !== 'object') continue;
    const row = r as { label?: unknown; count?: unknown };
    if (typeof row.label !== 'string') continue;
    const c = row.count;
    const n = typeof c === 'number' ? c : typeof c === 'string' ? Number(c) : NaN;
    if (!Number.isFinite(n)) continue;
    out.push({ label: row.label, count: n });
  }
  return out;
}

function conflictPayloadFrom409Body(text: string): { message: string; references: ApiReferenceCount[] } | null {
  let j: Record<string, unknown>;
  try {
    j = JSON.parse(text) as Record<string, unknown>;
  } catch {
    return null;
  }
  /** Some proxies return the conflict object at the root instead of under `detail`. */
  if (typeof j.message === 'string' || Array.isArray(j.references)) {
    const msg = typeof j.message === 'string' ? j.message : 'Conflict';
    const refs = Array.isArray(j.references) ? normalizeReferenceRows(j.references) : [];
    return { message: msg, references: refs };
  }
  const rawDetail = j.detail;
  let d: unknown = rawDetail;
  if (typeof d === 'string') {
    const detailStr = d;
    try {
      d = JSON.parse(detailStr) as unknown;
    } catch {
      return { message: detailStr, references: [] };
    }
  }
  if (typeof d !== 'object' || d === null || Array.isArray(d)) {
    if (typeof rawDetail === 'string') return { message: rawDetail, references: [] };
    return null;
  }
  const o = d as { message?: unknown; references?: unknown };
  const msg = typeof o.message === 'string' ? o.message : 'Conflict';
  const refs = Array.isArray(o.references) ? normalizeReferenceRows(o.references) : [];
  if ('references' in o || 'message' in o) return { message: msg, references: refs };
  const flat = j as { message?: unknown; references?: unknown };
  if (Array.isArray(flat.references)) {
    return { message: typeof flat.message === 'string' ? flat.message : msg, references: normalizeReferenceRows(flat.references) };
  }
  return null;
}

function parseConflictError(status: number, text: string): Error {
  if (status === 409) {
    const parsed = conflictPayloadFrom409Body(text);
    if (parsed) return new HttpConflictError(parsed.message, parsed.references);
    try {
      JSON.parse(text);
      return new HttpConflictError(errorMessageFromResponse(409, text), []);
    } catch {
      const plain = text.trim();
      return new HttpConflictError(plain || 'Conflict', []);
    }
  }
  return new Error(errorMessageFromResponse(status, text));
}

function parseDeleteError(status: number, text: string): Error {
  return parseConflictError(status, text);
}

export async function apiDelete(path: string, init?: RequestInit): Promise<void> {
  const res = await fetch(apiUrl(path), {
    method: 'DELETE',
    ...init,
    headers: defaultHeaders(init, false),
    cache: 'no-store',
  });
  if (!res.ok) {
    const text = await res.text();
    throw parseDeleteError(res.status, text);
  }
}

/** DELETE with JSON body (e.g. admin maintenance confirms). */
export async function apiDeleteJson<T>(path: string, body: unknown, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), {
    method: 'DELETE',
    ...init,
    headers: defaultHeaders(init, true),
    body: JSON.stringify(body ?? {}),
    cache: 'no-store',
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(parseApiErrorDetailText(text) || `Request failed (${res.status})`);
  }
  if (!text.trim()) return {} as T;
  return JSON.parse(text) as T;
}

/**
 * Load `{ label, count }` breakdown for a product (delete-block UX).
 * Tries routes in order; returns [] if the running API has no breakdown endpoints (stale process).
 */
export async function fetchProductReferenceBreakdown(
  productId: number,
  init?: RequestInit
): Promise<ApiReferenceCount[]> {
  const q = encodeURIComponent(String(productId));
  const paths = [
    `/api/v1/products/references?product_id=${q}`,
    `/api/v1/products/id/${productId}/refs`,
    `/api/v1/products/${productId}/references`,
  ] as const;
  for (const path of paths) {
    try {
      const data = await apiGet<{ references?: unknown[] }>(path, init);
      const refs = normalizeReferenceRows(Array.isArray(data.references) ? data.references : []);
      if (refs.length) return refs;
    } catch {
      /* 404 / old API */
    }
  }
  return [];
}

export async function apiDownloadBlob(path: string, filename: string, init?: RequestInit): Promise<void> {
  const res = await fetch(apiUrl(path), {
    ...init,
    headers: defaultHeaders(init, false),
    cache: 'no-store',
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${await res.text()}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
