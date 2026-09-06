import React from 'react';
import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { renderWithProviders } from '@/test-utils/renderWithProviders';

import { FundingPointerLens } from './FundingPointerLens';

describe('FundingPointerLens', () => {
  it('renders a single empty-state pointer with Import Center CTA', () => {
    renderWithProviders(
      <FundingPointerLens
        testId="funding-claims"
        title="Claim evidence is matched per case"
        description="Open the import job to finish stewarding."
        primary={{ label: 'Open Import Center', href: '/admin/imports?template=cpor_claim_evidence' }}
      />,
    );
    expect(screen.getByTestId('funding-claims')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Import Center' })).toHaveAttribute(
      'href',
      '/admin/imports?template=cpor_claim_evidence',
    );
    expect(screen.queryByRole('grid')).toBeNull();
  });
});
