import { describe, expect, it } from 'vitest';

import { readSavedFindViews } from './gridFind';

describe('readSavedFindViews', () => {
  it('keeps named find strings and drops All and junk', () => {
    const raw = JSON.stringify([
      { name: 'Takealot', find: 'takealot' },
      { name: 'All', find: 'nope' },
      { name: '', find: 'x' },
      { name: 'Empty ok', find: '' },
      { find: 'missing name' },
      'nope',
    ]);
    expect(readSavedFindViews(raw)).toEqual([
      { name: 'Takealot', find: 'takealot' },
      { name: 'Empty ok', find: '' },
    ]);
  });

  it('returns nothing for empty or broken storage', () => {
    expect(readSavedFindViews(null)).toEqual([]);
    expect(readSavedFindViews('not json')).toEqual([]);
    expect(readSavedFindViews('{"name":"x"}')).toEqual([]);
  });
});
