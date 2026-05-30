import { Suspense } from 'react';

import { AppShell } from '@/features/shell/AppShell';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <AppShell title="Channel Intelligence Platform">{children}</AppShell>
    </Suspense>
  );
}
