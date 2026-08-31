import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import {
  CONFIDENCE_HIGH_THRESHOLD,
  CONFIDENCE_MEDIUM_THRESHOLD,
  confidenceBandLabel,
} from '@/features/import-steward/confidenceBand';
import {
  ShipmentPlanConfidenceBandCell,
  buildShipmentResolutionWorkspaceColumns,
} from './shipmentResolutionWorkspaceTableProps';
import type { InboundEvidenceMappingCandidateRow } from './inboundEvidenceMappingCandidateWorkspaceColumns';

describe('shipmentResolutionWorkspaceTableProps S4 — confidence bands on Plan column', () => {
  it('renders High/Medium/Low band chips from shared confidenceBand vocabulary', () => {
    const { rerender } = render(<ShipmentPlanConfidenceBandCell score={CONFIDENCE_HIGH_THRESHOLD} />);
    expect(screen.getByTestId('shipment-plan-confidence-band')).toHaveTextContent(
      confidenceBandLabel('high')
    );

    rerender(<ShipmentPlanConfidenceBandCell score={CONFIDENCE_MEDIUM_THRESHOLD} />);
    expect(screen.getByTestId('shipment-plan-confidence-band')).toHaveTextContent(
      confidenceBandLabel('medium')
    );

    rerender(<ShipmentPlanConfidenceBandCell score={0.55} />);
    expect(screen.getByTestId('shipment-plan-confidence-band')).toHaveTextContent(
      confidenceBandLabel('low')
    );
  });

  it('plan column uses band cell instead of raw score-only typography', () => {
    const sample: InboundEvidenceMappingCandidateRow = {
      id: 99,
      import_job_id: 1,
      entity_type: 'customer_dealer_token',
      normalized_key: 'token-a',
      row_count: 2,
      status: 'needs_review',
      match_reason: 'alias',
      confidence_score: 0.95,
      sample_raw_values: ['TOKEN-A'],
      suggested_action: 'map_customer',
      suggested_entity_id: null,
      suggested_distributor_code: null,
      suggested_distributor_name: null,
      suggested_customer_code: 'C1',
      suggested_customer_name: 'Customer One',
      context: null,
    };
    const cols = buildShipmentResolutionWorkspaceColumns({
      planByCandidateId: new Map([[99, { candidate_id: 99, ready: true, confidence: 0.95 }]]),
    });
    const planCol = cols.find((c) => c.id === 'plan');
    expect(planCol).toBeDefined();
    render(<>{planCol!.cell(sample)}</>);
    expect(screen.getByTestId('shipment-plan-confidence-band')).toHaveTextContent('High');
    expect(screen.getByText('0.95')).toBeInTheDocument();
    expect(screen.queryByText(/^score 0\.95$/)).not.toBeInTheDocument();
  });
});
