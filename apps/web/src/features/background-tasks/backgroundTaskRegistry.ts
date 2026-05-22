'use client';

import { create } from 'zustand';

import type { BackgroundTaskKind } from './importJobProgress.types';

export type ClientBackgroundTask = {
  taskId: string;
  importJobId: number;
  kind: BackgroundTaskKind;
  label: string;
  registeredAt: number;
};

type BackgroundTaskRegistryState = {
  clientTasks: Record<string, ClientBackgroundTask>;
  registerTask: (task: Omit<ClientBackgroundTask, 'registeredAt'>) => void;
  removeTask: (taskId: string) => void;
  clearOlderThan: (maxAgeMs: number) => void;
};

export const useBackgroundTaskRegistry = create<BackgroundTaskRegistryState>((set) => ({
  clientTasks: {},
  registerTask: (task) =>
    set((s) => ({
      clientTasks: {
        ...s.clientTasks,
        [task.taskId]: { ...task, registeredAt: Date.now() },
      },
    })),
  removeTask: (taskId) =>
    set((s) => {
      const next = { ...s.clientTasks };
      delete next[taskId];
      return { clientTasks: next };
    }),
  clearOlderThan: (maxAgeMs) =>
    set((s) => {
      const cutoff = Date.now() - maxAgeMs;
      const next: Record<string, ClientBackgroundTask> = {};
      for (const [id, t] of Object.entries(s.clientTasks)) {
        if (t.registeredAt >= cutoff) next[id] = t;
      }
      return { clientTasks: next };
    }),
}));

/** Call when an async import endpoint returns a Celery task id. */
export function registerClientBackgroundTask(args: {
  taskId: string;
  importJobId: number;
  kind: BackgroundTaskKind;
  label: string;
}): void {
  useBackgroundTaskRegistry.getState().registerTask(args);
}
