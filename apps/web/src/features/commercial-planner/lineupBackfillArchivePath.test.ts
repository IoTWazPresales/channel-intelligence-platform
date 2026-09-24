import { describe, expect, it } from 'vitest';

import {
  parseArchiveRelativePath,
  shouldExcludeLineupFile,
  stageLineupFilesFromList,
} from './lineupBackfillArchivePath';

// Injected as the product-lines endpoint would return them (D-g: data, not a constant).
const LINE_CODES = ['NB', 'NR', 'PF', 'XB', 'PT'];

describe('lineupBackfillArchivePath', () => {
  it('parses NB/year/quarter from tree-relative path', () => {
    const parsed = parseArchiveRelativePath('NB\\2025\\Q1\\lineup.xlsx', LINE_CODES);
    expect(parsed.folderPath).toBe('NB\\2025\\Q1');
    expect(parsed.businessUnit).toBe('NB');
  });

  it('parses irregular PF/Q2 layout', () => {
    const parsed = parseArchiveRelativePath('PF\\Q2\\spec.xlsx', LINE_CODES);
    expect(parsed.folderPath).toBe('PF\\Q2');
  });

  it('recognises any injected product-line code, e.g. PT', () => {
    const parsed = parseArchiveRelativePath('pt/2026/26Q1/lineup.xlsx', LINE_CODES);
    expect(parsed.businessUnit).toBe('pt');
    expect(parsed.folderPath).toBe('pt\\2026\\Q1');
  });

  it('does not treat a folder outside the injected codes as a BU', () => {
    const parsed = parseArchiveRelativePath('NX\\2025\\Q1\\lineup.xlsx', LINE_CODES);
    expect(parsed.businessUnit).toBeNull();
    expect(parsed.folderPath).toBe('2025\\Q1');
  });

  it('has no built-in codes: an empty list recognises no BU folder', () => {
    const parsed = parseArchiveRelativePath('NB\\2025\\Q1\\lineup.xlsx', []);
    expect(parsed.businessUnit).toBeNull();
  });

  it('excludes reference-only filenames', () => {
    expect(shouldExcludeLineupFile('Do Not Use old lineup.xlsx')).toBe(true);
  });

  it('stages only spreadsheet files from a folder list', () => {
    const file = new File(['x'], 'NB\\2025\\Q1\\lineup.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    Object.defineProperty(file, 'webkitRelativePath', {
      value: 'NB/2025/Q1/lineup.xlsx',
    });
    const readme = new File(['x'], 'readme.txt', { type: 'text/plain' });
    const staged = stageLineupFilesFromList([file, readme], LINE_CODES);
    expect(staged).toHaveLength(1);
    expect(staged[0].folderPath).toBe('NB\\2025\\Q1');
  });
});
