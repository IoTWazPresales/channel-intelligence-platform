'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode, useEffect, useState } from 'react';

import { useUiStore } from '@/stores/uiStore';
import { CipThemeProvider } from '@/theme/CipThemeProvider';

function ThemeBridge({ children }: { children: ReactNode }) {
  const density = useUiStore((s) => s.density);
  const colorMode = useUiStore((s) => s.colorMode);
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);
  // SSR and the first client paint stay dark so persist() cannot mismatch hydration.
  return (
    <CipThemeProvider density={density} mode={mounted ? colorMode : 'dark'}>
      {children}
    </CipThemeProvider>
  );
}

function QueryLifecycle({ client, children }: { client: QueryClient; children: ReactNode }) {
  useEffect(() => {
    const onPageShow = (e: PageTransitionEvent) => {
      if (e.persisted) {
        void client.invalidateQueries();
      }
    };
    window.addEventListener('pageshow', onPageShow);
    return () => window.removeEventListener('pageshow', onPageShow);
  }, [client]);
  return <>{children}</>;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            /** Fewer full refetches when moving between screens; explicit Refresh still works. */
            staleTime: 60_000,
            /** Avoid focus-driven refetch racing with navigation / manual refresh (can briefly show new data then older in-flight results). */
            refetchOnWindowFocus: false,
            refetchOnReconnect: true,
            retry: 1,
          },
        },
      })
  );
  return (
    <QueryClientProvider client={client}>
      <QueryLifecycle client={client}>
        <ThemeBridge>{children}</ThemeBridge>
      </QueryLifecycle>
    </QueryClientProvider>
  );
}
