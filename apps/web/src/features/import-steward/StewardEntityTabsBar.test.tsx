import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StewardEntityTabsBar } from './StewardEntityTabsBar';

const TABS = [
  { id: 'distributor' as const, label: 'Distributors', testId: 'tab-distributor' },
  { id: 'customer' as const, label: 'Customers', testId: 'tab-customer' },
];

describe('StewardEntityTabsBar', () => {
  it('renders counts, needs-work chip, and changes tab', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <StewardEntityTabsBar
        tabs={TABS}
        activeTab="distributor"
        onChange={onChange}
        counts={{
          distributor: { total: 12, needsWork: 3 },
          customer: { total: 4, needsWork: 0 },
        }}
        testIdPrefix="demo"
        ariaLabel="Demo entity resolution"
        formatTabAriaLabel={(tab, total, needsWork) =>
          `${tab.label} ${total ?? 0}${needsWork ? `, ${needsWork} needs work` : ''}`
        }
      />
    );

    expect(screen.getByTestId('demo-entity-tabs')).toBeInTheDocument();
    expect(screen.getByTestId('demo-tab-count-distributor')).toHaveTextContent('(12)');
    expect(screen.getByTestId('demo-tab-needs-work-distributor')).toHaveTextContent('3 needs work');
    expect(screen.queryByTestId('demo-tab-needs-work-customer')).not.toBeInTheDocument();

    await user.click(screen.getByTestId('tab-customer'));
    expect(onChange).toHaveBeenCalledWith('customer');
  });
});
