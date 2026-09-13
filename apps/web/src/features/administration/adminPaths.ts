export const ADMIN_TITLE = 'Administration';

export const ADMIN_DESCRIPTION = 'Users and roles, background operations, audited SQL access, settings.';

export type AdminLens = 'hub' | 'users' | 'ops' | 'sql' | 'settings';

export const ADMIN_LEAVES: { value: Exclude<AdminLens, 'hub'>; label: string; href: string }[] = [
  { value: 'users', label: 'Users & roles', href: '/admin/users/list' },
  { value: 'ops', label: 'Operations', href: '/admin/ops' },
  { value: 'sql', label: 'SQL viewer', href: '/admin/sql-viewer' },
  { value: 'settings', label: 'Settings', href: '/settings' },
];

export function adminLensFromPath(pathname: string): AdminLens {
  if (pathname.startsWith('/admin/users/list')) return 'users';
  if (pathname.startsWith('/admin/ops')) return 'ops';
  if (pathname.startsWith('/admin/sql-viewer')) return 'sql';
  if (pathname.startsWith('/settings')) return 'settings';
  return 'hub';
}

/** Relocate the Users & roles workspace off the Administration hub without changing rail hrefs. */
export function adminWorkflowHref(href: string): string {
  return href === '/admin/users' ? '/admin/users/list' : href;
}
