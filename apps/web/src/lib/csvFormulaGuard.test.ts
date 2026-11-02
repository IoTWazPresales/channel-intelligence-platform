import { describe, expect, it } from 'vitest';

import { dsiProductCandidateExportToCsv, type DsiProductCandidateExportRow } from '@/app/(app)/admin/imports/dsi/dsiProductCandidateExport';
import { visibleFilteredCsvParams } from '@/features/workbench-ui/gridFind';

import { guardFormulaText, guardedCsvCell } from './csvFormulaGuard';

describe('CSV formula guard (GOV-008 minor: every exporter)', () => {
  it('guards every formula lead character and leaves ordinary text alone', () => {
    for (const s of ['=1+1', '+1', '-1', '@SUM(A1)', '\tx', '\rx', '=HYPERLINK("x")']) {
      expect(guardFormulaText(s)).toBe(`'${s}`);
    }
    expect(guardFormulaText('Makro')).toBe('Makro');
    expect(guardFormulaText('')).toBe('');
  });

  it('AG Grid cell callback: text is guarded, numbers and formatted numbers are not', () => {
    expect(guardedCsvCell({ value: '=cmd|x' })).toBe("'=cmd|x");
    expect(guardedCsvCell({ value: -12.5 })).toBe('-12.5'); // a negative number stays a number
    expect(guardedCsvCell({ value: -12.5, formatValue: (v) => `${v} units` })).toBe('-12.5 units');
    expect(guardedCsvCell({ value: '+27 11', formatValue: (v) => String(v) })).toBe("'+27 11");
    expect(guardedCsvCell({ value: null })).toBe('');
  });

  it('the shared grid export parameters carry the guard (every fact grid export)', () => {
    expect(visibleFilteredCsvParams('roadmap', ['sku']).processCellCallback).toBe(guardedCsvCell);
  });

  it('the DSI product candidate export guards a token that starts like a formula', () => {
    const row: DsiProductCandidateExportRow = {
      token: '=HYPERLINK("http://x")', rows: 1, units: -3, value: '', resolved_receipt_temporal: '', indeterminate: '',
      ignored: 0, reason_code: '', distributors: '', dominant_month: '',
    };
    const csv = dsiProductCandidateExportToCsv([row]).split('\r\n');
    expect(csv[1].startsWith('"\'=HYPERLINK(""http://x"")",1,-3,')).toBe(true);
  });
});
