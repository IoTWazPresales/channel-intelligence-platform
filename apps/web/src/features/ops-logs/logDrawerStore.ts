'use client';

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type LogDrawerState = {
  open: boolean;
  /** When set, the drawer shows only this import job's lines. */
  jobId: number | null;
  openLogs: (opts?: { jobId?: number | null }) => void;
  closeLogs: () => void;
  setJobId: (jobId: number | null) => void;
  /** Local time of the newest error the person has seen; a newer one lights the red dot. */
  lastSeenErrorTs: string | null;
  markErrorsSeen: (ts: string | null) => void;
};

export const useLogDrawerStore = create<LogDrawerState>()(
  persist(
    (set) => ({
      open: false,
      jobId: null,
      openLogs: (opts) => set({ open: true, jobId: opts?.jobId ?? null }),
      closeLogs: () => set({ open: false }),
      setJobId: (jobId) => set({ jobId }),
      lastSeenErrorTs: null,
      markErrorsSeen: (ts) => set((s) => ({ lastSeenErrorTs: ts && (!s.lastSeenErrorTs || ts > s.lastSeenErrorTs) ? ts : s.lastSeenErrorTs })),
    }),
    { name: 'cip-logs', partialize: (s) => ({ lastSeenErrorTs: s.lastSeenErrorTs }) },
  ),
);
