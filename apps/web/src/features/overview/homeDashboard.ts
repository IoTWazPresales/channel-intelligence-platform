/**
 * Dashboard V2 personal home (spec s.1, s.4 header): each person picks which of their dashboards
 * Overview shows, and can reset to the tenant's starter for their job. Stored as the person's own
 * UI layout (`user_ui_layout`, key `dashboard.home`); the job default is the tenant setting
 * `dashboard.job_defaults` (job -> starter key). Nothing here is seeded or guessed.
 */
export const HOME_LAYOUT_KEY = 'dashboard.home';
export const HOME_LAYOUT_URL = `/api/v1/me/ui-layout/${HOME_LAYOUT_KEY}`;
export const JOB_DEFAULTS_KEY = 'dashboard.job_defaults';

export type HomeLayoutDoc = { key: string; value: { dashboard_id?: number } | null; updated_at: string | null };

/** The chosen home when it is still one of the person's visible dashboards; otherwise the first (the earlier behaviour). */
export function pickHome<T extends { id: number }>(dashboards: T[], homeId: number | null | undefined): { active: T | undefined; chosen: boolean } {
  const chosen = homeId != null ? dashboards.find((d) => d.id === homeId) : undefined;
  return chosen ? { active: chosen, chosen: true } : { active: dashboards[0], chosen: false };
}

/** The tenant's starter key for this job, or null when the tenant has not chosen one. */
export function jobDefaultKey(settings: Record<string, unknown> | undefined, job: string | null | undefined): string | null {
  if (!job || !settings) return null;
  const map = settings[JOB_DEFAULTS_KEY];
  if (!map || typeof map !== 'object') return null;
  const key = (map as Record<string, unknown>)[job];
  return typeof key === 'string' && key ? key : null;
}

export type AgeBasis = 'due_at' | 'failed_at' | 'first_detected_at' | 'observed_at';

const AGE_WORD: Record<AgeBasis, string> = {
  due_at: 'Due',
  failed_at: 'Failed',
  first_detected_at: 'First seen',
  observed_at: 'Last data',
};

/** "Due 3 days ago" from a sourced timestamp; "Age unavailable" when the source gives none. */
export function attentionAge(ageAt: string | null | undefined, basis: AgeBasis | string | null | undefined, now: Date = new Date()): string {
  if (!ageAt || !basis || !(basis in AGE_WORD)) return 'Age unavailable';
  const t = Date.parse(ageAt);
  if (!Number.isFinite(t)) return 'Age unavailable';
  const days = Math.floor((now.getTime() - t) / 86_400_000);
  const word = AGE_WORD[basis as AgeBasis];
  if (days <= 0) return `${word} today`;
  return `${word} ${days} ${days === 1 ? 'day' : 'days'} ago`;
}