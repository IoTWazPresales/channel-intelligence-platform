import { Suspense } from 'react';

import { LabShell } from '@/design-lab/shell/LabShell';

/**
 * DESIGN LAB — isolated interactive design prototype for N-0013 r3.
 * Not production. Fixture data only; no API calls; independent of the production AppShell.
 * Route group `(design-lab)` keeps it outside the `(app)` shell; delete the folder to remove it.
 */
export const metadata = { title: 'CIP — Design lab' };

export default function DesignLabLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={null}>
      <LabShell>{children}</LabShell>
    </Suspense>
  );
}
