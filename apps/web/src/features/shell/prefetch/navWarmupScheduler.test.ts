import { describe, expect, it, vi } from 'vitest';

import { navWarmupDomainsForRole } from './navWarmupRegistry';
import {
  flattenDomainQueue,
  NavWarmupScheduler,
  type WarmupWorkItem,
} from './navWarmupScheduler';
import { isReadWarmupQuery } from './useNavQueryWarmup';

describe('NavWarmupScheduler', () => {
  const q = (id: string): WarmupWorkItem => ({
    domainId: id,
    query: {
      queryKey: ['warmup', id],
      queryFn: async () => ({ ok: true }),
    },
  });

  it('pumps only after unpause and respects the concurrency cap', async () => {
    const started: string[] = [];
    let release!: () => void;
    const gate = new Promise<void>((r) => {
      release = r;
    });

    const scheduler = new NavWarmupScheduler({
      concurrency: 2,
      prefetch: async (item) => {
        started.push(item.domainId);
        await gate;
      },
    });

    scheduler.setQueue([q('a'), q('b'), q('c')]);
    scheduler.unpause();
    scheduler.tryPump();

    await Promise.resolve();
    expect(started).toEqual(['a', 'b']);
    expect(scheduler.pendingCount).toBe(1);

    release();
    await vi.waitFor(() => expect(started).toContain('c'));
  });

  it('pause clears the queue and stops new prefetches until work is re-queued', async () => {
    const started: string[] = [];
    const scheduler = new NavWarmupScheduler({
      concurrency: 2,
      prefetch: async (item) => {
        started.push(item.domainId);
      },
    });

    scheduler.setQueue([q('a'), q('b')]);
    scheduler.unpause();
    scheduler.tryPump();
    await Promise.resolve();

    scheduler.pause();
    scheduler.setQueue([q('c')]);
    scheduler.unpause();
    scheduler.tryPump();
    await Promise.resolve();

    expect(started).toEqual(['a', 'b']);
    expect(scheduler.pendingCount).toBe(1);
  });

  it('flattenDomainQueue skips the active domain', () => {
    const work = flattenDomainQueue(
      [
        { id: 'stock', queries: [{ queryKey: ['s'], queryFn: async () => null }] },
        { id: 'supply', queries: [{ queryKey: ['u'], queryFn: async () => null }] },
      ],
      'stock',
    );
    expect(work).toHaveLength(1);
    expect(work[0].domainId).toBe('supply');
  });
});

describe('navWarmupDomainsForRole', () => {
  it('exposes only GET-shaped read queries (no mutations)', () => {
    const domains = navWarmupDomainsForRole('admin', {
      id: '1',
      role: 'admin',
      tenant_id: 't1',
    });
    expect(domains.length).toBeGreaterThan(0);
    for (const d of domains) {
      for (const query of d.queries) {
        expect(isReadWarmupQuery(query)).toBe(true);
      }
    }
  });

  it('omits funding when commercial planner is disabled for the build', () => {
    const orig = process.env.NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED;
    process.env.NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED = 'false';
    const domains = navWarmupDomainsForRole('planner', { id: '1', role: 'planner', tenant_id: 't1' });
    expect(domains.some((d) => d.id === 'funding')).toBe(false);
    process.env.NEXT_PUBLIC_CIP_COMMERCIAL_PLANNER_ENABLED = orig;
  });
});