'use client';

import type { ReactNode } from 'react';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { apiGet, apiPost } from '@/lib/api';

export type BackgroundTaskRow = {
  id: string;
  type: string;
  title: string;
  status: string;
  summary?: string;
  import_job_id?: number | null;
  related_import_job_ids?: number[];
  lines_total?: number | null;
  lines_processed?: number | null;
  newly_resolved?: number | null;
  still_unresolved?: number | null;
  error_message?: string | null;
  commit_phase?: string | null;
  created_at?: string;
  updated_at?: string;
};

type Ctx = {
  tasks: BackgroundTaskRow[];
  redisAvailable: boolean;
  refresh: () => Promise<void>;
  dismiss: (id: string) => Promise<void>;
};

const BackgroundTasksContext = createContext<Ctx | null>(null);

export function BackgroundTasksProvider({ children }: { children: ReactNode }) {
  const [tasks, setTasks] = useState<BackgroundTaskRow[]>([]);
  const [redisAvailable, setRedisAvailable] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await apiGet<{ items: BackgroundTaskRow[]; redis_available?: boolean }>('/api/v1/background-tasks');
      setTasks(Array.isArray(res.items) ? res.items : []);
      setRedisAvailable(res.redis_available !== false);
    } catch {
      setTasks([]);
    }
  }, []);

  const dismiss = useCallback(async (id: string) => {
    await apiPost(`/api/v1/background-tasks/${encodeURIComponent(id)}/dismiss`, {});
    await refresh();
  }, [refresh]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(id);
  }, [refresh]);

  const value = useMemo(
    () => ({
      tasks,
      redisAvailable,
      refresh,
      dismiss,
    }),
    [tasks, redisAvailable, refresh, dismiss]
  );

  return <BackgroundTasksContext.Provider value={value}>{children}</BackgroundTasksContext.Provider>;
}

export function useBackgroundTasks(): Ctx {
  const v = useContext(BackgroundTasksContext);
  if (!v) {
    throw new Error('useBackgroundTasks must be used within BackgroundTasksProvider');
  }
  return v;
}
