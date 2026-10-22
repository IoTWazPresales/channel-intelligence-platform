import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { useLogDrawerStore } from './logDrawerStore';
import { ShowJobLogButton } from './ShowJobLogButton';

const me = vi.hoisted(() => ({ role: 'admin' as string | null }));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: me.role ? { id: 'u', role: me.role } : undefined }),
}));

beforeEach(() => {
  useLogDrawerStore.setState({ open: false, jobId: null });
});

describe('ShowJobLogButton (N-0089)', () => {
  it("opens the log drawer on this job for an administrator", async () => {
    me.role = 'admin';
    renderWithProviders(<ShowJobLogButton jobId={1688} />);
    await userEvent.setup().click(screen.getByTestId('show-job-log'));
    expect(useLogDrawerStore.getState()).toMatchObject({ open: true, jobId: 1688 });
  });

  it.each(['steward', 'planner', 'viewer', null])('renders nothing for %s', (role) => {
    me.role = role;
    renderWithProviders(<ShowJobLogButton jobId={1688} />);
    expect(screen.queryByTestId('show-job-log')).toBeNull();
  });
});
