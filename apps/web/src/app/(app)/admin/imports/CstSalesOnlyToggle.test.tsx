import React, { useState } from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { CstSalesOnlyToggle } from './CstSalesOnlyToggle';

function Harness() {
  const [on, setOn] = useState(false);
  return (
    <>
      <CstSalesOnlyToggle checked={on} onChange={setOn} />
      <span data-testid="state">{on ? 'on' : 'off'}</span>
    </>
  );
}

describe('CstSalesOnlyToggle', () => {
  it('is off by default, labelled, described, and toggles', () => {
    renderWithProviders(<Harness />);
    const box = screen.getByRole('checkbox', { name: 'Sales-only file (units, no on-hand)' });
    expect(box).not.toBeChecked();
    expect(box).toHaveAccessibleDescription(/refused unless this is ticked/);
    fireEvent.click(box);
    expect(screen.getByTestId('state')).toHaveTextContent('on');
  });
});
