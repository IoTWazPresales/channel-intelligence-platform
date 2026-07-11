'use client';

import { useEffect, useRef, useState } from 'react';

/**
 * Local search box state backed by a URL `q` (or similar) param.
 * Typing updates local state immediately; `onCommit` fires after `delayMs`
 * idle so TanStack Query / router.replace do not run on every keystroke.
 *
 * External URL changes (back/forward, clear-filters) sync into the input;
 * commits we ourselves triggered do not clobber characters typed during the
 * round-trip.
 */
export function useDebouncedUrlQuery(
  urlValue: string,
  onCommit: (next: string) => void,
  delayMs = 300,
): [string, (value: string) => void] {
  const [input, setInput] = useState(urlValue);
  const skipNextUrlSync = useRef(false);
  const onCommitRef = useRef(onCommit);
  onCommitRef.current = onCommit;

  useEffect(() => {
    if (skipNextUrlSync.current) {
      skipNextUrlSync.current = false;
      return;
    }
    setInput(urlValue);
  }, [urlValue]);

  useEffect(() => {
    if (input === urlValue) return;
    const t = window.setTimeout(() => {
      skipNextUrlSync.current = true;
      onCommitRef.current(input);
    }, delayMs);
    return () => window.clearTimeout(t);
  }, [input, urlValue, delayMs]);

  return [input, setInput];
}
