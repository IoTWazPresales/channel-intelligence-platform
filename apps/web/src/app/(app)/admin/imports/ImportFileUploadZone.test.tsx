import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ImportFileUploadZone } from './ImportFileUploadZone';

describe('ImportFileUploadZone', () => {
  it('shows compact strip when a job is bound and not expanded', () => {
    render(
      <ImportFileUploadZone
        boundJobId={40}
        boundJobFileName="shipments.xlsx"
        boundJobStage="shipment_mapping_ready"
        expanded={false}
        onExpandedChange={vi.fn()}
        canUpload
        onFile={vi.fn()}
        testIdPrefix="test-upload"
      />
    );
    expect(screen.getByTestId('test-upload-compact')).toBeTruthy();
    expect(screen.queryByTestId('test-upload-dropzone')).toBeNull();
    expect(screen.getByText(/Job/)).toBeTruthy();
    expect(screen.getByText('shipments.xlsx')).toBeTruthy();
  });

  it('expands dropzone when Upload different file is clicked', () => {
    const onExpandedChange = vi.fn();
    render(
      <ImportFileUploadZone
        boundJobId={40}
        expanded={false}
        onExpandedChange={onExpandedChange}
        canUpload
        onFile={vi.fn()}
        testIdPrefix="test-upload"
      />
    );
    fireEvent.click(screen.getByTestId('test-upload-replace-btn'));
    expect(onExpandedChange).toHaveBeenCalledWith(true);
  });

  it('shows full dropzone when no job is bound', () => {
    render(
      <ImportFileUploadZone
        boundJobId={null}
        expanded={false}
        onExpandedChange={vi.fn()}
        canUpload
        onFile={vi.fn()}
        testIdPrefix="test-upload"
      />
    );
    expect(screen.getByTestId('test-upload-dropzone')).toBeTruthy();
    expect(screen.getByText('Drop CSV or XLSX here')).toBeTruthy();
  });
});
