import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ImportStewardCandidateWorkspace } from './ImportStewardCandidateWorkspace';
import type { ImportStewardCandidateRowBase } from './importStewardCandidateWorkspace.types';

type Row = ImportStewardCandidateRowBase;

const baseRow = (id: number): Row => ({
  id,
  entity_type: 'shipment_distributor',
  normalized_key: `k-${id}`,
  row_count: 1,
  total_units: null,
  total_reported_value: null,
  sample_raw_values: ['tok'],
  status: 'open',
  match_reason: null,
  confidence_score: null,
  context: null,
});

describe('ImportStewardCandidateWorkspace', () => {
  it('renders missing job prompt when importJobId is null', () => {
    render(
      <ImportStewardCandidateWorkspace<Row>
        listDomainId="unit-test"
        importJobId={null}
        copy={{
          title: 'Candidates',
          description: 'Desc',
          missingJobPrompt: <span data-testid="missing-job">Choose a job</span>,
        }}
        openRows={[]}
        filteredRows={[]}
        isLoading={false}
        busy={false}
        columns={[{ id: 'x', header: 'X', cell: () => '—' }]}
      />
    );
    expect(screen.getByTestId('import-steward-candidate-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('missing-job')).toHaveTextContent('Choose a job');
  });

  it('renders one data row when filteredRows has items', () => {
    const r = baseRow(7);
    render(
      <ImportStewardCandidateWorkspace<Row>
        listDomainId="unit-test"
        importJobId={42}
        copy={{ title: 'T', description: 'D' }}
        openRows={[r]}
        filteredRows={[r]}
        isLoading={false}
        busy={false}
        columns={[{ id: 'id', header: 'ID', cell: (row) => String(row.id) }]}
      />
    );
    expect(screen.getByText('7')).toBeInTheDocument();
  });
});
