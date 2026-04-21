import { describe, expect, it } from 'vitest';

import { parseLineupImportCsv, splitCsvRecord } from './lineupImportCsv';

describe('splitCsvRecord', () => {
  it('splits simple commas', () => {
    expect(splitCsvRecord('a,b,c')).toEqual(['a', 'b', 'c']);
  });

  it('handles quoted commas and doubled quotes', () => {
    expect(splitCsvRecord('"a,b",c,"d""e"')).toEqual(['a,b', 'c', 'd"e']);
  });
});

describe('parseLineupImportCsv', () => {
  it('maps aliases and builds API rows', () => {
    const csv = [
      'Customer,period,SKU,Channel,notes',
      'ACME,2025-01-01,SKU-1,RETAIL,"hello, world"',
    ].join('\n');
    const { rows, headerErrors, parseWarnings } = parseLineupImportCsv(csv);
    expect(headerErrors).toEqual([]);
    expect(parseWarnings).toEqual([]);
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      customer_code: 'ACME',
      period_start: '2025-01-01',
      sku: 'SKU-1',
      channel_code: 'RETAIL',
      notes: 'hello, world',
    });
  });

  it('errors when required columns are missing', () => {
    const { rows, headerErrors } = parseLineupImportCsv('foo,bar\n1,2');
    expect(rows).toEqual([]);
    expect(headerErrors.length).toBeGreaterThan(0);
  });

  it('warns on short data rows', () => {
    const csv = ['customer_code,period_start,sku', 'ACME,2025-01-01,'].join('\n');
    const { rows, parseWarnings } = parseLineupImportCsv(csv);
    expect(rows).toEqual([]);
    expect(parseWarnings.some((w) => w.message.includes('non-empty'))).toBe(true);
  });
});
