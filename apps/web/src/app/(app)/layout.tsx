import { BackgroundTasksProvider } from '@/features/backgroundTasks/BackgroundTasksProvider';
import { AppShell } from '@/features/shell/AppShell';

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <BackgroundTasksProvider>
      <AppShell title="Channel Intelligence Platform">{children}</AppShell>
    </BackgroundTasksProvider>
  );
}
