'use client';

import { AdminChrome } from '@/features/administration/AdminChrome';
import { AdminOverview } from '@/features/administration/AdminOverview';

export default function AdministrationPage() {
  return (
    <AdminChrome>
      <AdminOverview />
    </AdminChrome>
  );
}
