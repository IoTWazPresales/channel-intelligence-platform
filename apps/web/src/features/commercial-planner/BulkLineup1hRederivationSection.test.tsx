import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import {
  BulkLineup1hRederivationSection,
  type RederivationCollisionGroup,
  type RederivationProposal,
} from './BulkLineup1hRederivationSection';

const allDoneProposals: RederivationProposal[] = [
  {
    proposal_key: 'rederive:16',
    source_case_id: 16,
    file_name: 'PF 1H.xlsx',
    q1_adjustment: { planned_units_before: 1000, planned_units_after: 500, po_link_count: 2, already_allocated: true },
  },
  {
    proposal_key: 'rederive:35',
    source_case_id: 35,
    file_name: 'NB 1H.xlsx',
    q1_adjustment: { planned_units_before: 800, planned_units_after: 400, po_link_count: 1, already_allocated: true },
  },
];

const resolvedCollision: RederivationCollisionGroup = {
  supersession_group_key: '2026Q2|NB',
  winner_proposal_key: 'existing:9',
  winner_member_key: 'existing:9',
  members: [
    { member_key: 'existing:9', kind: 'existing_case', case_id: 9, filename: 'NB Q2.xlsx', business_unit: 'NB' },
    {
      member_key: 'rederive:35:q2',
      kind: 'proposed_q2_twin',
      filename: 'NB 1H.xlsx',
      business_unit: 'NB',
    },
  ],
};

describe('BulkLineup1hRederivationSection', () => {
  it('shows done banner and hides apply controls when all eligible cases are re-derived', () => {
    render(
      <BulkLineup1hRederivationSection
        preview={{
          rederivation_proposals: allDoneProposals,
          supersession_collisions: [resolvedCollision],
          totals: { eligible_cases: 2, collision_groups: 1 },
        }}
        collisionWinners={{ '2026Q2|NB': 'existing:9' }}
        onCollisionWinnerChange={vi.fn()}
        applyNotice={null}
        onDismissApplyNotice={vi.fn()}
        previewError={null}
        applyError={null}
        onPreview={vi.fn()}
        previewPending={false}
        confirmRederivation={false}
        onConfirmRederivationChange={vi.fn()}
        onApply={vi.fn()}
        applyPending={false}
        canApply={false}
      />,
    );

    expect(screen.getByTestId('rederivation-all-done-banner')).toHaveTextContent('All 2 eligible 1H cases re-derived');
    expect(screen.queryByTestId('rederivation-apply-button')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Confirm re-derivation apply/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('collision-resolved-2026Q2|NB')).toHaveTextContent('Existing case #9');
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });
});
