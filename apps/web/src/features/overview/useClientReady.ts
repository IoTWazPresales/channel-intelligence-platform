'use client';

import { useEffect, useState } from 'react';

/** Gate SSR/client first paint so query-cache numbers do not hydrate-mismatch against "—". */
export function useClientReady() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    setReady(true);
  }, []);
  return ready;
}
