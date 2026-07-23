import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StewardDrawerChrome } from './StewardDrawerChrome';

describe('StewardDrawerChrome', () => {
  it('renders title, body, and closes', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <StewardDrawerChrome
        title="Product steward"
        onClose={onClose}
        rootTestId="test-drawer"
        closeTestId="test-drawer-close"
      >
        <div>body content</div>
      </StewardDrawerChrome>
    );

    expect(screen.getByTestId('test-drawer')).toBeInTheDocument();
    expect(screen.getByText('Product steward')).toBeInTheDocument();
    expect(screen.getByText('body content')).toBeInTheDocument();

    await user.click(screen.getByTestId('test-drawer-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
