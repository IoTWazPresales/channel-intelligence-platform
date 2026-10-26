import path from 'node:path';
import { readFile } from 'node:fs/promises';
import { inflateRawSync } from 'node:zlib';
import { expect, test } from '@playwright/test';

import type { V2Request, V2Response } from '../src/features/dashboards/builder/types';

/** Read one ZIP member in memory; never extract a downloaded path to the workspace. */
function zipMember(zip: Buffer, name: string): string {
  const end = zip.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (end < 0) throw new Error('Downloaded workbook has no ZIP directory');
  const count = zip.readUInt16LE(end + 10);
  let cursor = zip.readUInt32LE(end + 16);
  for (let i = 0; i < count; i += 1) {
    if (zip.readUInt32LE(cursor) !== 0x02014b50) throw new Error('Invalid workbook ZIP directory');
    const method = zip.readUInt16LE(cursor + 10);
    const size = zip.readUInt32LE(cursor + 20);
    const length = zip.readUInt16LE(cursor + 28);
    const filename = zip.subarray(cursor + 46, cursor + 46 + length).toString('utf8');
    if (filename === name) {
      const local = zip.readUInt32LE(cursor + 42);
      const start = local + 30 + zip.readUInt16LE(local + 26) + zip.readUInt16LE(local + 28);
      const data = zip.subarray(start, start + size);
      if (method !== 0 && method !== 8) throw new Error('Unsupported workbook ZIP compression');
      return (method === 8 ? inflateRawSync(data) : data).toString('utf8');
    }
    cursor += 46 + length + zip.readUInt16LE(cursor + 30) + zip.readUInt16LE(cursor + 32);
  }
  throw new Error(`Workbook member is missing: ${name}`);
}

test('authenticated E4 preserves inherited dates, filters, sorted row limit and saved downloads', async ({ page, request }) => {
  const api = process.env.CIP_BUILDER_TEST_API!;
  const identity = await request.get(`${api}/__cip_test_identity`);
  expect(await identity.json()).toEqual({ database: 'cip_test', mode: 'rolled-back-test' });
  const token = process.env.CIP_BUILDER_TEST_TOKEN;
  if (!token) throw new Error('The transactional test harness must supply its ephemeral bearer.');
  await page.route('**/api/v1/**', async (route) => {
    if (new URL(route.request().url()).origin !== 'http://127.0.0.1:3107') {
      await route.abort();
      throw new Error('Refused an API destination outside the isolated E4 test web host.');
    }
    await route.continue();
  });
  await page.addInitScript((session) => localStorage.setItem('cip.auth.token.v1', session), token);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));

  await page.goto('/dashboards');
  await expect(page.getByTestId('dashboard-create')).toHaveAttribute('aria-haspopup', 'menu');
  await page.getByTestId('dashboard-create').click();
  await page.getByTestId('dashboard-create-blank').click();
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('E4 browser board');
  await page.getByTestId('dashboard-create-confirm').click();
  await page.getByTestId('dashboard-add-widget').click();
  await page.getByTestId('builder-editor-measure-dsi_sellout.units').click();
  await page.getByTestId('builder-editor-breakdown-product').click();
  await page.getByTestId('builder-editor-visual-bar').click();
  await page.getByRole('combobox', { name: 'Sort rows by' }).click();
  await page.getByRole('option', { name: /sell-out units, lowest first/i }).click();
  await page.getByTestId('builder-editor-limit').fill('1');
  await page.getByTestId('builder-editor-title').fill('E4 January sorted');
  const created = page.waitForResponse((r) => /\/dashboards\/\d+\/widgets$/.test(r.url()) && r.request().method() === 'POST');
  await page.getByTestId('builder-editor-save').click();
  const dashboard = await (await created).json();
  const widget = dashboard.widgets.find((w: { title: string }) => w.title === 'E4 January sorted');
  expect(widget.definition_v2.query.sort).toEqual({ by: 'dsi_sellout.units', dir: 'asc' });
  expect(widget.definition_v2.query.limit).toBe(1);
  expect(widget.definition_v2.dashboard?.fixed_window).toBeUndefined();
  const card = page.getByTestId(`dashboard-widget-${widget.id}`);
  await expect(card).toBeVisible();

  const fixed = { from: '2026-01-01', to: '2026-01-31' };
  await page.getByRole('combobox', { name: 'Date range', exact: true }).click();
  await page.getByRole('option', { name: 'Custom', exact: true }).click();
  await page.getByTestId('dashboard-filter-from').fill(fixed.from);
  await page.getByTestId('dashboard-filter-to').fill(fixed.to);
  await page.getByTestId('dashboard-filter-customer').click();
  const questionResponse = page.waitForResponse((r) => {
    if (!r.url().endsWith('/query/v2/execute') || r.request().method() !== 'POST') return false;
    const q = r.request().postDataJSON() as V2Request;
    return q.measures[0] === 'dsi_sellout.units' && q.limit === 1
      && q.period?.from === fixed.from && q.period?.to === fixed.to && Boolean(q.filters?.customer);
  });
  await page.getByRole('option', { name: /Fixture customer 0/ }).click();
  // Close the multiple-value picker before opening the widget menu.
  await page.getByRole('heading', { name: 'E4 browser board', exact: true }).click();
  const questionHttp = await questionResponse;
  expect(questionHttp.status()).toBe(200);
  const execution = questionHttp.request().postDataJSON() as V2Request;
  const answer = await questionHttp.json() as V2Response;
  expect(answer.ok).toBe(true);
  expect(answer.rows).toHaveLength(1);
  expect(answer.rows[0]).toMatchObject({ product_name: 'Fixture product 0', 'dsi_sellout.units': 13 });
  expect(answer.totals['dsi_sellout.units']).toBe(112);
  await expect(card.getByRole('table')).toContainText('Fixture product 0');
  await expect(card.getByRole('table')).toContainText('13');
  await expect(card.getByRole('table')).not.toContainText('900');
  await expect(page.getByTestId('dashboard-filter-save')).toBeEnabled();

  await card.getByRole('button', { name: /^Actions for / }).click();
  const promoted = page.waitForResponse((r) => r.url().endsWith(`/widgets/${widget.id}/promote`) && r.request().method() === 'POST');
  await page.getByTestId(`dashboard-widget-promote-${widget.id}`).click();
  const promotedHttp = await promoted;
  expect(promotedHttp.status()).toBe(200);
  expect(promotedHttp.request().postDataJSON()).toEqual({ execution });
  const report = (await promotedHttp.json()).saved_report;
  expect(report.definition_v2.dashboard.fixed_window).toEqual(fixed);
  expect(report.definition_v2.query.filters).toEqual(execution.filters);
  expect(report.definition_v2.query.sort).toEqual(execution.sort);
  expect(report.definition_v2.query.limit).toBe(1);
  expect(report.definition_v2.v1_equivalent).toBe(false);
  await expect(page.getByTestId('dashboard-promote-result')).toContainText('fixed dates');
  await card.screenshot({ path: path.resolve(__dirname, '../../../.eif/audit/EXECUTION_20261026_E4/frontend-card.png') });

  await page.goto('/reports');
  await page.getByTestId(`saved-report-${report.id}`).getByText(report.name, { exact: true }).click();
  await expect(page.getByTestId('report-saved-definition-note')).toContainText(`fixed dates: ${fixed.from} to ${fixed.to}`);
  await expect(page.getByTestId('report-run')).toBeDisabled();
  await expect(page.getByTestId('report-save')).toBeDisabled();
  await expect(page.getByTestId('report-grain-select')).toHaveCount(0);
  await expect(page.getByTestId('report-deliver-inbox')).toBeEnabled();

  for (const format of ['xlsx', 'pdf'] as const) {
    const downloaded = page.waitForEvent('download');
    const exported = page.waitForResponse((r) => r.url().endsWith(`/reports/saved/${report.id}/export?format=${format}`));
    await page.getByTestId(`report-export-${format}`).click();
    const exportedHttp = await exported;
    expect(exportedHttp.request().method()).toBe('GET');
    expect(exportedHttp.status()).toBe(200);
    const bytes = await readFile((await (await downloaded).path())!);
    if (format === 'xlsx') {
      const cover = zipMember(bytes, 'xl/worksheets/sheet1.xml');
      const data = zipMember(bytes, 'xl/worksheets/sheet2.xml');
      expect(cover).toContain('Value: 112');
      expect(cover).toContain(fixed.from);
      expect(cover).toContain(fixed.to);
      expect(data).toContain('dsi_sellout.units');
      expect(data).toContain('Fixture product 0');
      expect(data).toContain('<v>13</v>');
      expect(data.match(/<row\b/g)).toHaveLength(2);
      expect(data).not.toContain('Fixture product 1');
      expect(data).not.toContain('<v>900</v>');
    } else {
      const pdf = bytes.toString('latin1');
      expect(pdf.startsWith('%PDF-')).toBe(true);
      expect(pdf).toContain('Value: 112');
      expect(pdf).toContain(fixed.from);
      expect(pdf).toContain(fixed.to);
      expect(pdf).toContain('Fixture product 0');
      expect(pdf).toMatch(/"dsi_sellout.units": 13(?:\.0)?/);
      expect(pdf).not.toContain('Fixture product 1');
      expect(pdf).not.toContain('"dsi_sellout.units": 900');
    }
  }

  const delivered = page.waitForResponse((r) => r.url().endsWith(`/reports/saved/${report.id}/deliver`) && r.request().method() === 'POST');
  await page.getByTestId('report-deliver-inbox').click();
  const deliveryHttp = await delivered;
  expect(deliveryHttp.status()).toBe(200);
  const delivery = await deliveryHttp.json();
  expect(Number(delivery.value_preview)).toBe(112);
  expect(delivery.data_vintage.period).toEqual(fixed);
  await expect(page.getByTestId('report-action-msg')).toContainText('Sent to your Report inbox');
  await page.getByTestId('report-builder').screenshot({ path: path.resolve(__dirname, '../../../.eif/audit/EXECUTION_20261026_E4/frontend-report.png') });
  expect(errors).toEqual([]);
});
