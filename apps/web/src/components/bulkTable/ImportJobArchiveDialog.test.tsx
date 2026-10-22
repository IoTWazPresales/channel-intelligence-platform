import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ImportJobArchiveDialog, type ImportJobArchivePreview } from './ImportJobArchiveDialog';

const preview: ImportJobArchivePreview = {
  action: 'archive',
  job_ids: [40, 41],
  missing_job_ids: [],
  jobs: [
    {
      id: 40,
      file_name: 'ACZA Shipped Unshipped.xlsx',
      template_slug: 'inbound_shipments',
      status: 'failed',
      stage: 'failed',
      created_at: '2026-07-18T10:00:00+02:00',
      archived_at: null,
      will_change: true,
    },
    {
      id: 41,
      file_name: 'Asus Week 33.xlsx',
      template_slug: 'customer_sell_through',
      status: 'completed',
      stage: 'validated',
      created_at: '2026-08-09T10:00:00+02:00',
      archived_at: '2026-10-20T08:00:00+02:00',
      will_change: false,
    },
  ],
  to_change: 1,
  unchanged: 1,
};

function renderDialog(props: Partial<Parameters<typeof ImportJobArchiveDialog>[0]> = {}) {
  const handlers = { onPreviewIds: vi.fn(), onClose: vi.fn(), onConfirm: vi.fn() };
  render(<ImportJobArchiveDialog open action="archive" busy={false} preview={null} {...handlers} {...props} />);
  return handlers;
}

describe('ImportJobArchiveDialog (N-0113)', () => {
  it('previews the ids typed or pasted', async () => {
    const user = userEvent.setup();
    const { onPreviewIds } = renderDialog();
    await user.type(screen.getByLabelText('Job ids to archive'), '1641, 1642\n1650');
    await user.click(screen.getByTestId('preview-archive-job-ids'));
    expect(onPreviewIds).toHaveBeenCalledWith([1641, 1642, 1650]);
    expect(screen.getByTestId('confirm-archive')).toBeDisabled();
  });

  it('previews a typed range, with either dash, as every id in it', async () => {
    const user = userEvent.setup();
    const { onPreviewIds } = renderDialog();
    await user.type(screen.getByLabelText('Job ids to archive'), '1230-1232, 1240–1241');
    expect(screen.getByText(/5 job ids/)).toBeInTheDocument();
    await user.click(screen.getByTestId('preview-archive-job-ids'));
    expect(onPreviewIds).toHaveBeenCalledWith([1230, 1231, 1232, 1240, 1241]);
  });

  it('starts from the ids selected in the grid', () => {
    renderDialog({ initialIds: [7, 8] });
    expect(screen.getByLabelText('Job ids to archive')).toHaveValue('7, 8');
  });

  it('shows each job with its status and only counts the jobs that change', async () => {
    const user = userEvent.setup();
    const { onConfirm } = renderDialog({ preview });
    expect(screen.getByText('Job 40 — ACZA Shipped Unshipped.xlsx')).toBeInTheDocument();
    expect(screen.getByText(/inbound_shipments · failed \/ failed · 2026-07-18/)).toBeInTheDocument();
    expect(screen.getByText(/archived 2026-10-20 · already archived/)).toBeInTheDocument();
    expect(screen.getByTestId('archive-summary')).toHaveTextContent(
      '1 job will be archived; 1 is already archived and stays as it is.',
    );
    const confirm = screen.getByTestId('confirm-archive');
    expect(confirm).toHaveTextContent('Archive 1 job');
    await user.click(confirm);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('refuses to confirm while an id does not exist, or when nothing would change', () => {
    renderDialog({ preview: { ...preview, missing_job_ids: [99999] } });
    expect(screen.getByText(/These job ids do not exist: 99999/)).toBeInTheDocument();
    expect(screen.getByTestId('confirm-archive')).toBeDisabled();
  });

  it('confirm is off when every job is already in the asked state', () => {
    renderDialog({ preview: { ...preview, to_change: 0, unchanged: 2 } });
    expect(screen.getByTestId('confirm-archive')).toBeDisabled();
  });

  it('words unarchive as unarchive', () => {
    renderDialog({
      action: 'unarchive',
      preview: { ...preview, action: 'unarchive', jobs: [{ ...preview.jobs[1], will_change: true }], to_change: 1, unchanged: 0 },
    });
    expect(screen.getByText('Unarchive import jobs')).toBeInTheDocument();
    expect(screen.getByLabelText('Job ids to unarchive')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-archive')).toHaveTextContent('Unarchive 1 job');
  });
});
