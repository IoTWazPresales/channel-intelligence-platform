import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { loadWipeAvailability } from './wipeAvailability';

describe('loadWipeAvailability', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns server payload on success', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ wipe_enabled: true }),
    });
    const r = await loadWipeAvailability();
    expect(r).toEqual({ wipe_enabled: true });
  });

  it('returns fetch_error instead of throwing on non-ok', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => 'missing',
    });
    const r = await loadWipeAvailability();
    expect(r.wipe_enabled).toBe(false);
    expect(r.fetch_error).toMatch(/404/);
  });

  it('returns fetch_error when fetch rejects', async () => {
    global.fetch = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'));
    const r = await loadWipeAvailability();
    expect(r.wipe_enabled).toBe(false);
    expect(r.fetch_error).toMatch(/Failed to fetch/);
  });
});
