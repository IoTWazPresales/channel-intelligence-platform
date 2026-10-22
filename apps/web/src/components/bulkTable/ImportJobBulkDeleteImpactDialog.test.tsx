import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import {
  IMPORT_JOB_DELETE_MAX,
  ImportJobBulkDeleteImpactDialog,
  parseJobIds,
  type ImportJobBulkDeletePreview,
} from './ImportJobBulkDeleteImpactDialog';

const basePreview: ImportJobBulkDeletePreview = {
  job_ids: [10, 11],
  missing_job_ids: [],
  jobs: [
    {
      id: 10,
      file_name: 'Asus Sales and Inventory - synthetic.xlsx',
      counts: { fact_sales_sellout_rows_removed: 8, fact_returns_rows_removed: 3, dsi_staging_rows: 11 },
    },
    { id: 11, file_name: 'history.xlsx', counts: { sellthrough_figures_restored: 2, cst_staging_rows: 1 } },
  ],
  counts: {
    import_jobs: 2,
    import_jobs_requested: 2,
    import_jobs_missing: 0,
    fact_sales_sellout_rows_removed: 8,
    fact_returns_rows_removed: 3,
    sellthrough_figures_restored: 2,
  },
  risky: { customer_source_token_aliases: 0, distributor_source_token_aliases: 0 },
  recomputed: { customers: 1, distributors: 1 },
  storage_keys_total: 1,
  storage_keys_sample: ['imports/test/x.csv'],
};

function renderDialog(props: Partial<Parameters<typeof ImportJobBulkDeleteImpactDialog>[0]> = {}) {
  return render(
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
      {...props}
    />
  );
}

describe('ImportJobBulkDeleteImpactDialog', () => {
  it('blocks confirm until acknowledged', () => {
    renderDialog();
    expect(screen.getByTestId('import-job-bulk-delete-dialog')).toBeVisible();
    expect(screen.getByText(/Delete import jobs — impact preview/i)).toBeInTheDocument();
    expect(screen.getByTestId('confirm-delete')).toBeDisabled();
  });

  it('lists plain counts per job', () => {
    renderDialog();
    const perJob = screen.getByTestId('per-job-counts');
    expect(perJob).toHaveTextContent('Job 10 — Asus Sales and Inventory - synthetic.xlsx');
    expect(perJob).toHaveTextContent('Distributor sales lines removed: 8');
    expect(perJob).toHaveTextContent('Distributor returns lines removed: 3');
    expect(perJob).toHaveTextContent('Sell-through figures brought back from the earlier load: 2');
    expect(screen.getByText(/stock positions are recomputed for 1 customer,/i)).toBeInTheDocument();
  });

  it('enables confirm when acknowledged', () => {
    renderDialog({ impactAcknowledged: true });
    expect(screen.getByTestId('confirm-delete')).not.toBeDisabled();
  });

  it('keeps learned aliases by default and does not block on them', async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    renderDialog({
      preview: { ...basePreview, risky: { customer_source_token_aliases: 2, distributor_source_token_aliases: 0 } },
      impactAcknowledged: true,
      onConfirm,
    });
    expect(screen.getByTestId('risky-artifacts-alert')).toHaveTextContent('2 learned aliases came from these jobs. They are kept');
    expect(screen.getByTestId('delete-semantic-checkbox')).not.toBeChecked();
    await user.click(screen.getByTestId('confirm-delete'));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('says when a later load has replaced the figures', () => {
    renderDialog({ preview: { ...basePreview, counts: { ...basePreview.counts, fact_sales_sellout_kept_later: 4 } } });
    expect(screen.getByTestId('kept-later-alert')).toHaveTextContent('The later figures stay');
  });

  it('blocks confirm when an id does not exist', () => {
    renderDialog({ preview: { ...basePreview, missing_job_ids: [99] }, impactAcknowledged: true });
    expect(screen.getByText(/These job ids do not exist: 99/)).toBeInTheDocument();
    expect(screen.getByTestId('confirm-delete')).toBeDisabled();
  });

  it('previews jobs typed by id', async () => {
    const user = userEvent.setup();
    const onPreviewIds = vi.fn();
    renderDialog({ preview: null, onPreviewIds });
    const button = screen.getByTestId('preview-job-ids');
    expect(button).toBeDisabled();
    await user.type(screen.getByLabelText('Job ids to delete'), '1164, 1184{enter}1199 1184');
    expect(screen.getByText(/3 job ids\./)).toBeInTheDocument();
    await user.click(button);
    expect(onPreviewIds).toHaveBeenCalledWith([1164, 1184, 1199]);
  });

  it('refuses more than 200 ids at a time', async () => {
    const user = userEvent.setup();
    renderDialog({ preview: null, onPreviewIds: vi.fn() });
    const ids = Array.from({ length: 201 }, (_, i) => i + 1).join(',');
    await user.click(screen.getByLabelText('Job ids to delete'));
    await user.paste(ids);
    expect(screen.getByText(/201 ids: preview up to 200 at a time/)).toBeInTheDocument();
    expect(screen.getByTestId('preview-job-ids')).toBeDisabled();
  });
});

describe('parseJobIds', () => {
  it('reads ids in any separator and drops repeats', () => {
    expect(parseJobIds('1164,1184\n1199  1184; x 0')).toEqual([1164, 1184, 1199]);
    expect(parseJobIds('')).toEqual([]);
  });

  it('expands ranges written with a hyphen or any dash, mixed with single ids', () => {
    expect(parseJobIds('1230-1234')).toEqual([1230, 1231, 1232, 1233, 1234]);
    expect(parseJobIds('1230–1232, 1240 — 1241\n1250−1251\n1260‑1261‐1262')).toEqual([
      1230, 1231, 1232, 1240, 1241, 1250, 1251, 1260, 1261, 1262,
    ]);
    expect(parseJobIds('1100 1230 - 1231 1500')).toEqual([1100, 1230, 1231, 1500]);
  });

  it('reads a backwards range, drops overlaps, and keeps ids above zero', () => {
    expect(parseJobIds('1234-1232, 1231-1233')).toEqual([1232, 1233, 1234, 1231]);
    expect(parseJobIds('0-2')).toEqual([1, 2]);
  });

  it('does not hang on a huge range: it stops expanding, and the box refuses it as too many', () => {
    const ids = parseJobIds('1-999999999');
    expect(ids.length).toBeGreaterThan(IMPORT_JOB_DELETE_MAX);
    expect(ids.length).toBeLessThanOrEqual(10_000);
  });
});
