import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ShipmentSkippedSheets } from './ShipmentSkippedSheets';

describe('ShipmentSkippedSheets (BACKLOG-046)', () => {
  it('renders nothing when every sheet is imported', () => {
    const { container } = render(<ShipmentSkippedSheets sheets={[]} />);
    expect(container).toBeEmptyDOMElement();
    const { container: c2 } = render(<ShipmentSkippedSheets sheets={undefined} />);
    expect(c2).toBeEmptyDOMElement();
    const { container: c3 } = render(<ShipmentSkippedSheets sheets={null} />);
    expect(c3).toBeEmptyDOMElement();
  });

  it('shows an Ignored badge with the reason for each skipped sheet', () => {
    render(
      <ShipmentSkippedSheets
        sheets={[
          { sheet: 'Cover', reason: 'not_selected' },
          { sheet: 'Notes', reason: 'unrecognised_layout' },
          { sheet: 'Other', reason: 'something_new' },
        ]}
      />,
    );
    const chips = screen.getAllByTestId('shipment-skipped-sheet').map((c) => c.textContent);
    expect(chips).toEqual([
      'Cover · Ignored, not selected',
      'Notes · Ignored, layout not recognised',
      'Other · Ignored, something_new',
    ]);
  });

  it('shows every unknown sheet when no selected sheet has a recognised layout', () => {
    render(
      <ShipmentSkippedSheets
        sheets={[
          { sheet: 'A', reason: 'unrecognised_layout' },
          { sheet: 'B', reason: 'unrecognised_layout' },
        ]}
      />,
    );
    const badges = screen.getAllByTestId('shipment-skipped-sheet');
    expect(badges).toHaveLength(2);
    expect(badges[0]).toHaveTextContent('A');
    expect(badges[1]).toHaveTextContent('B');
    badges.forEach((badge) => {
      expect(badge).toHaveTextContent('Ignored, layout not recognised');
    });
  });

  it('shows an unselected exception tab without implying the detector rejected its layout', () => {
    render(
      <ShipmentSkippedSheets
        sheets={[{ sheet: 'Summary', reason: 'not_selected' }]}
      />,
    );
    expect(screen.getByTestId('shipment-skipped-sheet')).toHaveTextContent(
      'Ignored, not selected',
    );
    expect(screen.queryByText(/layout not recognised/)).not.toBeInTheDocument();
  });
});
