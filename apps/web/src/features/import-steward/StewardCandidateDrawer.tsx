'use client';

import type { ReactNode } from 'react';

import { StewardDrawerChrome } from './StewardDrawerChrome';

/** Generic steward drawer chrome + evidence-body slot (S5/S6 shell). */
export function StewardCandidateDrawer({
  title,
  onClose,
  rootTestId,
  closeTestId,
  ariaLabel,
  children,
}: {
  title: string;
  onClose: () => void;
  rootTestId: string;
  closeTestId: string;
  ariaLabel: string;
  children: ReactNode;
}) {
  return (
    <StewardDrawerChrome
      title={title}
      onClose={onClose}
      rootTestId={rootTestId}
      closeTestId={closeTestId}
      ariaLabel={ariaLabel}
    >
      {children}
    </StewardDrawerChrome>
  );
}
