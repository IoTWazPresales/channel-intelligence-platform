import { describe, expect, it } from 'vitest';

import { matchNavLeaf, navPageChrome } from './navPageChrome';

describe('matchNavLeaf (D-0008)', () => {
  it('prefers the longer exact path over a parent prefix', () => {
    const match = matchNavLeaf('/commercial-planner/cpor-cases');
    expect(match?.item.href).toBe('/commercial-planner/cpor-cases');
    expect(match?.item.label).toBe('Case book');
    expect(match?.group.id).toBe('funding');
    expect(match?.group.label).toBe('Promotions & Funding');
  });

  it('matches nested case routes to Case book, not Plans & line economics', () => {
    const match = matchNavLeaf('/commercial-planner/cpor-cases/12');
    expect(match?.item.href).toBe('/commercial-planner/cpor-cases');
    expect(match?.item.label).toBe('Case book');
    expect(match?.group.id).toBe('funding');
  });

  it('owns claims evidence as its own Promotions & Funding leaf', () => {
    const match = matchNavLeaf('/commercial-planner/cpor-cases/claims');
    expect(match?.item.href).toBe('/commercial-planner/cpor-cases/claims');
    expect(match?.item.label).toBe('Claims evidence');
    expect(match?.group.id).toBe('funding');
  });

  it('owns sell-through under Stock & Sell-through, not a Channel Operations container', () => {
    const match = matchNavLeaf('/channel-intelligence');
    expect(match?.item.label).toBe('Sell-through');
    expect(match?.group.id).toBe('stock');
    expect(matchNavLeaf('/sell-out')).toBeNull();
  });

  it('prefers the query-specific CST leaf for customer sell-through files', () => {
    const match = matchNavLeaf('/admin/imports', '?template=customer_sell_through');
    expect(match?.item.label).toBe('Customer sell-through files');
    expect(match?.group.id).toBe('data');
  });

  it('keeps Import Center when the template is not a dedicated leaf', () => {
    const match = matchNavLeaf('/admin/imports', '?template=inbound_shipments');
    expect(match?.item.label).toBe('Import Center');
  });

  it('still selects CST files when other query params are present', () => {
    const match = matchNavLeaf('/admin/imports', '?job=42&template=customer_sell_through');
    expect(match?.item.label).toBe('Customer sell-through files');
  });
});

describe('navPageChrome (D-0008)', () => {
  it('builds domain + leaf crumbs with a domain hub href when the leaf is not the hub', () => {
    const chrome = navPageChrome('/stock', { search: '?lens=cover' });
    expect(chrome.title).toBe('Cover');
    expect(chrome.crumbs).toEqual([
      { label: 'Stock & Sell-through', href: '/stock' },
      { label: 'Cover' },
    ]);
  });

  it('omits the domain href when the leaf is the domain hub', () => {
    const chrome = navPageChrome('/brief');
    expect(chrome.crumbs[0]).toEqual({ label: 'Overview' });
    expect(chrome.crumbs[1]).toEqual({ label: 'Attention' });
  });

  it('links the parent leaf when extra crumbs are present', () => {
    const chrome = navPageChrome('/commercial-planner/cpor-cases/9', {
      extraCrumbs: [{ label: 'CPOR-9' }],
      title: 'CPOR-9',
    });
    expect(chrome.title).toBe('CPOR-9');
    expect(chrome.crumbs).toEqual([
      { label: 'Promotions & Funding', href: '/commercial-planner/cpor-cases' },
      { label: 'Case book', href: '/commercial-planner/cpor-cases' },
      { label: 'CPOR-9' },
    ]);
  });

  it('aligns Import Center title with the nav leaf', () => {
    const chrome = navPageChrome('/admin/imports');
    expect(chrome.title).toBe('Import Center');
    expect(chrome.crumbs).toEqual([
      { label: 'Data & Stewardship' },
      { label: 'Import Center' },
    ]);
  });

  it('links Data & Stewardship hub when the leaf is CST files', () => {
    const chrome = navPageChrome('/admin/imports', { search: '?template=customer_sell_through' });
    expect(chrome.title).toBe('Customer sell-through files');
    expect(chrome.crumbs).toEqual([
      { label: 'Data & Stewardship', href: '/admin/imports' },
      { label: 'Customer sell-through files' },
    ]);
  });

  it('does not invent a Master Data hub; products sit under Data & Stewardship', () => {
    const chrome = navPageChrome('/admin/products');
    expect(chrome.crumbs[0]).toEqual({ label: 'Data & Stewardship', href: '/admin/imports' });
    expect(chrome.crumbs[1]).toEqual({ label: 'Products' });
  });

  it('matches inbound shipments on the stock lens, not a retired /shipping route', () => {
    const chrome = navPageChrome('/stock', { search: '?lens=inbound' });
    expect(chrome.title).toBe('Shipments');
    expect(chrome.crumbs).toEqual([
      { label: 'Supply & Inbound' },
      { label: 'Shipments' },
    ]);
    expect(matchNavLeaf('/shipping')).toBeNull();
  });
});
