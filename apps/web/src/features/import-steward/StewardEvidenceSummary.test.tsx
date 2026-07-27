import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { StewardEvidenceSummary } from './StewardEvidenceSummary';
import { StewardSuggestionCards } from './StewardSuggestionCards';

describe('StewardEvidenceSummary', () => {
  it('renders empty samples and dashes for missing units/value', () => {
    render(<StewardEvidenceSummary />);
    expect(screen.getByTestId('steward-evidence-summary-samples-empty')).toHaveTextContent('—');
    expect(screen.getByTestId('steward-evidence-summary-units')).toHaveTextContent('Units —');
    expect(screen.getByTestId('steward-evidence-summary-value')).toHaveTextContent('Value —');
  });

  it('renders partial and full evidence', () => {
    render(
      <StewardEvidenceSummary
        affectedRowCount={3}
        totalUnits={12}
        totalReportedValue={99.5}
        sampleRawValues={['RAW-A', 'RAW-B']}
        extras={<span data-testid="extra-case">CASE-1</span>}
      />
    );
    expect(screen.getByTestId('steward-evidence-summary-rows')).toHaveTextContent('3 rows');
    expect(screen.getByTestId('steward-evidence-summary-units')).toHaveTextContent('Units 12');
    expect(screen.getByTestId('steward-evidence-summary-value')).toHaveTextContent('Value 99.5');
    expect(screen.getByTestId('steward-evidence-summary-samples')).toHaveTextContent('RAW-A');
    expect(screen.getByTestId('extra-case')).toBeInTheDocument();
  });
});

describe('StewardSuggestionCards', () => {
  it('shows never-auto-create empty state', () => {
    render(<StewardSuggestionCards suggestions={[]} />);
    expect(screen.getByTestId('steward-suggestion-cards-empty')).toHaveTextContent(/never auto-created/i);
  });

  it('renders ranked cards and invokes onMap', async () => {
    const user = userEvent.setup();
    const onMap = vi.fn();
    render(
      <StewardSuggestionCards
        suggestions={[
          {
            targetId: 11,
            label: 'Master A',
            score: 0.95,
            reason: 'exact',
            onMap,
          },
        ]}
        overrideSlot={<div data-testid="override-slot">search</div>}
      />
    );
    expect(screen.getByTestId('steward-suggestion-cards-item-11')).toHaveTextContent('Master A');
    await user.click(screen.getByTestId('steward-suggestion-cards-map-11'));
    expect(onMap).toHaveBeenCalledWith(11);
    expect(screen.getByTestId('override-slot')).toBeInTheDocument();
  });
});
