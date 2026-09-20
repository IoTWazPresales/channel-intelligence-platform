'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ColumnPickerDialog } from './ColumnPickerDialog';

describe('ColumnPickerDialog size=md', () => {
  const groups = [
    { label: 'Identity', fields: ['customer_code', 'customer_name'] },
    { label: 'Meta', fields: ['notes_summary'] },
  ];

  it('renders injected groups and filters by search', () => {
    const onToggle = vi.fn();
    const onSearchChange = vi.fn();
    const { rerender } = render(
      <ColumnPickerDialog
        size="md"
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

    expect(screen.getByTestId('master-column-picker')).toBeInTheDocument();
    expect(screen.getByText('Identity')).toBeInTheDocument();
    expect(screen.getByText('Customer code')).toBeInTheDocument();
    expect(screen.getByText('Notes')).toBeInTheDocument();
    expect(screen.getByText('Done')).toBeInTheDocument();
    expect(screen.queryByTestId('col-reset-defaults')).not.toBeInTheDocument();

    const search = screen.getByLabelText('Search columns');
    fireEvent.change(search, {
      target: { value: 'notes' },
    });
    expect(onSearchChange).toHaveBeenCalledWith('notes');

    rerender(
      <ColumnPickerDialog
        size="md"
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
      <ColumnPickerDialog
        size="md"
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

  it('disables toggles and shows alert when the grid is not ready', () => {
    render(
      <ColumnPickerDialog
        size="md"
        open
        onClose={vi.fn()}
        title="Manage columns"
        groups={groups}
        visibility={{ customer_code: true }}
        onToggle={vi.fn()}
        gridReady={false}
        search=""
        onSearchChange={vi.fn()}
      />
    );

    expect(
      screen.getByText('Grid is still initializing. Column toggles become available in a moment.')
    ).toBeInTheDocument();
    expect(screen.getByTestId('master-column-toggle-customer_code')).toHaveAttribute(
      'aria-disabled',
      'true'
    );
  });

  it('renders description, group captions, loading / empty-hint groups, reset and a host testid', () => {
    const onReset = vi.fn();
    render(
      <ColumnPickerDialog
        size="md"
        data-testid="host-column-picker"
        open
        onClose={vi.fn()}
        title="Additional columns"
        description="Intro copy"
        groups={[
          { label: 'Canonical', description: 'API-backed', fields: ['order_no'] },
          { label: 'Loading group', fields: [], loading: true },
          { label: 'Empty group', fields: [], emptyHint: 'Pick a job first.' },
        ]}
        columnLabelByField={{ order_no: 'Order no.' }}
        visibility={{ order_no: true }}
        onToggle={vi.fn()}
        onReset={onReset}
        gridReady
        search=""
        onSearchChange={vi.fn()}
      />
    );

    expect(screen.getByTestId('host-column-picker')).toBeInTheDocument();
    expect(screen.getByText('Intro copy')).toBeInTheDocument();
    expect(screen.getByText('API-backed')).toBeInTheDocument();
    expect(screen.getByText('Loading group')).toBeInTheDocument();
    expect(screen.getByText('Loading column names…')).toBeInTheDocument();
    expect(screen.getByText('Empty group')).toBeInTheDocument();
    expect(screen.getByText('Pick a job first.')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('host-column-picker-reset'));
    expect(onReset).toHaveBeenCalled();
  });
});

describe('ColumnPickerDialog size=wide', () => {
  const lines = [
    { product_category: 'NB', product_line: 'NB', product_form_factor: '' },
    { product_category: 'NB', product_line: '', product_form_factor: 'clamshell' },
  ];

  it('keeps locked columns, coverage, presets, reset, evidence alert, and discovered spec keys', () => {
    const onChange = vi.fn();
    const onReset = vi.fn();
    const onPreset = vi.fn();
    const onSpecKeyToggle = vi.fn();
    render(
      <ColumnPickerDialog
        size="wide"
        open
        onClose={vi.fn()}
        lines={lines}
        optionalVisible={{ product_category: true }}
        onChange={onChange}
        onReset={onReset}
        onPreset={onPreset}
        specKeyVisible={{ cpu: true }}
        onSpecKeyToggle={onSpecKeyToggle}
        columnMeta={{
          plan_id: 1,
          plan_line_count: 2,
          total_products: 2,
          catalogue: { category: 2, form_factor: 1, lifecycle_status: 0, product_line: 1, series_name: 0, business_unit: 0 },
          spec_keys: { cpu: 2, ram: 0 },
          coverage_note: 'test',
        }}
      />
    );

    expect(screen.getByText('Planner line columns')).toBeInTheDocument();
    expect(screen.getByText('2 optional on')).toBeInTheDocument();
    expect(screen.getAllByText('Locked').length).toBeGreaterThan(0);
    expect(screen.getByTestId('column-selector-evidence-note')).toBeInTheDocument();
    expect(screen.getByTestId('column-selector-discovered-specs')).toBeInTheDocument();
    expect(screen.getByText('2 / 2 populated')).toBeInTheDocument();
    expect(screen.getAllByText('1 / 2 populated').length).toBeGreaterThanOrEqual(1);

    fireEvent.click(screen.getByText('Planning'));
    expect(onPreset).toHaveBeenCalledWith('planning');

    fireEvent.click(screen.getByTestId('col-toggle-product_category'));
    expect(onChange).toHaveBeenCalledWith('product_category', false);

    fireEvent.click(screen.getByTestId('col-spec-toggle-cpu'));
    expect(onSpecKeyToggle).toHaveBeenCalledWith('cpu', false);

    fireEvent.click(screen.getByTestId('col-reset-defaults'));
    expect(onReset).toHaveBeenCalled();
  });
});
