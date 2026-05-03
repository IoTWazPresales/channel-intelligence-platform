import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ImportJobBulkDeleteImpactDialog, type ImportJobBulkDeletePreview } from './ImportJobBulkDeleteImpactDialog';

const basePreview: ImportJobBulkDeletePreview = {
  job_ids: [10, 11],
  missing_job_ids: [],
  counts: {
    import_jobs: 2,
    import_jobs_requested: 2,
    import_jobs_missing: 0,
    raw_file_metadata_rows: 1,
    import_row_result_rows: 3,
    dsi_staging_rows: 4,
    dsi_mapping_candidate_rows: 1,
    fact_sales_sellout_rows: 2,
    fact_inventory_distributor_rows: 1,
    entity_mapping_queue_rows: 0,
    historical_lineup_header_rows: 0,
    historical_lineup_line_rows: 0,
    commercial_lineup_case_rows: 0,
    catalog_products_pointing_at_jobs: 0,
    fact_competitor_price_rows: 0,
  },
  risky: { customer_source_token_aliases: 0, distributor_source_token_aliases: 0 },
  storage_keys_total: 1,
  storage_keys_sample: ['imports/test/x.csv'],
};

describe('ImportJobBulkDeleteImpactDialog', () => {
  it('blocks confirm until acknowledged', () => {
    render(
      <ImportJobBulkDeleteImpactDialog
        open
        busy={false}
        preview={basePreview}
        deleteSemanticArtifacts={false}
        onDeleteSemanticArtifactsChange={vi.fn()}
        impactAcknowledged={false}
        onImpactAcknowledgedChange={vi.fn()}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByTestId('import-job-bulk-delete-dialog')).toBeVisible();
    expect(screen.getByText(/Delete import jobs — impact preview/i)).toBeInTheDocument();
    expect(screen.getByTestId('confirm-delete')).toBeDisabled();
  });

  it('enables confirm when acknowledged and no alias block', () => {
    render(
      <ImportJobBulkDeleteImpactDialog
        open
        busy={false}
        preview={basePreview}
        deleteSemanticArtifacts={false}
        onDeleteSemanticArtifactsChange={vi.fn()}
        impactAcknowledged
        onImpactAcknowledgedChange={vi.fn()}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByTestId('confirm-delete')).not.toBeDisabled();
  });

  it('requires semantic opt-in when aliases exist', () => {
    const preview: ImportJobBulkDeletePreview = {
      ...basePreview,
      risky: { customer_source_token_aliases: 2, distributor_source_token_aliases: 0 },
    };
    render(
      <ImportJobBulkDeleteImpactDialog
        open
        busy={false}
        preview={preview}
        deleteSemanticArtifacts={false}
        onDeleteSemanticArtifactsChange={vi.fn()}
        impactAcknowledged
        onImpactAcknowledgedChange={vi.fn()}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
      />
    );
    expect(screen.getByTestId('confirm-delete')).toBeDisabled();
  });

  it('allows confirm when aliases cleared via opt-in and acknowledged', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const preview: ImportJobBulkDeletePreview = {
      ...basePreview,
      risky: { customer_source_token_aliases: 1, distributor_source_token_aliases: 0 },
    };
    render(
      <ImportJobBulkDeleteImpactDialog
        open
        busy={false}
        preview={preview}
        deleteSemanticArtifacts
        onDeleteSemanticArtifactsChange={vi.fn()}
        impactAcknowledged
        onImpactAcknowledgedChange={vi.fn()}
        onClose={vi.fn()}
        onConfirm={onConfirm}
      />
    );
    const confirm = screen.getByTestId('confirm-delete');
    expect(confirm).not.toBeDisabled();
    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
