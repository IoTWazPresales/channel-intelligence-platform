import { apiGet } from './api';

/** Response from GET /api/v1/dev/database-wipe, or a synthetic payload when the request fails. */
export type WipeStatus = { wipe_enabled: boolean; fetch_error?: string };

/**
 * Loads whether POST /api/v1/dev/database-wipe is allowed. Never throws: failures return
 * `{ wipe_enabled: false, fetch_error }` so UI can show CLI alternatives.
 */
export async function loadWipeAvailability(signal?: AbortSignal): Promise<WipeStatus> {
  try {
    return await apiGet<WipeStatus>('/api/v1/dev/database-wipe', signal ? { signal } : undefined);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return { wipe_enabled: false, fetch_error: msg };
  }
}
