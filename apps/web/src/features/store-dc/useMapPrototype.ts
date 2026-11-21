'use client';

import { useEffect, useState } from 'react';

export const MAP_PROTOTYPE_KEY = 'cip.storeMap.prototype.v1';

export function useMapPrototype(): [boolean, (enabled: boolean) => void] {
  // Server and first browser render both preserve today's SVG map.
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    try {
      setEnabled(window.localStorage.getItem(MAP_PROTOTYPE_KEY) === 'true');
    } catch {
      // Restricted/private storage must not prevent either map from working.
    }
  }, []);

  function update(next: boolean) {
    setEnabled(next);
    try {
      window.localStorage.setItem(MAP_PROTOTYPE_KEY, String(next));
    } catch {
      // The switch still works for this mount.
    }
  }

  return [enabled, update];
}
