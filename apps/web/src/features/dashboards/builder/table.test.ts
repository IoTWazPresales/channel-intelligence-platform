import { describe, expect, it } from 'vitest';

import { v1Csv } from '../DashboardWidgetCard';
import { exportFileName, exportToast, guardCell, headerWithUnit, matchRule, quoteCell, ruleMatches, ruleText, tableCols, toCsv } from './table';
import type { ColourRule, V2Response } from './types';

const resp: V2Response = {
  ok: true,
  columns: [
    { id: 'customer', kind: 'breakdown', label: 'Customer', fields: ['customer_id', 'customer_name'] },
    { id: 'period', kind: 'breakdown', label: 'Period', fields: ['bucket_key', 'bucket_start', 'bucket_end'] },
    { id: 'site_label', kind: 'breakdown', label: 'Store / site', fields: ['site_label'] },
    { id: 'cst_sellthrough.units', kind: 'measure', label: 'Sell-through units', fields: ['cst_sellthrough.units'], unit: 'units' },
    { id: 'cpor.support_usd', kind: 'measure', label: 'Support USD', fields: ['cpor.support_usd'], unit: 'usd' },
  ],
  rows: [
    { customer_id: 101, customer_name: 'Kestrel Home Stores', bucket_key: '2026-W28', bucket_start: '2026-07-06', bucket_end: '2026-07-12', site_label: 'Rosebank', 'cst_sellthrough.units': 1234, 'cpor.support_usd': 1500.5 },
    { customer_id: 102, customer_name: 'Marula "Main", Ltd', bucket_key: '2026-W29', site_label: '=HYPERLINK("x")', 'cst_sellthrough.units': null, 'cpor.support_usd': -3 },
    { customer_id: null, customer_name: null, bucket_key: '2026-W30', site_label: null, 'cst_sellthrough.units': 7, 'cpor.support_usd': 0 },
  ],
  totals: {},
  truncated: false,
  refusals: [],
};

describe('table columns', () => {
  it('entity columns read the name field only, with units in measure headers', () => {
    const cols = tableCols(resp);
    expect(cols.map((c) => c.field)).toEqual(['customer_name', 'bucket_key', 'site_label', 'cst_sellthrough.units', 'cpor.support_usd']);
    expect(cols.find((c) => c.id === 'customer')?.kind).toBe('entity');
    expect(cols.find((c) => c.id === 'cst_sellthrough.units')?.header).toBe('Sell-through units (units)');
    expect(cols.find((c) => c.id === 'cpor.support_usd')?.header).toMatch(/^Support USD \(.+\)$/);
    expect(headerWithUnit('Lines', undefined)).toBe('Lines');
  });
});

describe('CSV export', () => {
  const csv = toCsv(tableCols(resp), resp.rows);
  const lines = csv.slice(1).split('\r\n');

  it('starts with a UTF-8 BOM and ends rows with CRLF', () => {
    expect(csv.charCodeAt(0)).toBe(0xfeff);
    expect(csv.endsWith('\r\n')).toBe(true);
    expect(lines).toHaveLength(5); // header + 3 rows + trailing empty
  });

  it('has names, never ids, and unit headers', () => {
    expect(lines[0]).toBe('Customer,Period,Store / site,Sell-through units (units),' + quoteCell(tableCols(resp)[4].header));
    expect(lines[1]).toBe('Kestrel Home Stores,2026-W28,Rosebank,1234,1500.5');
    expect(csv).not.toMatch(/,101,|^101,/m);
    expect(lines[3]).toBe('Unassigned,2026-W30,Unassigned,7,0');
  });

  it('quotes per RFC 4180 and guards formula cells; numbers stay numbers (negative too)', () => {
    expect(lines[2]).toBe(`"Marula ""Main"", Ltd",2026-W29,"'=HYPERLINK(""x"")",,-3`);
  });

  it('guards every formula lead character', () => {
    for (const s of ['=1+1', '+1', '-1', '@SUM(A1)', '\tx', '\rx']) expect(guardCell(s).startsWith("'")).toBe(true);
    expect(guardCell('Makro')).toBe('Makro');
    expect(quoteCell('a\nb')).toBe('"a\nb"');
  });

  it('v1 CSV uses the same rules', () => {
    const out = v1Csv([{ customer_id: 3, customer_name: '-Takealot', value: 12 }]);
    expect(out.charCodeAt(0)).toBe(0xfeff);
    expect(out).toContain("'-Takealot");
    expect(out).not.toMatch(/(^|,)3(,|\r)/m);
  });

  it('file name and toast', () => {
    expect(exportFileName('Channel stock board', 'Units / week: Makro', 'csv', new Date(2026, 9, 23))).toBe('Channel-stock-board-Units-week-Makro-2026-10-23.csv');
    expect(exportToast(500, 1678, true)).toBe('Exported 500 rows (first 500 of 1,678)');
    expect(exportToast(12, 12, false)).toBe('Exported 12 rows');
  });
});

describe('conditional colour', () => {
  const rules: ColourRule[] = [
    { measure: 'u', op: '<', value: 1, tone: 'warn' },
    { measure: 'u', op: '>=', value: 20, tone: 'good' },
    { measure: 's', op: 'between', value: 10, value2: 0, tone: 'bad' },
    { measure: 'u', op: '<', value: 100, tone: 'bad' }, // a fourth rule is ignored
  ];

  it('evaluates each operator; null never matches', () => {
    expect(ruleMatches({ measure: 'u', op: '<=', value: 5, tone: 'warn' }, 5)).toBe(true);
    expect(ruleMatches({ measure: 'u', op: '>', value: 5, tone: 'warn' }, 5)).toBe(false);
    expect(ruleMatches(rules[2], 0)).toBe(true);
    expect(ruleMatches(rules[2], 10)).toBe(true);
    expect(ruleMatches(rules[2], 10.1)).toBe(false);
    expect(ruleMatches(rules[0], null)).toBe(false);
  });

  it('first matching rule for that measure wins; at most three rules', () => {
    expect(matchRule(rules, 'u', 0.5)?.tone).toBe('warn');
    expect(matchRule(rules, 'u', 25)?.tone).toBe('good');
    expect(matchRule(rules, 'u', 50)?.tone).toBe('good');
    expect(matchRule(rules, 'u', 5)).toBeNull(); // only the ignored fourth rule would match
    expect(matchRule(rules, 's', 4)?.tone).toBe('bad');
    expect(matchRule(undefined, 'u', 1)).toBeNull();
  });

  it('text marker read with the value (colour is not the only signal)', () => {
    expect(ruleText(rules[0])).toBe('Warning: below 1');
    expect(ruleText(rules[1])).toBe('Good: at or above 20');
    expect(ruleText(rules[2])).toBe('Problem: between 10 to 0');
  });
});
