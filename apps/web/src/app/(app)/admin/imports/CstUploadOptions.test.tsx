import React, { useState } from 'react';
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { renderWithProviders } from '@/test-utils/renderWithProviders';

import {
  appendCstUploadOptions,
  CstUploadOptionsFields,
  EMPTY_CST_UPLOAD_OPTIONS,
  suggestYearFromNames,
  type CstUploadOptions,
} from './CstUploadOptions';

function Harness({ initial = EMPTY_CST_UPLOAD_OPTIONS }: { initial?: CstUploadOptions }) {
  const [value, setValue] = useState<CstUploadOptions>(initial);
  return (
    <>
      <CstUploadOptionsFields value={value} onChange={setValue} />
      <span data-testid="state">{JSON.stringify(value)}</span>
    </>
  );
}

const state = () => JSON.parse(screen.getByTestId('state').textContent ?? '{}') as CstUploadOptions;

describe('CstUploadOptionsFields (N-0111)', () => {
  it('sales-only and stock-only exclude each other', () => {
    renderWithProviders(<Harness />);
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sales-only file (units, no on-hand)' }));
    expect(state().salesOnly).toBe(true);
    const stock = screen.getByRole('checkbox', { name: 'Stock-only file (on-hand, no units sold)' });
    expect(stock).toHaveAccessibleDescription(/units already loaded for those weeks stay/);
    fireEvent.click(stock);
    expect(state()).toMatchObject({ salesOnly: false, stockOnly: true });
  });

  it('Year confirmed needs a valid year, and editing the year clears it', () => {
    renderWithProviders(<Harness />);
    const confirmed = screen.getByRole('checkbox', { name: 'Year confirmed' });
    expect(confirmed).toBeDisabled();
    fireEvent.change(screen.getByTestId('cst-year'), { target: { value: '2024' } });
    expect(confirmed).toBeEnabled();
    fireEvent.click(confirmed);
    expect(state()).toMatchObject({ year: '2024', yearConfirmed: true });
    fireEvent.change(screen.getByTestId('cst-year'), { target: { value: '2023' } });
    expect(state()).toMatchObject({ year: '2023', yearConfirmed: false });
  });

  it('sends the year only when confirmed', () => {
    const fd = new FormData();
    appendCstUploadOptions(fd, { salesOnly: false, stockOnly: true, year: '2024', yearConfirmed: false });
    expect(fd.get('cst_stock_only')).toBe('true');
    expect(fd.get('cst_confirmed_year')).toBeNull();
    const fd2 = new FormData();
    appendCstUploadOptions(fd2, { salesOnly: false, stockOnly: false, year: '2024', yearConfirmed: true });
    expect(fd2.get('cst_confirmed_year')).toBe('2024');
  });

  it('suggests a year from file names or folders', () => {
    expect(suggestYearFromNames(['Amazon W12.xlsx', 'History/2024/Amazon W12.xlsx'])).toBe(2024);
    expect(suggestYearFromNames(['sales_20240318.xlsx'])).toBeNull();
    expect(suggestYearFromNames(['2023.xlsx', '2024.xlsx'])).toBeNull();
  });
});
