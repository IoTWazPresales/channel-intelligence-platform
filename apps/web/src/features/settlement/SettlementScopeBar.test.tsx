import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SettlementScopeBar } from '@/features/settlement/SettlementScopeBar';
import { DEFAULT_SETTLEMENT_SCOPE } from '@/features/settlement/settlementViews';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams('state=open&view=desk'),
}));

vi.mock('@/features/settlement/useSettlementBook', () => ({
  useSettlementBook: () => ({ data: { open_case_count: 55 } }),
}));

describe('SettlementScopeBar', () => {
  it('renders deferred structural filters and disabled Apply honestly', () => {
    render(<SettlementScopeBar scope={DEFAULT_SETTLEMENT_SCOPE} onScopeChange={vi.fn()} />);

    expect(screen.getByTestId('settlement-scope-from-deferred')).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByTestId('settlement-scope-apply')).toBeDisabled();
    expect(screen.getByTestId('settlement-scope-apply')).toHaveTextContent('Apply (not active)');
    expect(screen.getByTestId('settlement-scope-state')).not.toBeDisabled();
    expect(screen.getByTestId('settlement-saved-view')).not.toBeDisabled();
  });
});
