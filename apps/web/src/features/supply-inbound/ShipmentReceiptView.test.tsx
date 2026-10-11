import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ShipmentReceiptView, type ShipmentReceipt } from './ShipmentReceiptView';

const receipt: ShipmentReceipt = {
  id: 9,
  group: 'delivery',
  title: 'Delivery D1',
  pod_recorded: false,
  pod_date: null,
  est_pod_date: '2026-10-01',
  lines: [
    {
      id: 9,
      order_no: '100',
      order_line: '1',
      delivery_no: 'D1',
      item_code: 'SKU',
      sales_model_name: null,
      product_sku: 'SKU',
      quantity: 4,
      line_state: 'shipped',
      pod_date: null,
    },
  ],
  events: [],
};

describe('ShipmentReceiptView', () => {
  it('shows the delivery, no proof of delivery, the line, and an empty timeline', () => {
    render(<ShipmentReceiptView receipt={receipt} />);
    expect(screen.getByTestId('shipment-receipt')).toHaveTextContent('Delivery D1');
    expect(screen.getByTestId('shipment-receipt-pod')).toHaveTextContent('No proof of delivery');
    expect(screen.getByTestId('shipment-receipt-pod')).toHaveTextContent('Expected 2026-10-01');
    expect(screen.getByTestId('shipment-receipt-lines')).toHaveTextContent('SKU');
    expect(screen.getByTestId('shipment-receipt-timeline')).toHaveTextContent(
      'No changes recorded for this shipment',
    );
  });

  it('names a cancelled candidate on the line and the timeline', () => {
    render(
      <ShipmentReceiptView
        receipt={{
          ...receipt,
          lines: [{ ...receipt.lines[0], cancelled_candidate: true }],
          events: [
            {
              event_type: 'cancelled_candidate',
              valid_from: '2026-10-02T08:00:00',
              details: { item_code: 'SKU' },
            },
          ],
        }}
      />,
    );
    expect(screen.getByTestId('shipment-receipt-lines')).toHaveTextContent('Cancelled candidate');
    expect(screen.getByTestId('shipment-receipt-timeline')).toHaveTextContent(
      'missing from the latest report',
    );
  });
});
