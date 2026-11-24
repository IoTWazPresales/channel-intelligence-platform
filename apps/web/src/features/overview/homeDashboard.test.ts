import { describe, expect, it } from 'vitest';

import { attentionAge, jobDefaultKey, pickHome } from './homeDashboard';

describe('home dashboard', () => {
  const list = [{ id: 4 }, { id: 9 }];
  it('uses the chosen home when it is still visible, else the first dashboard', () => {
    expect(pickHome(list, 9)).toEqual({ active: { id: 9 }, chosen: true });
    expect(pickHome(list, 77)).toEqual({ active: { id: 4 }, chosen: false });
    expect(pickHome([], 9)).toEqual({ active: undefined, chosen: false });
  });
  it('reads the job default only from the tenant setting', () => {
    const settings = { 'dashboard.job_defaults': { account_manager: 'my_accounts' } };
    expect(jobDefaultKey(settings, 'account_manager')).toBe('my_accounts');
    expect(jobDefaultKey(settings, 'finance')).toBeNull();
    expect(jobDefaultKey({}, 'account_manager')).toBeNull();
    expect(jobDefaultKey(settings, null)).toBeNull();
  });
});

describe('attention age', () => {
  const now = new Date('2026-11-24T10:00:00Z');
  it('words a sourced age by its basis', () => {
    expect(attentionAge('2026-11-21T08:00:00Z', 'due_at', now)).toBe('Due 3 days ago');
    expect(attentionAge('2026-11-23T09:00:00Z', 'failed_at', now)).toBe('Failed 1 day ago');
    expect(attentionAge('2026-11-24T09:00:00Z', 'observed_at', now)).toBe('Last data today');
  });
  it('never invents an age', () => {
    expect(attentionAge(null, 'due_at', now)).toBe('Age unavailable');
    expect(attentionAge('2026-11-21T08:00:00Z', null, now)).toBe('Age unavailable');
    expect(attentionAge('nope', 'due_at', now)).toBe('Age unavailable');
  });
});