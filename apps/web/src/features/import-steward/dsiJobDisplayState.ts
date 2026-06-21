/** Coherent DSI job UI state — never show failed + running simultaneously. */

export type DsiJobDisplayState =
  | { kind: 'failed'; message: string }
  | { kind: 'interrupted'; message: string }
  | { kind: 'running'; hasHeartbeat: boolean }
  | { kind: 'running_stale'; message: string }
  | { kind: 'queued' }
  | { kind: 'idle' };

const DEFAULT_STALE_MS = 30 * 60 * 1000;

function parseIsoMs(raw: string | null | undefined): number | null {
  if (!raw || !String(raw).trim()) return null;
  const ms = Date.parse(String(raw).replace('Z', '+00:00'));
  return Number.isFinite(ms) ? ms : null;
}

function hasRecentHeartbeat(args: {
  progressAt?: string | null;
  pipelineStartedAt?: string | null;
  staleAfterMs: number;
}): boolean {
  const now = Date.now();
  const progressAt = parseIsoMs(args.progressAt);
  if (progressAt != null) return now - progressAt < args.staleAfterMs;
  const startedAt = parseIsoMs(args.pipelineStartedAt);
  if (startedAt != null) return now - startedAt < args.staleAfterMs;
  return false;
}

export function deriveDsiJobDisplayState(args: {
  status?: string | null;
  stage?: string | null;
  errorSummary?: string | null;
  progressPhase?: string | null;
  taskState?: string | null;
  progressAt?: string | null;
  pipelineStartedAt?: string | null;
  staleAfterMs?: number;
}): DsiJobDisplayState {
  const status = String(args.status ?? '').trim().toLowerCase();
  const stage = String(args.stage ?? '').trim().toLowerCase();
  const errorSummary = args.errorSummary?.trim() || null;
  const staleAfterMs = args.staleAfterMs ?? DEFAULT_STALE_MS;

  if (status === 'interrupted') {
    return { kind: 'interrupted', message: errorSummary ?? 'Validation interrupted' };
  }
  if (status === 'failed' || stage === 'failed') {
    return { kind: 'failed', message: errorSummary ?? 'Import job failed' };
  }

  if (status === 'running') {
    const heartbeat = hasRecentHeartbeat({
      progressAt: args.progressAt,
      pipelineStartedAt: args.pipelineStartedAt,
      staleAfterMs,
    });
    if (errorSummary && !heartbeat) {
      return { kind: 'running_stale', message: 'State unknown — check now' };
    }
    const taskState = String(args.taskState ?? '').trim().toUpperCase();
    const phase = String(args.progressPhase ?? '').trim().toLowerCase();
    if (!heartbeat && (taskState === 'STARTED' || taskState === 'PENDING' || phase === 'queued')) {
      return { kind: 'queued' };
    }
    if (!heartbeat) {
      return { kind: 'running_stale', message: 'State unknown — check now' };
    }
    return { kind: 'running', hasHeartbeat: true };
  }

  const taskState = String(args.taskState ?? '').trim().toUpperCase();
  const phase = String(args.progressPhase ?? '').trim().toLowerCase();
  if (taskState === 'PENDING' || phase === 'queued') {
    return { kind: 'queued' };
  }

  return { kind: 'idle' };
}
