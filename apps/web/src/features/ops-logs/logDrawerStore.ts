'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const DOCK_MIN_HEIGHT = 140;
export const DOCK_MAX_HEIGHT = 1200;
export const DOCK_DEFAULT_HEIGHT = 320;

export function clampDockHeight(h: number): number {
  if (!Number.isFinite(h)) return DOCK_DEFAULT_HEIGHT;
  return Math.min(DOCK_MAX_HEIGHT, Math.max(DOCK_MIN_HEIGHT, Math.round(h)));
}

type LogDockState = {
  /** The log panel is shown (docked at the bottom, or collapsed to its thin bar). Remembered per browser. */
  open: boolean;
  /** Collapsed to a thin bar that keeps the red error dot. Remembered per browser. */
  collapsed: boolean;
  /** Height in px when expanded. Remembered per browser. */
  height: number;
  /** When set, the panel shows only this import job's lines. */
  jobId: number | null;
  openLogs: (opts?: { jobId?: number | null }) => void;
  closeLogs: () => void;
  setCollapsed: (collapsed: boolean) => void;
  setHeight: (height: number) => void;
  setJobId: (jobId: number | null) => void;
  /** Local time of the newest error the person has seen; a newer one lights the red dot. */
  lastSeenErrorTs: string | null;
  markErrorsSeen: (ts: string | null) => void;
};

export const useLogDrawerStore = create<LogDockState>()(
  persist(
    (set) => ({
      open: false,
      collapsed: false,
      height: DOCK_DEFAULT_HEIGHT,
      jobId: null,
      openLogs: (opts) => set((s) => ({ open: true, collapsed: false, jobId: opts?.jobId !== undefined ? opts.jobId : s.jobId })),
      closeLogs: () => set({ open: false }),
      setCollapsed: (collapsed) => set({ collapsed }),
      setHeight: (height) => set({ height: clampDockHeight(height) }),
      setJobId: (jobId) => set({ jobId }),
      lastSeenErrorTs: null,
      markErrorsSeen: (ts) =>
        set((s) => ({ lastSeenErrorTs: ts && (!s.lastSeenErrorTs || ts > s.lastSeenErrorTs) ? ts : s.lastSeenErrorTs })),
    }),
    {
      name: 'cip-logs',
      partialize: (s) => ({ lastSeenErrorTs: s.lastSeenErrorTs, open: s.open, collapsed: s.collapsed, height: s.height }),
      merge: (persisted, current) => {
        const p = (persisted ?? {}) as Partial<LogDockState>;
        return {
          ...current,
          lastSeenErrorTs: typeof p.lastSeenErrorTs === 'string' ? p.lastSeenErrorTs : null,
          open: p.open === true,
          collapsed: p.collapsed === true,
          height: clampDockHeight(typeof p.height === 'number' ? p.height : DOCK_DEFAULT_HEIGHT),
        };
      },
    },
  ),
);

/** The person is looking at the log: open and not collapsed. */
export function useLogDockWatching(): boolean {
  return useLogDrawerStore((s) => s.open && !s.collapsed);
}
