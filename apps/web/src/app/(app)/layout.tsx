import { AppShell } from '@/features/shell/AppShell';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AppShell title="Channel Intelligence Platform">{children}</AppShell>;
}
