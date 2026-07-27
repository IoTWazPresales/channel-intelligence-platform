import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { DsiProductResolutionEvidenceCard } from './DsiProductResolutionEvidenceCard';

describe('DsiProductResolutionEvidenceCard', () => {
  it('renders nothing when context is empty', () => {
    const { container } = renderWithProviders(<DsiProductResolutionEvidenceCard context={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows cross-distributor corroboration block', () => {
    renderWithProviders(
      <DsiProductResolutionEvidenceCard
        context={{
          unresolved_distributor_ids: [21, 38],
          dominant_evidence_month: '2025-06',
          shipment_cross_distributor_corroboration: {
            distinct_resolved_product_ids: [11353],
            match_count: 6,
            evidence_month: '2025-06',
            auto_resolve_blocked: true,
            summary: 'Other distributors only.',
          },
        }}
      />
    );
    expect(screen.getByTestId('dsi-product-resolution-evidence')).toBeTruthy();
    expect(screen.getByText(/Other distributors only/)).toBeTruthy();
    expect(screen.getByText(/Distributors in unresolved rows: 21, 38/)).toBeTruthy();
  });
});
