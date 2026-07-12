'use client';

import { useCallback, useEffect, useState } from 'react';

export type IntelDepth = 'raw' | 'operational' | 'strategic' | 'forecast';

export type PeriodGrain = 'quarter' | 'year' | 'rolling_weeks';

export const INTEL_DEPTH_STORAGE_KEY = 'cip_intel_depth';

export const INTEL_DEPTH_OPTIONS: { value: IntelDepth; label: string }[] = [
  { value: 'raw', label: 'Raw' },
  { value: 'operational', label: 'Operational' },
  { value: 'strategic', label: 'Strategic' },
  { value: 'forecast', label: 'Forecast' },
];

export function readIntelDepth(): IntelDepth {
  if (typeof window === 'undefined') return 'operational';
  const v = window.localStorage.getItem(INTEL_DEPTH_STORAGE_KEY);
  if (v === 'raw' || v === 'operational' || v === 'strategic' || v === 'forecast') return v;
  return 'operational';
}

export function useIntelDepth(): [IntelDepth, (d: IntelDepth) => void] {
  const [depth, setDepthState] = useState<IntelDepth>('operational');

  useEffect(() => {
    setDepthState(readIntelDepth());
  }, []);

  const setDepth = useCallback((d: IntelDepth) => {
    setDepthState(d);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(INTEL_DEPTH_STORAGE_KEY, d);
    }
  }, []);

  return [depth, setDepth];
}

export function depthAtLeast(depth: IntelDepth, min: IntelDepth): boolean {
  const order: IntelDepth[] = ['raw', 'operational', 'strategic', 'forecast'];
  return order.indexOf(depth) >= order.indexOf(min);
}
