import { describe, expect, it } from 'vitest';

import { matchNavLeaf, navPageChrome } from './navPageChrome';

describe('matchNavLeaf', () => {
  it('prefers the longer exact path over a parent prefix', () => {
    const match = matchNavLeaf('/commercial-planner/cpor-cases');
    expect(match?.item.href).toBe('/commercial-planner/cpor-cases');
    expect(match?.group.id).toBe('commercial-planning');
  });

  it('matches nested case routes to CPOR Cases, not Commercial Planner', () => {
    const match = matchNavLeaf('/commercial-planner/cpor-cases/12');
    expect(match?.item.href).toBe('/commercial-planner/cpor-cases');
  });

  it('prefers Channel Operations over Sell-Through for /sell-out', () => {
    const match = matchNavLeaf('/sell-out');
    expect(match?.item.label).toBe('Channel Operations');
  });

  it('prefers the query-specific Import Center leaf for CST reports', () => {
    const match = matchNavLeaf('/admin/imports', '?template=customer_sell_through');
    expect(match?.item.label).toBe('Customer Reports');
  });

  it('keeps bare Import Center when the template is not a dedicated leaf', () => {
    const match = matchNavLeaf('/admin/imports', '?template=inbound_shipments');
    expect(match?.item.label).toBe('Import Center');
  });

  it('still selects Customer Reports when other query params are present', () => {
    const match = matchNavLeaf('/admin/imports', '?job=42&template=customer_sell_through');
    expect(match?.item.label).toBe('Customer Reports');
  });
});

describe('navPageChrome', () => {
  it('builds group + leaf crumbs with a group hub href', () => {
    const chrome = navPageChrome('/shipping');
    expect(chrome.title).toBe('Inbound shipments');
    expect(chrome.crumbs).toEqual([
      { label: 'Channel Intelligence', href: '/sell-out' },
      { label: 'Inbound shipments' },
    ]);
  });

  it('omits the group href when the leaf is the group hub', () => {
    const chrome = navPageChrome('/sell-out');
    expect(chrome.crumbs[0]).toEqual({ label: 'Channel Intelligence' });
    expect(chrome.crumbs[1]).toEqual({ label: 'Channel Operations' });
  });

  it('links the parent leaf when extra crumbs are present', () => {
    const chrome = navPageChrome('/commercial-planner/cpor-cases/9', {
      extraCrumbs: [{ label: 'CPOR-9' }],
      title: 'CPOR-9',
    });
    expect(chrome.title).toBe('CPOR-9');
    expect(chrome.crumbs).toEqual([
      { label: 'Commercial Planning', href: '/commercial-planner' },
      { label: 'CPOR Cases', href: '/commercial-planner/cpor-cases' },
      { label: 'CPOR-9' },
    ]);
  });

  it('aligns Import Center title with the nav leaf', () => {
    const chrome = navPageChrome('/admin/imports');
    expect(chrome.title).toBe('Import Center');
    expect(chrome.crumbs).toEqual([
      { label: 'Data Imports' },
      { label: 'Import Center' },
    ]);
  });

  it('links Data Imports hub when the leaf is Customer Reports', () => {
    const chrome = navPageChrome('/admin/imports', { search: '?template=customer_sell_through' });
    expect(chrome.title).toBe('Customer Reports');
    expect(chrome.crumbs).toEqual([
      { label: 'Data Imports', href: '/admin/imports' },
      { label: 'Customer Reports' },
    ]);
  });

  it('does not invent a Master Data hub href', () => {
    const chrome = navPageChrome('/admin/products');
    expect(chrome.crumbs[0]).toEqual({ label: 'Master Data' });
    expect(chrome.crumbs[1]).toEqual({ label: 'Products' });
  });
});
