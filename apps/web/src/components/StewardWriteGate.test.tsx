import { Button, TextField } from '@mui/material';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { roleState } = vi.hoisted(() => ({ roleState: { current: 'steward' as string | undefined } }));

vi.mock('@/features/shell/useCurrentUser', () => ({
  useCurrentUser: () => ({ data: roleState.current === undefined ? undefined : { id: 'u1', role: roleState.current } }),
}));

import { StewardWriteGate } from './StewardWriteGate';

function renderGate(onApply = vi.fn()) {
  render(
    <StewardWriteGate>
      <TextField label="Alias" />
      <Button onClick={onApply}>Apply</Button>
    </StewardWriteGate>,
  );
  return onApply;
}

describe('StewardWriteGate (N-0086)', () => {
  beforeEach(() => {
    roleState.current = 'steward';
  });

  it.each(['steward', 'admin'])('leaves controls on and shows no notice for %s', async (role) => {
    roleState.current = role;
    const onApply = renderGate();
    expect(screen.queryByTestId('steward-write-notice')).toBeNull();
    const apply = screen.getByRole('button', { name: 'Apply' });
    expect(apply).toBeEnabled();
    await userEvent.click(apply);
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Alias')).toBeEnabled();
  });

  it.each(['planner', 'viewer'])('turns controls off with the reason for %s', async (role) => {
    roleState.current = role;
    const onApply = renderGate();
    const notice = screen.getByTestId('steward-write-notice');
    expect(notice).toHaveTextContent(`signed in as ${role}`);
    expect(notice).toHaveTextContent('steward or admin');
    const apply = screen.getByRole('button', { name: 'Apply' });
    expect(apply).toBeDisabled();
    // A user's click on a control inside a disabled fieldset is not delivered (HTML disabled semantics).
    await userEvent.click(apply);
    expect(onApply).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Alias')).toBeDisabled();
    const area = screen.getByTestId('steward-write-area');
    expect(area).toBeDisabled();
    expect(area).toHaveAttribute('aria-describedby', notice.id);
  });

  it('does not disable anything before the role is known', () => {
    roleState.current = undefined;
    renderGate();
    expect(screen.queryByTestId('steward-write-notice')).toBeNull();
    expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled();
  });
});
