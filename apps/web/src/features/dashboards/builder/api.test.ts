import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fixtureStarterDashboard, visualWidgets } from '@/design-lab/fixtures/builder';

import { createFromTemplate, duplicateBody, fetchCatalogV2, fetchTemplates, persistLayout } from './api';

const mocks = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn(), put: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiGet: mocks.get, apiPatch: mocks.patch, apiPut: mocks.put, apiPost: mocks.post }));
beforeEach(() => vi.resetAllMocks());

const widget = visualWidgets[0];
const board = { ...fixtureStarterDashboard, widgets: [{ ...widget, layout_json: { x: 0, y: 0, w: 6, h: 8 } }] };
const layout = [{ id: widget.id, x: 2, y: 3, w: 5, h: 7 }];

describe('builder API compatibility', () => {
  it('persists layout through the position-only PATCH without revalidating definitions', async () => {
    mocks.patch.mockResolvedValue(board);
    expect(await persistLayout(board, layout)).toEqual({ dashboard: board, route: 'patch' });
    expect(mocks.patch).toHaveBeenCalledWith(`/api/v1/dashboards/${board.id}/layout`, layout);
    expect(mocks.put).not.toHaveBeenCalled();
  });

  it.each([404, 405])('uses the old complete writer only for a missing layout route: %i', async (code) => {
    mocks.patch.mockRejectedValue(new Error(`Request failed (${code})`));
    mocks.put.mockResolvedValue(board);
    expect((await persistLayout(board, layout)).route).toBe('put');
    expect(mocks.put).toHaveBeenCalledWith(`/api/v1/dashboards/${board.id}/widgets`, {
      widgets: [expect.objectContaining({ id: widget.id, definition_v2: widget.definition_v2, layout_json: { x: 2, y: 3, w: 5, h: 7 } })],
    });
  });

  it.each([401, 403, 409, 500])('does not hide failures or retry writes through another route: %i', async (code) => {
    const error = new Error(`Request failed (${code})`);
    mocks.patch.mockRejectedValue(error);
    await expect(persistLayout(board, layout)).rejects.toBe(error);
    expect(mocks.put).not.toHaveBeenCalled();
  });

  it('permits the old API without a v2 catalog but propagates authorization errors', async () => {
    mocks.get.mockRejectedValueOnce(new Error('Not Found'));
    expect(await fetchCatalogV2()).toBeNull();
    mocks.get.mockRejectedValueOnce(new Error('Unauthorized (401)'));
    await expect(fetchCatalogV2()).rejects.toThrow('401');
  });

  it('tolerates old template route validation and keeps starter creation explicit', async () => {
    mocks.get.mockRejectedValueOnce(new Error('Validation (422)'));
    expect(await fetchTemplates()).toBeNull();
    mocks.post.mockResolvedValue(board);
    await createFromTemplate('account_overview');
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/dashboards/from-template', { key: 'account_overview' });
  });

  it('duplicates the existing definition without its migration marker, below all widgets', () => {
    const settings = { ignore_filters: ['customer'], fixed_window: { from: '2026-01-01', to: '2026-01-31' } };
    const copy = duplicateBody(board, { ...widget, definition_v2: { ...widget.definition_v2!, dashboard: settings } });
    expect(copy).toMatchObject({ title: `${widget.title} (copy)`, visual: widget.visual, layout_json: { y: 8 } });
    expect(copy.definition_v2?.query).toEqual(widget.definition_v2?.query);
    expect(copy.definition_v2).not.toHaveProperty('migrated_from');
    expect(copy.definition_v2?.dashboard).toEqual(settings);
    expect(widget.title).not.toContain('(copy)');
  });
});
