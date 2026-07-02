import { describe, expect, it } from 'vitest';

import {
  parseArchiveRelativePath,
  shouldExcludeLineupFile,
  stageLineupFilesFromList,
} from './lineupBackfillArchivePath';

describe('lineupBackfillArchivePath', () => {
  it('parses NB/year/quarter from tree-relative path', () => {
    const parsed = parseArchiveRelativePath('NB\\2025\\Q1\\lineup.xlsx');
    expect(parsed.folderPath).toBe('NB\\2025\\Q1');
    expect(parsed.businessUnit).toBe('NB');
  });

  it('parses irregular PF/Q2 layout', () => {
    const parsed = parseArchiveRelativePath('PF\\Q2\\spec.xlsx');
    expect(parsed.folderPath).toBe('PF\\Q2');
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
    const staged = stageLineupFilesFromList([file, readme]);
    expect(staged).toHaveLength(1);
    expect(staged[0].folderPath).toBe('NB\\2025\\Q1');
  });
});
