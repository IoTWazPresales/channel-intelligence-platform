'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MasterColumnPickerDialog } from './MasterColumnPickerDialog';

describe('MasterColumnPickerDialog', () => {
  const groups = [
    { label: 'Identity', fields: ['customer_code', 'customer_name'] },
    { label: 'Meta', fields: ['notes_summary'] },
  ];

  it('renders injected groups and filters by search', () => {
    const onToggle = vi.fn();
    const onSearchChange = vi.fn();
    const { rerender } = render(
      <MasterColumnPickerDialog
        open
        onClose={vi.fn()}
        title="Manage columns"
        groups={groups}
        columnLabelByField={{
          customer_code: 'Customer code',
          customer_name: 'Customer name',
          notes_summary: 'Notes',
        }}
        visibility={{ customer_code: true, customer_name: false, notes_summary: true }}
        onToggle={onToggle}
        gridReady
        search=""
        onSearchChange={onSearchChange}
      />
    );

    expect(screen.getByText('Identity')).toBeInTheDocument();
    expect(screen.getByText('Customer code')).toBeInTheDocument();
    expect(screen.getByText('Notes')).toBeInTheDocument();

    const search = screen.getByLabelText('Search columns');
    fireEvent.change(search, {
      target: { value: 'notes' },
    });
    expect(onSearchChange).toHaveBeenCalledWith('notes');

    rerender(
      <MasterColumnPickerDialog
        open
        onClose={vi.fn()}
        title="Manage columns"
        groups={groups}
        columnLabelByField={{
          customer_code: 'Customer code',
          customer_name: 'Customer name',
          notes_summary: 'Notes',
        }}
        visibility={{ customer_code: true, customer_name: false, notes_summary: true }}
        onToggle={onToggle}
        gridReady
        search="notes"
        onSearchChange={onSearchChange}
      />
    );

    expect(screen.queryByText('Customer code')).not.toBeInTheDocument();
    expect(screen.getByText('Notes')).toBeInTheDocument();
  });

  it('toggles visibility via checkbox callback', () => {
    const onToggle = vi.fn();
    render(
      <MasterColumnPickerDialog
        open
        onClose={vi.fn()}
        title="Manage columns"
        groups={groups}
        columnLabelByField={{ customer_code: 'Customer code', customer_name: 'Customer name' }}
        visibility={{ customer_code: true, customer_name: false }}
        onToggle={onToggle}
        gridReady
        search=""
        onSearchChange={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId('master-column-toggle-customer_name'));
    expect(onToggle).toHaveBeenCalledWith('customer_name', true);
  });
});
