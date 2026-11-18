import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ShipmentSkippedSheets } from './ShipmentSkippedSheets';

describe('ShipmentSkippedSheets (BACKLOG-046)', () => {
  it('renders nothing when every sheet is imported', () => {
    const { container } = render(<ShipmentSkippedSheets sheets={[]} />);
    expect(container).toBeEmptyDOMElement();
    const { container: c2 } = render(<ShipmentSkippedSheets sheets={undefined} />);
    expect(c2).toBeEmptyDOMElement();
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
});