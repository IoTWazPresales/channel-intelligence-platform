import { describe, expect, it } from 'vitest';
import { ambiguousHeaders, applySelections, normalizeHeader, selectionProblems, selectionsFor } from './calendarMapping';

// Same cases as NORMALISE_CASES in apps/api/tests/unit/test_customer_calendar_headers.py: the web
// editor and the API parser must agree on what counts as the same header.
const NORMALISE_CASES: [unknown, string][] = [
  ['Start', 'start'], ['  Event   NAME ', 'event name'], ['START DATE', 'start date'],
  ['End\tDate', 'end date'], ['', ''], [null, ''], [undefined, ''],
];

describe('normalizeHeader', () => {
  it.each(NORMALISE_CASES)('%j -> %j', (raw, want) => expect(normalizeHeader(raw)).toBe(want));
});

describe('selectionsFor', () => {
  it('shows a saved alias against a differently cased and spaced header', () => {
    expect(selectionsFor({ name: ['name'], start_date: ['New Start'] }, ['Name', '  new   START ']))
      .toEqual({ Name: 'name', '  new   START ': 'start_date' });
  });
  it('mirrors the parser: first alias wins, and a column already taken drops the later field', () => {
    expect(selectionsFor({ name: ['Title'], start_date: ['Title', 'Start'] }, ['Title', 'Start']))
      .toEqual({ Title: 'name' });
    expect(selectionsFor({ name: ['Title'], start_date: ['Begins', 'Start'] }, ['Title', 'Start']))
      .toEqual({ Title: 'name', Start: 'start_date' });
  });
});

describe('applySelections (editor -> saved mapping -> parser round trip)', () => {
  const headers = ['Name', 'start', 'New Start'];

  it('selecting a different column replaces an alias that differs only by case (review B1)', () => {
    const map = { name: ['Name'], start_date: ['Start'] };
    const next = { Name: 'name', 'New Start': 'start_date' };
    const saved = applySelections(map, headers, next);
    expect(saved.start_date).toEqual(['New Start']);
    expect(selectionsFor(saved, headers)).toEqual(next);
  });

  it('drops aliases that match a file header however it is cased or spaced', () => {
    const saved = applySelections({ name: [' NAME '], start_date: ['Start Date'] }, ['name', 'Begins'], { name: 'name', Begins: 'start_date' });
    expect(saved).toEqual({ name: ['name'], start_date: ['Start Date', 'Begins'] });
  });

  it('keeps aliases for other files that do not match this file', () => {
    const saved = applySelections({ name: ['Name'], start_date: ['From', 'Start'] }, ['Name', 'Begins'], { Name: 'name', Begins: 'start_date' });
    expect(saved.start_date).toEqual(['From', 'Start', 'Begins']);
  });

  it('round-trips a clearing: an unselected column is no longer read', () => {
    const saved = applySelections({ name: ['Name'], start_date: ['Start'], end_date: ['END'] }, ['Name', 'Start', 'end'], { Name: 'name', Start: 'start_date' });
    expect(saved.end_date).toEqual([]);
    expect(selectionsFor(saved, ['Name', 'Start', 'end'])).toEqual({ Name: 'name', Start: 'start_date' });
  });
});

describe('selection problems', () => {
  it('groups columns that normalise to the same header', () => {
    expect(ambiguousHeaders(['Name', 'Start', ' start ', '', ' '])).toEqual([['Start', ' start ']]);
  });
  it('blocks a selection on an ambiguous header', () => {
    const problems = selectionProblems(['Name', 'Start', 'START'], { Name: 'name', Start: 'start_date' });
    expect(problems.join(' ')).toMatch(/Start.*START/);
  });
  it('ignores an ambiguity in a column that is not mapped', () => {
    expect(selectionProblems(['Name', 'Start', 'Notes', 'notes'], { Name: 'name', Start: 'start_date' })).toEqual([]);
  });
  it('blocks two columns selected for one field', () => {
    const problems = selectionProblems(['Name', 'Start', 'New Start'], { Name: 'name', Start: 'start_date', 'New Start': 'start_date' });
    expect(problems.join(' ')).toMatch(/Start date/);
  });
});
