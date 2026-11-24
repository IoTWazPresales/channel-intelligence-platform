import type { NavWarmupQueryDef } from './navWarmupRegistry';

export type WarmupWorkItem = {
  domainId: string;
  query: NavWarmupQueryDef;
};

export type WarmupPrefetchFn = (item: WarmupWorkItem, signal: AbortSignal) => Promise<void>;

/**
 * Low-priority sequential warm-up: caps concurrency, pauses on navigation or while the active
 * page is still fetching, and drops in-flight generation on pause.
 */
export class NavWarmupScheduler {
  readonly concurrency: number;
  private readonly prefetch: WarmupPrefetchFn;
  private queue: WarmupWorkItem[] = [];
  private paused = true;
  private generation = 0;
  private inFlight = 0;

  constructor(opts: { concurrency?: number; prefetch: WarmupPrefetchFn }) {
    this.concurrency = opts.concurrency ?? 2;
    this.prefetch = opts.prefetch;
  }

  get pausedState(): boolean {
    return this.paused;
  }

  get pendingCount(): number {
    return this.queue.length;
  }

  get activeCount(): number {
    return this.inFlight;
  }

  /** Navigation or active-page load: stop scheduling new work and invalidate the current generation. */
  pause(): void {
    this.paused = true;
    this.generation += 1;
    this.queue = [];
    this.inFlight = 0;
  }

  /** Resume after idle; does not clear generation (only pause() bumps it). */
  unpause(): void {
    this.paused = false;
  }

  setQueue(items: WarmupWorkItem[]): void {
    this.queue = [...items];
  }

  tryPump(): void {
    if (this.paused) return;
    while (this.inFlight < this.concurrency && this.queue.length > 0 && !this.paused) {
      const item = this.queue.shift()!;
      const gen = this.generation;
      this.inFlight += 1;
      const controller = new AbortController();
      void this.prefetch(item, controller.signal)
        .catch(() => {
          /* warm-up is best-effort */
        })
        .finally(() => {
          if (gen !== this.generation) return;
          this.inFlight = Math.max(0, this.inFlight - 1);
          this.tryPump();
        });
    }
  }
}

export function flattenDomainQueue(
  domains: { id: string; queries: NavWarmupQueryDef[] }[],
  activeDomainId: string | null | undefined,
): WarmupWorkItem[] {
  const items: WarmupWorkItem[] = [];
  for (const d of domains) {
    if (d.id === activeDomainId) continue;
    for (const query of d.queries) {
      items.push({ domainId: d.id, query });
    }
  }
  return items;
}

export function scheduleAfterIdle(callback: () => void, fallbackMs = 120): () => void {
  const win = typeof globalThis !== 'undefined' ? globalThis : undefined;
  if (win && 'requestIdleCallback' in win && typeof win.requestIdleCallback === 'function') {
    const id = win.requestIdleCallback(() => callback(), { timeout: fallbackMs + 400 });
    return () => win.cancelIdleCallback?.(id);
  }
  if (win && typeof win.setTimeout === 'function') {
    const t = win.setTimeout(callback, fallbackMs);
    return () => win.clearTimeout(t);
  }
  callback();
  return () => {};
}