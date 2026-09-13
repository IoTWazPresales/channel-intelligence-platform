'use client';

import { AdminChrome } from '@/features/administration/AdminChrome';
import { UsersWorkspace } from '@/features/administration/UsersWorkspace';

export default function AdminUsersListPage() {
  return (
    <AdminChrome>
      <UsersWorkspace />
    </AdminChrome>
  );
}
