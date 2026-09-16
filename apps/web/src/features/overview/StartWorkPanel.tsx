'use client';

import { StartWorkLaunch } from '@/features/overview/StartWorkLaunch';
import { useCurrentUser } from '@/features/shell/useCurrentUser';

export function StartWorkPanel() {
  const { data: me } = useCurrentUser();
  const role = me?.role ? String(me.role) : null;
  return <StartWorkLaunch role={role} layout="strip" />;
}
